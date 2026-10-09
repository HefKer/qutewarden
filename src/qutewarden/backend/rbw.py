"""The rbw Backend (rbw >= 1.15). See docs/adr/0003-rbw-1-15-and-match-types-from-its-db.md.

Security rule 2: secrets go to rbw only through stdin (``rbw add``/``rbw edit``,
which read stdin instead of opening ``$EDITOR`` when it isn't a terminal) and
come back only through stdout (``rbw get --raw``). Error text never includes
stdin data or the output of secret-returning commands.

Re-prompt items make rbw ask for the master password on every decryption, so:
``list_logins`` never decrypts an Item (``rbw list --raw`` plus the match types
read from rbw's local db file), ``list_cards`` decrypts only Card items that
aren't Re-prompt items (for their brand and last 4 digits), and ``get_secrets``
makes exactly one ``rbw get --raw`` call and computes the TOTP code locally.

``rbw get --raw`` doesn't say which item type it printed, so the type always
comes from the db file (ADR-0003, amendment for v2).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qutewarden import proc
from qutewarden.backend.base import (
    Backend,
    BackendError,
    BackendUnavailable,
    ItemNotFound,
    NotLoggedIn,
    SaveFailed,
    UnlockFailed,
)
from qutewarden.model import (
    CardItem,
    CardSecrets,
    ItemSecrets,
    ItemUri,
    LoginItem,
    LoginSecrets,
    MatchMode,
    Status,
)
from qutewarden.totp import totp_code

MIN_VERSION = (1, 15)
_NOT_LOGGED_IN_STDERR = "failed to find email address in config"
_LOGIN_HINT = "run `rbw config set email <address>` and `rbw login`"
# The server rejected rbw's refresh token; rbw then fails to parse the reply.
_EXPIRED_LOGIN_STDERR = "missing field `access_token`"
_RELOGIN_HINT = "run `rbw login` (`rbw purge` first if that fails)"
# Userscripts have no terminal, so a curses/tty pinentry fails with ENOTTY.
_NO_TTY_STDERR = "Inappropriate ioctl for device"
_PINENTRY_HINT = ("rbw's pinentry must be graphical: run `rbw config set pinentry pinentry-qt` "
                  "(or pinentry-gnome3, pinentry-bemenu, pinentry-rofi, ...), "
                  "then `rbw stop-agent`")
_SYNC_HINT = "run `rbw sync`"

# rbw's UriMatchType (serde_repr u8) -> MatchMode
_MATCH_TYPES = {
    0: MatchMode.BASE_DOMAIN,
    1: MatchMode.HOST,
    2: MatchMode.STARTS_WITH,
    3: MatchMode.EXACT,
    4: MatchMode.REGULAR_EXPRESSION,
    5: MatchMode.NEVER,
}


@dataclass(frozen=True)
class _DbEntry:
    """The non-secret, unencrypted bits of one Item in rbw's db file."""

    type: str  # rbw's item type: "Login", "Card", "Identity", "SecureNote", "SshKey"
    reprompt: bool
    has_totp: bool = False
    match_types: tuple[object, ...] = ()  # one per URI, Login items only


class RbwBackend(Backend):
    name = "rbw"

    def __init__(self, environ: Mapping[str, str], *, executable: str = "rbw",
                 clock: Callable[[], float] = time.time) -> None:
        self._environ = environ
        self._executable = executable
        self._clock = clock
        self._version_ok = False

    # --- lock state ---------------------------------------------------------

    def is_unlocked(self) -> bool:
        return self._run(["unlocked"]).returncode == 0

    def unlock(self) -> None:
        result = self._run(["unlock"])
        if result.returncode != 0:
            raise self._error(result, UnlockFailed, "rbw couldn't unlock the vault")

    def lock(self) -> None:
        self._run_checked(["lock"])

    def sync(self) -> None:
        self._run_checked(["sync"])

    def status(self) -> Status:
        unlocked = self.is_unlocked()
        try:
            mtime = self._db_path().stat().st_mtime
        except (NotLoggedIn, OSError):
            return Status(unlocked=unlocked, last_sync=None)
        return Status(unlocked=unlocked,
                      last_sync=datetime.fromtimestamp(mtime, tz=UTC))

    # --- reading ----------------------------------------------------------------

    def list_logins(self) -> list[LoginItem]:
        listed = _parse_json(self._run_checked(["list", "--raw"]).stdout, "rbw list")
        db = self._read_db()
        logins = []
        for entry in listed:
            if entry.get("type") != "Login":
                continue
            uris = [u for u in entry.get("uris") or [] if isinstance(u, str)]
            info = db.get(entry["id"])
            if info is not None and len(info.match_types) == len(uris):
                modes = [_match_mode(m) for m in info.match_types]
            else:  # rbw dropped an undecryptable URI: never guess a looser mode
                modes = [MatchMode.NEVER] * len(uris)
            logins.append(LoginItem(
                id=entry["id"],
                name=entry.get("name") or "",
                username=entry.get("user") or None,
                uris=tuple(ItemUri(uri, mode) for uri, mode in zip(uris, modes)),
                has_totp=bool(info and info.has_totp),
                reprompt=bool(info and info.reprompt),
            ))
        return logins

    def list_cards(self) -> list[CardItem]:
        listed = _parse_json(self._run_checked(["list", "--raw"]).stdout, "rbw list")
        db = self._read_db()
        cards = []
        for entry in listed:
            info = db.get(entry.get("id"))
            if info is None or info.type != "Card":
                continue
            card = CardItem(id=entry["id"], name=entry.get("name") or "", reprompt=info.reprompt)
            if not info.reprompt:  # a Re-prompt item would ask for the master password
                data = self._get_data(card.id)
                card = CardItem(id=card.id, name=card.name, brand=_text(data.get("brand")),
                                last4=_last4(_text(data.get("number"))))
            cards.append(card)
        return cards

    def get_secrets(self, item_id: str) -> ItemSecrets:
        info = self._read_db().get(item_id)
        if info is None:
            raise ItemNotFound("rbw has no item with that id", hint=_SYNC_HINT)
        if info.type == "Login":
            return self._login_secrets(self._get_data(item_id))
        if info.type == "Card":
            data = self._get_data(item_id)
            return CardSecrets(**{f.name: _text(data.get(f.name)) for f in fields(CardSecrets)})
        raise BackendError("this item type can't be filled")

    def _login_secrets(self, data: dict[str, Any]) -> LoginSecrets:
        seed = data.get("totp")
        code = None
        if seed:
            try:
                code = totp_code(seed, now=self._clock())
            except ValueError:
                raise BackendError("this item's TOTP secret isn't valid") from None
        return LoginSecrets(password=data.get("password"), totp=code)

    # --- writing ----------------------------------------------------------------

    def create_login(self, *, name: str, username: str | None, uri: str,
                     password: str) -> None:
        _check_password(password)
        argv = ["add", "--uri", uri, "--", name]
        if username:
            argv.append(username)
        if self._run(argv, input=password + "\n").returncode != 0:
            raise SaveFailed("rbw couldn't save the new login")

    def update_password(self, item_id: str, password: str) -> None:
        _check_password(password)
        notes = self._get_raw(item_id).get("notes") or ""
        # rbw edit replaces password *and* notes from stdin, and drops note lines
        # starting with "#"; refuse rather than lose them.
        if any(line.startswith("#") for line in notes.splitlines()):
            raise SaveFailed("this item's notes have lines starting with '#' that rbw would drop; "
                             "change the password with rbw edit")
        stdin = f"{password}\n\n{notes}" if notes else f"{password}\n"
        if self._run(["edit", "--", item_id], input=stdin).returncode != 0:
            raise SaveFailed("rbw couldn't save the new password")

    # --- helpers ----------------------------------------------------------------

    def _run(self, args: list[str], *, input: str | None = None):
        self._check_version()
        return self._spawn(args, input=input)

    def _spawn(self, args: list[str], *, input: str | None = None):
        try:
            return proc.run([self._executable, *args], input=input, check=False)
        except OSError:
            raise BackendUnavailable(f"can't run {self._executable}",
                                     hint="install rbw >= 1.15") from None

    def _check_version(self) -> None:
        if self._version_ok:
            return
        result = self._spawn(["--version"])
        match = re.search(r"(\d+)\.(\d+)", result.stdout)
        found = tuple(int(n) for n in match.groups()) if match else None
        if result.returncode != 0 or found is None or found < MIN_VERSION:
            shown = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "unknown"
            raise BackendUnavailable(f"rbw >= 1.15 required (found {shown})")
        self._version_ok = True

    def _run_checked(self, args: list[str]):
        """Run a command that handles no secrets; its stderr may be shown."""
        result = self._run(args)
        if result.returncode != 0:
            raise self._error(result, BackendError, f"rbw {args[0]} failed")
        return result

    @staticmethod
    def _error(result, cls: type[BackendError], fallback: str) -> BackendError:
        known = _known_error(result.stderr)
        if known is not None:
            return known
        lines = result.stderr.strip().splitlines()
        return cls(lines[0] if lines else fallback)

    def _get_raw(self, item_id: str) -> dict[str, Any]:
        """One ``rbw get --raw``. Its stdout and stderr are never put in errors."""
        result = self._run(["get", "--raw", "--", item_id])
        if result.returncode != 0:
            known = _known_error(result.stderr)
            if known is not None:
                raise known
            if "no entry found" in result.stderr or "couldn't find entry" in result.stderr:
                raise ItemNotFound("rbw has no item with that id", hint=_SYNC_HINT)
            raise BackendError("rbw get failed")
        item = _parse_json(result.stdout, "rbw get")
        if not isinstance(item, dict):
            raise BackendError("couldn't parse rbw get output")
        return item

    def _get_data(self, item_id: str) -> dict[str, Any]:
        """The Item's values from one ``rbw get --raw`` (keys as rbw names them)."""
        data = self._get_raw(item_id).get("data")
        return data if isinstance(data, dict) else {}

    def _db_path(self) -> Path:
        """rbw's local db file: <cache>/<profile>/<server>:<email>.json (rbw src/dirs.rs)."""
        config = _parse_json(self._run_checked(["config", "show"]).stdout, "rbw config show")
        email = config.get("email") if isinstance(config, dict) else None
        if not email:
            raise NotLoggedIn("rbw isn't logged in", hint=_LOGIN_HINT)
        server = _percent_encode(config.get("base_url") or "default")
        return self._cache_dir() / f"{server}:{email}.json"

    def _cache_dir(self) -> Path:
        base = self._environ.get("XDG_CACHE_HOME", "")
        if not os.path.isabs(base):
            base = os.path.join(self._environ.get("HOME") or str(Path.home()), ".cache")
        profile = self._environ.get("RBW_PROFILE", "")
        return Path(base) / (f"rbw-{profile}" if profile else "rbw")

    def _read_db(self) -> dict[str, _DbEntry]:
        """Read only the non-secret, unencrypted bits we need: id -> type, reprompt, URI modes.

        The file is opened read-only and never written. Everything else in it
        (tokens, encrypted fields) is dropped right away.
        """
        path = self._db_path()
        try:
            with open(path, encoding="utf-8") as f:
                entries = json.load(f).get("entries") or []
        except (OSError, ValueError, AttributeError):
            raise BackendError("can't read rbw's local db file", hint=_SYNC_HINT) from None
        db = {}
        for entry in entries:
            # rbw's Data enum: {"Login": {...}}, {"Card": {...}}, ... or "SecureNote".
            data = entry.get("data")
            if isinstance(data, dict) and len(data) == 1:
                [(item_type, values)] = data.items()
            elif isinstance(data, str):
                item_type, values = data, None
            else:
                continue
            reprompt = entry.get("master_password_reprompt") not in (None, 0)
            if item_type == "Login" and isinstance(values, dict):
                db[entry.get("id")] = _DbEntry(
                    "Login", reprompt, has_totp=values.get("totp") is not None,
                    # Old dbs store bare URI strings, which rbw treats as match_type None.
                    match_types=tuple(u.get("match_type") if isinstance(u, dict) else None
                                      for u in values.get("uris") or []))
            else:
                db[entry.get("id")] = _DbEntry(str(item_type), reprompt)
        return db


def _known_error(stderr: str) -> BackendError | None:
    """rbw failures with a fixed message and a fix; never includes ``stderr`` itself."""
    if _NOT_LOGGED_IN_STDERR in stderr:
        return NotLoggedIn("rbw isn't logged in", hint=_LOGIN_HINT)
    if _EXPIRED_LOGIN_STDERR in stderr:
        return NotLoggedIn("rbw's login has expired", hint=_RELOGIN_HINT)
    if _NO_TTY_STDERR in stderr and "pinentry" in stderr.lower():
        return UnlockFailed("rbw's pinentry needs a terminal", hint=_PINENTRY_HINT)
    return None


def _match_mode(match_type: object) -> MatchMode | None:
    if match_type is None:
        return None
    if not isinstance(match_type, int):
        return MatchMode.NEVER  # unknown: never match
    return _MATCH_TYPES.get(match_type, MatchMode.NEVER)


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _last4(number: str | None) -> str | None:
    """The last 4 digits of a card number (Security rule 6 allows no more), if it has 4."""
    digits = re.sub(r"\D", "", number or "")
    return digits[-4:] if len(digits) >= 4 else None


def _check_password(password: str) -> None:
    if "\n" in password or "\r" in password:
        raise SaveFailed("passwords with line breaks can't be saved through rbw")


def _parse_json(text: str, what: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        raise BackendError(f"couldn't parse {what} output") from None


def _percent_encode(text: str) -> str:
    """percent_encoding with rbw's INVALID_PATH set: controls, non-ASCII, '/', '%', ':'."""
    out = []
    for byte in text.encode("utf-8"):
        if byte < 0x20 or byte >= 0x7F or chr(byte) in "/%:":
            out.append(f"%{byte:02X}")
        else:
            out.append(chr(byte))
    return "".join(out)
