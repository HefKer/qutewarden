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

from qutewarden.backend import make_backend
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
from qutewarden.config import ConfigError
from qutewarden.model import ItemUri, LoginItem, MatchMode, Secrets

FIXTURES = Path(__file__).parent / "fixtures" / "rbw"
GITHUB_ID = "6f1c2d4e-8a3b-4c5d-9e7f-0a1b2c3d4e5f"
BANK_ID = "a2c4e6f8-1b3d-4f5a-9c7e-0d2f4a6b8c1e"
EMAIL = "alice@example.com"
CONFIG_SHOW = json.dumps({"email": EMAIL, "sso_id": None, "base_url": None, "identity_url": None,
                          "ui_url": None, "notifications_url": None, "lock_timeout": 3600,
                          "sync_interval": 3600, "pinentry": "pinentry", "client_cert_path": None})

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

def test_make_backend_builds_rbw_and_rejects_others():
    assert isinstance(make_backend("rbw", {}), RbwBackend)
    with pytest.raises(ConfigError):
        make_backend("bw", {})


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


# --- get_secrets ------------------------------------------------------------

def test_get_secrets_parses_rbw_get_raw_with_one_call(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], fixture("get_raw_login.json"))
    secrets = rbw.backend().get_secrets(GITHUB_ID)
    assert secrets.password == "QWSECRET-rbw-password"
    assert secrets.totp is not None and secrets.totp.isdigit() and len(secrets.totp) == 6
    assert rbw.argvs == [["get", "--raw", "--", GITHUB_ID]]


def test_get_secrets_computes_the_totp_code_from_the_seed(rbw):
    item = json.loads(fixture("get_raw_login.json"))
    item["data"]["totp"] = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # RFC 6238 seed
    rbw.respond(["get", "--raw", "--", GITHUB_ID], json.dumps(item))
    secrets = rbw.backend(clock=lambda: 59.0).get_secrets(GITHUB_ID)
    assert secrets == Secrets(password="QWSECRET-rbw-password", totp="287082")


def test_get_secrets_without_totp_or_password(rbw):
    rbw.respond(["get", "--raw", "--", BANK_ID], fixture("get_raw_reprompt.json"))
    assert rbw.backend().get_secrets(BANK_ID) == Secrets(password="QWSECRET-rbw-bank-password")
    item = json.loads(fixture("get_raw_reprompt.json"))
    item["data"]["password"] = None
    rbw.respond(["get", "--raw", "--", BANK_ID], json.dumps(item))
    assert rbw.backend().get_secrets(BANK_ID) == Secrets()


def test_get_secrets_unknown_item(rbw):
    rbw.respond(["get", "--raw", "--", "nope"],
                stderr="rbw get: couldn't find entry for 'nope': no entry found\n", rc=1)
    with pytest.raises(ItemNotFound):
        rbw.backend().get_secrets("nope")


def test_get_secrets_errors_never_echo_rbw_output(rbw):
    rbw.respond(["get", "--raw", "--", GITHUB_ID], stdout=f"{SECRET_MARKER}-partial",
                stderr=f"rbw get: {SECRET_MARKER}-weird\n", rc=1)
    with pytest.raises(BackendError) as excinfo:
        rbw.backend().get_secrets(GITHUB_ID)
    assert SECRET_MARKER not in str(excinfo.value)


def test_get_secrets_invalid_totp_seed_is_secret_free_error(rbw):
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
    assert SECRET_MARKER in backend.get_secrets(GITHUB_ID).password
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
