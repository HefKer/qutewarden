"""RbwBackend against a fake ``rbw`` executable that serves fixtures.

The real rbw is never run: every test passes the absolute path of a fake script
(written to tmp_path) that answers from a response table and records its argv,
stdin and environment.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from qutewarden.backend.base import (
    BackendError,
    BackendUnavailable,
    ItemNotFound,
    NotLoggedIn,
    SaveFailed,
    UnlockFailed,
)
from qutewarden.backend.fake import SECRET_MARKER
from qutewarden.backend.rbw import RbwBackend
from qutewarden.model import (
    CardItem,
    CardSecrets,
    IdentityItem,
    IdentitySecrets,
    ItemUri,
    LoginItem,
    LoginSecrets,
    MatchMode,
)

FIXTURES = Path(__file__).parent / "fixtures" / "rbw"
GITHUB_ID = "6f1c2d4e-8a3b-4c5d-9e7f-0a1b2c3d4e5f"
BANK_ID = "a2c4e6f8-1b3d-4f5a-9c7e-0d2f4a6b8c1e"
CARD_ID = "e5f7a9b1-3c5d-4e7f-8a9b-1c3d5e7f9a0b"
OLD_CARD_ID = "f7b9c1d3-5e7f-4a9b-8c1d-3e5f7a9b1c2d"  # a Re-prompt Card item
IDENTITY_ID = "1a3c5e7a-9b1d-4f3a-8c5e-7a9b1d3f5a7c"
PASSPORT_ID = "2b4d6f8b-0c2e-4a4b-9d6f-8b0c2e4a6b8d"  # a Re-prompt Identity item
NOTE_ID = "0b9e7a1c-2d3f-4e5a-8b6c-7d8e9f0a1b2c"
EMAIL = "alice@example.com"
CONFIG_SHOW = json.dumps({"email": EMAIL, "sso_id": None, "base_url": None, "identity_url": None,
                          "ui_url": None, "notifications_url": None, "lock_timeout": 3600,
                          "sync_interval": 3600, "pinentry": "pinentry", "client_cert_path": None})
NO_TTY_PINENTRY_STDERR = ("rbw unlock: failed to read password from pinentry: pinentry error: "
                          "Inappropriate ioctl for device <Pinentry>\n")
EXPIRED_LOGIN_STDERR = ("rbw sync: failed to sync database from server: failed to parse JSON: "
                        "missing field `access_token` at line 1 column 120\n")

FAKE_RBW = r'''#!{python}
import json, os, sys
here = {here!r}
stdin = sys.stdin.read()
with open(os.path.join(here, "calls.jsonl"), "a") as log:
    log.write(json.dumps({{"argv": sys.argv[1:], "stdin": stdin, "env": dict(os.environ)}}) + "\n")
with open(os.path.join(here, "responses.json")) as f:
    responses = json.load(f)
for r in responses:
    if r["argv"] == sys.argv[1:]:
        sys.stdout.write(r["stdout"]); sys.stderr.write(r["stderr"]); sys.exit(r["rc"])
sys.stderr.write("rbw: unexpected call\n"); sys.exit(1)
'''


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class FakeRbw:
    def __init__(self, tmp_path: Path) -> None:
        self.dir = tmp_path / "fakerbw"
        self.dir.mkdir()
        self.path = self.dir / "rbw"
        self.path.write_text(FAKE_RBW.format(python=sys.executable, here=str(self.dir)))
        self.path.chmod(0o700)
        self.responses: list[dict] = []
        self.cache = tmp_path / "cache"
        self.environ = {"HOME": str(tmp_path / "home"), "XDG_CACHE_HOME": str(self.cache)}
        self.respond(["--version"], "rbw 1.15.0\n")
        self.respond(["config", "show"], CONFIG_SHOW + "\n")

    def respond(self, argv: list[str], stdout: str = "", stderr: str = "", rc: int = 0) -> None:
        self.responses.insert(0, {"argv": argv, "stdout": stdout, "stderr": stderr, "rc": rc})
        (self.dir / "responses.json").write_text(json.dumps(self.responses))

    def write_db(self, name: str = f"default:{EMAIL}.json", profile_dir: str = "rbw") -> Path:
        path = self.cache / profile_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(fixture("db_cache.json"))
        return path

    @property
    def calls(self) -> list[dict]:
        log = self.dir / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text().splitlines()]

    @property
    def argvs(self) -> list[list[str]]:
        return [c["argv"] for c in self.calls if c["argv"] != ["--version"]]

    def backend(self, **kwargs) -> RbwBackend:
        return RbwBackend(self.environ, executable=str(self.path), **kwargs)


@pytest.fixture
def rbw(tmp_path: Path) -> FakeRbw:
    return FakeRbw(tmp_path)


# --- availability -----------------------------------------------------------

def test_missing_rbw_is_backend_unavailable(tmp_path: Path):
    backend = RbwBackend({}, executable=str(tmp_path / "no-such-rbw"))
    with pytest.raises(BackendUnavailable):
        backend.is_unlocked()


def test_rbw_older_than_1_15_is_backend_unavailable(rbw):
    rbw.respond(["--version"], "rbw 1.14.2\n")
    with pytest.raises(BackendUnavailable, match="1.15"):
        rbw.backend().is_unlocked()
    assert rbw.argvs == []


def test_version_is_checked_once(rbw):
    rbw.respond(["unlocked"])
    backend = rbw.backend()
    backend.is_unlocked()
    backend.is_unlocked()
    assert [c["argv"] for c in rbw.calls].count(["--version"]) == 1


# --- lock state -------------------------------------------------------------

def test_is_unlocked_follows_rbw_unlocked_exit_code(rbw):
    rbw.respond(["unlocked"])
    assert rbw.backend().is_unlocked() is True
    rbw.respond(["unlocked"], stderr="rbw unlocked: agent is locked\n", rc=1)
    assert rbw.backend().is_unlocked() is False


def test_unlock_lock_sync_call_rbw(rbw):
    for sub in ("unlock", "lock", "sync"):
        rbw.respond([sub])
    backend = rbw.backend()
    backend.unlock()
    backend.lock()
    backend.sync()
    assert rbw.argvs == [["unlock"], ["lock"], ["sync"]]


def test_unlock_failure_is_unlock_failed_with_rbw_stderr(rbw):
    rbw.respond(["unlock"], stderr="rbw unlock: failed to unlock: pinentry cancelled\nmore\n", rc=1)
    with pytest.raises(UnlockFailed) as excinfo:
        rbw.backend().unlock()
    assert "pinentry cancelled" in str(excinfo.value)
    assert "more" not in str(excinfo.value)


def test_not_logged_in_is_reported_with_a_hint(rbw):
    rbw.respond(["unlock"], stderr="rbw unlock: failed to find email address in config\n", rc=1)
    with pytest.raises(NotLoggedIn) as excinfo:
        rbw.backend().unlock()
    assert "rbw login" in (excinfo.value.hint or "")


def test_sync_failure_is_backend_error(rbw):
    rbw.respond(["sync"], stderr="rbw sync: failed to sync: network down\n", rc=1)
    with pytest.raises(BackendError, match="network down"):
        rbw.backend().sync()


def test_unlock_with_terminal_only_pinentry_asks_for_a_graphical_one(rbw):
    rbw.respond(["unlock"], stderr=NO_TTY_PINENTRY_STDERR, rc=1)
    with pytest.raises(UnlockFailed) as excinfo:
        rbw.backend().unlock()
    assert "Inappropriate ioctl" not in str(excinfo.value)
    assert "rbw config set pinentry pinentry-qt" in (excinfo.value.hint or "")
    assert "rbw stop-agent" in (excinfo.value.hint or "")


def test_cancelled_pinentry_keeps_rbw_stderr_and_has_no_hint(rbw):
    rbw.respond(["unlock"], stderr="rbw unlock: failed to read password from pinentry: "
                                   "pinentry error: Operation cancelled <Pinentry>\n", rc=1)
    with pytest.raises(UnlockFailed) as excinfo:
        rbw.backend().unlock()
    assert "Operation cancelled" in str(excinfo.value)
    assert excinfo.value.hint is None


def test_other_no_tty_errors_are_not_blamed_on_pinentry(rbw):
    rbw.respond(["unlock"], stderr="rbw unlock: Inappropriate ioctl for device\n", rc=1)
    with pytest.raises(UnlockFailed) as excinfo:
        rbw.backend().unlock()
    assert excinfo.value.hint is None


def test_sync_with_rejected_refresh_token_asks_to_log_in_again(rbw):
    rbw.respond(["sync"], stderr=EXPIRED_LOGIN_STDERR, rc=1)
    with pytest.raises(NotLoggedIn) as excinfo:
        rbw.backend().sync()
    assert "access_token" not in str(excinfo.value)
    assert "rbw login" in (excinfo.value.hint or "")
    assert "rbw purge" in (excinfo.value.hint or "")


def test_status_reports_unlocked_and_db_mtime_as_last_sync(rbw):
    rbw.respond(["unlocked"])
    db = rbw.write_db()
    os.utime(db, (1_700_000_000, 1_700_000_000))
    status = rbw.backend().status()
    assert status.unlocked is True
    assert status.last_sync == datetime.fromtimestamp(1_700_000_000, tz=UTC)


def test_status_without_db_has_unknown_last_sync(rbw):
    rbw.respond(["unlocked"], stderr="rbw unlocked: agent is locked\n", rc=1)
    status = rbw.backend().status()
    assert status.unlocked is False and status.last_sync is None


# --- list_logins ------------------------------------------------------------

def test_list_logins_joins_rbw_list_with_match_types_from_the_db(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.write_db()
    logins = {item.id: item for item in rbw.backend().list_logins()}

    assert set(logins) == {BANK_ID, GITHUB_ID, "d4e6f8a0-2b4c-4d6e-9f8a-0b2c4d6e8f1a",
                           "c3d5e7f9-1a2b-4c3d-8e9f-a0b1c2d3e4f5"}  # Logins only
    assert logins[GITHUB_ID] == LoginItem(
        id=GITHUB_ID, name="GitHub", username="alice@example.com", has_totp=True, reprompt=False,
        uris=(ItemUri("https://github.com/login", None),
              ItemUri("github.com", MatchMode.BASE_DOMAIN),
              ItemUri("https://gist.github.com", MatchMode.HOST),
              ItemUri("https://github.com/settings", MatchMode.STARTS_WITH),
              ItemUri("https://github.com/session", MatchMode.EXACT),
              ItemUri("^https://([a-z]+\\.)?github\\.com/.*$", MatchMode.REGULAR_EXPRESSION),
              ItemUri("https://evil.example", MatchMode.NEVER)))


def test_list_logins_reads_reprompt_and_old_style_uris(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.write_db()
    logins = {item.id: item for item in rbw.backend().list_logins()}
    assert logins[BANK_ID] == LoginItem(id=BANK_ID, name="Bank", username="alice",
                                        uris=(ItemUri("https://bank.example", None),),
                                        has_totp=False, reprompt=True)
    router = logins["c3d5e7f9-1a2b-4c3d-8e9f-a0b1c2d3e4f5"]
    assert router.uris == () and router.username == "admin"


def test_list_logins_never_guesses_modes_when_uri_counts_differ(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.write_db()
    partial = {i.id: i for i in rbw.backend().list_logins()}["d4e6f8a0-2b4c-4d6e-9f8a-0b2c4d6e8f1a"]
    assert partial.uris == (ItemUri("https://partial.example", MatchMode.NEVER),)


def test_list_logins_never_decrypts_items(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.write_db()
    rbw.backend().list_logins()
    assert not any(argv[0] in ("get", "code") for argv in rbw.argvs)


def test_list_logins_without_db_asks_for_sync(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().list_logins()
    assert "rbw sync" in (excinfo.value.hint or "")


def test_list_logins_not_logged_in_when_config_has_no_email(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["config", "show"], json.dumps({"email": None, "base_url": None}))
    with pytest.raises(NotLoggedIn):
        rbw.backend().list_logins()


def test_db_path_follows_base_url_and_rbw_profile(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["config", "show"],
                json.dumps({"email": EMAIL, "base_url": "https://vault.example.com/"}))
    rbw.environ["RBW_PROFILE"] = "work"
    rbw.write_db(name=f"https%3A%2F%2Fvault.example.com%2F:{EMAIL}.json", profile_dir="rbw-work")
    assert len(rbw.backend().list_logins()) == 4


# --- list_cards -------------------------------------------------------------

def test_list_cards_takes_card_items_from_the_db_with_brand_and_last_4_digits(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["get", "--raw", "--", CARD_ID], fixture("get_raw_card.json"))
    rbw.write_db()
    assert rbw.backend().list_cards() == [
        CardItem(id=CARD_ID, name="Card", brand="Visa", last4="1234"),
        CardItem(id=OLD_CARD_ID, name="Old card", reprompt=True),
    ]


def test_list_cards_never_decrypts_a_reprompt_card(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["get", "--raw", "--", CARD_ID], fixture("get_raw_card.json"))
    rbw.write_db()
    rbw.backend().list_cards()
    assert [argv for argv in rbw.argvs if argv[0] == "get"] == [["get", "--raw", "--", CARD_ID]]


@pytest.mark.parametrize("number, last4", [
    ("4111-1111-1111-0042", "0042"), ("123", None), (None, None), ("", None)])
def test_list_cards_shows_only_the_last_4_digits_of_the_number(rbw, number, last4):
    item = json.loads(fixture("get_raw_card.json"))
    item["data"]["number"] = number
    item["data"]["brand"] = None
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["get", "--raw", "--", CARD_ID], json.dumps(item))
    rbw.write_db()
    [card, _] = rbw.backend().list_cards()
    assert (card.brand, card.last4) == (None, last4)


def test_list_cards_without_db_asks_for_sync(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().list_cards()
    assert excinfo.value.hint == "run `rbw sync`"


# --- list_identities --------------------------------------------------------

def test_list_identities_takes_identity_items_from_the_db_without_decrypting_any(rbw):
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.write_db()
    assert rbw.backend().list_identities() == [
        IdentityItem(id=IDENTITY_ID, name="Me"),
        IdentityItem(id=PASSPORT_ID, name="Passport", reprompt=True),
    ]
    assert not any(argv[0] == "get" for argv in rbw.argvs)


# --- get_secrets ------------------------------------------------------------

def test_get_secrets_parses_rbw_get_raw_with_one_call(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], fixture("get_raw_login.json"))
    rbw.write_db()
    secrets = rbw.backend().get_secrets(GITHUB_ID)
    assert isinstance(secrets, LoginSecrets)
    assert secrets.password == "QWSECRET-rbw-password"
    assert secrets.totp is not None and secrets.totp.isdigit() and len(secrets.totp) == 6
    assert [argv for argv in rbw.argvs if argv[0] == "get"] == [["get", "--raw", "--", GITHUB_ID]]


def test_get_secrets_of_a_card_item_returns_its_card_values(rbw):
    rbw.respond(["get", "--raw", "--", CARD_ID], fixture("get_raw_card.json"))
    rbw.write_db()
    assert rbw.backend().get_secrets(CARD_ID) == CardSecrets(
        cardholder_name="Alice Example", number="QWSECRET-rbw-4111 1111 1111 1234",
        brand="Visa", exp_month="3", exp_year="2030", code="QWSECRET-rbw-code")


def test_get_secrets_of_an_identity_item_returns_its_identity_values(rbw):
    rbw.respond(["get", "--raw", "--", IDENTITY_ID], fixture("get_raw_identity.json"))
    rbw.write_db()
    assert rbw.backend().get_secrets(IDENTITY_ID) == IdentitySecrets(
        title="Dr", first_name="Alice", middle_name="M", last_name="Example",
        address1="QWSECRET-rbw-1 Main St", address2="Apt 2", city="Springfield", state="IL",
        postal_code="62701", country="US", phone="QWSECRET-rbw-555-0100",
        email="alice@example.com", ssn="QWSECRET-rbw-ssn", username="alice")


def test_get_secrets_takes_the_item_type_from_the_db_not_from_the_keys(rbw):
    # A Card whose values happen to look like nothing in particular.
    rbw.respond(["get", "--raw", "--", CARD_ID], json.dumps(
        {"id": CARD_ID, "name": "Card", "data": {"username": "x", "password": "y"}}))
    rbw.write_db()
    assert rbw.backend().get_secrets(CARD_ID) == CardSecrets()


def test_get_secrets_of_an_item_missing_from_the_db_asks_for_sync(rbw):
    rbw.write_db()
    with pytest.raises(ItemNotFound) as excinfo:
        rbw.backend().get_secrets("nope")
    assert excinfo.value.hint == "run `rbw sync`"
    assert not any(argv[0] == "get" for argv in rbw.argvs)


def test_get_secrets_of_a_secure_note_is_refused_without_decrypting(rbw):
    rbw.write_db()
    with pytest.raises(BackendError, match="can't be filled"):
        rbw.backend().get_secrets(NOTE_ID)
    assert not any(argv[0] == "get" for argv in rbw.argvs)


def test_get_secrets_computes_the_totp_code_from_the_seed(rbw):
    rbw.write_db()
    item = json.loads(fixture("get_raw_login.json"))
    item["data"]["totp"] = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # RFC 6238 seed
    rbw.respond(["get", "--raw", "--", GITHUB_ID], json.dumps(item))
    secrets = rbw.backend(clock=lambda: 59.0).get_secrets(GITHUB_ID)
    assert secrets == LoginSecrets(password="QWSECRET-rbw-password", totp="287082")


def test_get_secrets_without_totp_or_password(rbw):
    rbw.write_db()
    rbw.respond(["get", "--raw", "--", BANK_ID], fixture("get_raw_reprompt.json"))
    assert rbw.backend().get_secrets(BANK_ID) == LoginSecrets(password="QWSECRET-rbw-bank-password")
    item = json.loads(fixture("get_raw_reprompt.json"))
    item["data"]["password"] = None
    rbw.respond(["get", "--raw", "--", BANK_ID], json.dumps(item))
    assert rbw.backend().get_secrets(BANK_ID) == LoginSecrets()


def test_get_secrets_of_an_item_rbw_get_cannot_find(rbw):
    rbw.write_db()
    rbw.respond(["get", "--raw", "--", BANK_ID],
                stderr="rbw get: couldn't find entry for 'x': no entry found\n", rc=1)
    with pytest.raises(ItemNotFound):
        rbw.backend().get_secrets(BANK_ID)


def test_get_secrets_errors_never_echo_rbw_output(rbw):
    rbw.write_db()
    rbw.respond(["get", "--raw", "--", GITHUB_ID], stdout=f"{SECRET_MARKER}-partial",
                stderr=f"rbw get: {SECRET_MARKER}-weird\n", rc=1)
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().get_secrets(GITHUB_ID)
    assert SECRET_MARKER not in str(excinfo.value)


def test_get_secrets_with_terminal_only_pinentry_asks_for_a_graphical_one(rbw):
    rbw.write_db()
    stderr = NO_TTY_PINENTRY_STDERR.replace("rbw unlock:", f"rbw get: {SECRET_MARKER}:")
    rbw.respond(["get", "--raw", "--", BANK_ID], stdout=f"{SECRET_MARKER}-partial",
                stderr=stderr, rc=1)
    with pytest.raises(UnlockFailed) as excinfo:
        rbw.backend().get_secrets(BANK_ID)
    assert "rbw config set pinentry pinentry-qt" in (excinfo.value.hint or "")
    assert SECRET_MARKER not in str(excinfo.value)
    assert "Inappropriate ioctl" not in str(excinfo.value)


def test_get_secrets_with_rejected_refresh_token_asks_to_log_in_again(rbw):
    rbw.write_db()
    stderr = EXPIRED_LOGIN_STDERR.replace("rbw sync:", f"rbw get: {SECRET_MARKER}:")
    rbw.respond(["get", "--raw", "--", BANK_ID], stdout=f"{SECRET_MARKER}-partial",
                stderr=stderr, rc=1)
    with pytest.raises(NotLoggedIn) as excinfo:
        rbw.backend().get_secrets(BANK_ID)
    assert "rbw purge" in (excinfo.value.hint or "")
    assert SECRET_MARKER not in str(excinfo.value)


def test_get_secrets_with_cancelled_pinentry_is_still_rbw_get_failed(rbw):
    rbw.write_db()
    rbw.respond(["get", "--raw", "--", BANK_ID], stderr="rbw get: pinentry error: "
                                                        "Operation cancelled <Pinentry>\n", rc=1)
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().get_secrets(BANK_ID)
    assert type(excinfo.value) is BackendError
    assert str(excinfo.value) == "rbw get failed"


def test_get_secrets_invalid_totp_seed_is_secret_free_error(rbw):
    rbw.write_db()
    item = json.loads(fixture("get_raw_login.json"))
    item["data"]["totp"] = f"{SECRET_MARKER}!!"
    rbw.respond(["get", "--raw", "--", GITHUB_ID], json.dumps(item))
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().get_secrets(GITHUB_ID)
    assert SECRET_MARKER not in str(excinfo.value)


# --- create_login / update_password -------------------------------------------

def test_create_login_sends_password_on_stdin(rbw):
    rbw.respond(["add", "--uri", "https://site.test", "--", "Site", "alice"])
    rbw.backend().create_login(name="Site", username="alice", uri="https://site.test",
                               password="QWSECRET-new")
    assert rbw.calls[-1]["argv"] == ["add", "--uri", "https://site.test", "--", "Site", "alice"]
    assert rbw.calls[-1]["stdin"] == "QWSECRET-new\n"


def test_create_login_without_username(rbw):
    rbw.respond(["add", "--uri", "https://site.test", "--", "-Site"])
    rbw.backend().create_login(name="-Site", username=None, uri="https://site.test", password="pw")
    assert rbw.argvs == [["add", "--uri", "https://site.test", "--", "-Site"]]


def test_create_login_failure_is_save_failed(rbw):
    rbw.respond(["add", "--uri", "https://site.test", "--", "Site"],
                stderr="rbw add: failed\n", rc=1)
    with pytest.raises(SaveFailed):
        rbw.backend().create_login(name="Site", username=None, uri="https://site.test",
                                   password="pw")


def test_update_password_keeps_notes_and_sends_both_on_stdin(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], fixture("get_raw_login.json"))
    rbw.respond(["edit", "--", GITHUB_ID])
    rbw.backend().update_password(GITHUB_ID, "QWSECRET-new")
    assert rbw.argvs == [["get", "--raw", "--", GITHUB_ID], ["edit", "--", GITHUB_ID]]
    assert rbw.calls[-1]["stdin"] == "QWSECRET-new\n\nQWSECRET-rbw-note line 1\nline 2"


def test_update_password_without_notes(rbw):
    rbw.respond(["get", "--raw", "--", BANK_ID], fixture("get_raw_reprompt.json"))
    rbw.respond(["edit", "--", BANK_ID])
    rbw.backend().update_password(BANK_ID, "QWSECRET-new")
    assert rbw.calls[-1]["stdin"] == "QWSECRET-new\n"


def test_update_password_refuses_notes_rbw_would_drop(rbw):
    item = json.loads(fixture("get_raw_login.json"))
    item["notes"] = "keep this\n# and this"
    rbw.respond(["get", "--raw", "--", GITHUB_ID], json.dumps(item))
    with pytest.raises(SaveFailed, match="rbw edit"):
        rbw.backend().update_password(GITHUB_ID, "QWSECRET-new")
    assert ["edit", "--", GITHUB_ID] not in rbw.argvs


def test_update_password_rejects_multiline_password(rbw):
    with pytest.raises(SaveFailed):
        rbw.backend().update_password(GITHUB_ID, "a\nb")
    assert rbw.argvs == []


def test_update_password_failure_is_save_failed(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], fixture("get_raw_login.json"))
    rbw.respond(["edit", "--", GITHUB_ID], stderr="rbw edit: failed\n", rc=1)
    with pytest.raises(SaveFailed):
        rbw.backend().update_password(GITHUB_ID, "QWSECRET-new")


# --- security rule 2 ----------------------------------------------------------

def test_no_secret_in_child_arguments_or_environment(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], fixture("get_raw_login.json"))
    rbw.respond(["add", "--uri", "https://site.test", "--", "Site", "alice"])
    rbw.respond(["edit", "--", GITHUB_ID])
    rbw.respond(["list", "--raw"], fixture("list_raw.json"))
    rbw.respond(["unlocked"])
    rbw.write_db()
    backend = rbw.backend()

    backend.status()
    backend.list_logins()
    secrets = backend.get_secrets(GITHUB_ID)
    assert isinstance(secrets, LoginSecrets) and SECRET_MARKER in (secrets.password or "")
    backend.create_login(name="Site", username="alice", uri="https://site.test",
                         password=f"{SECRET_MARKER}-created")
    backend.update_password(GITHUB_ID, f"{SECRET_MARKER}-updated")

    calls = rbw.calls
    assert len(calls) >= 7
    for call in calls:
        assert not any(SECRET_MARKER in arg for arg in call["argv"])
        assert not any(SECRET_MARKER in k or SECRET_MARKER in v for k, v in call["env"].items())
    # Wired: the secrets did travel, through stdin.
    stdins = [c["stdin"] for c in calls]
    assert f"{SECRET_MARKER}-created\n" in stdins
    assert any(s.startswith(f"{SECRET_MARKER}-updated\n") for s in stdins)
