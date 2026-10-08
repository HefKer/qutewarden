"""`unlock`, `lock`, `sync`, `status`: thin wrappers around the Backend (#10)."""

import shlex
import time
from pathlib import Path

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.base import (
    BackendError,
    BackendUnavailable,
    NotLoggedIn,
    UnlockFailed,
)
from qutewarden.backend.fake import FakeBackend
from qutewarden.context import Context
from qutewarden.qute import Qute


@pytest.fixture(autouse=True)
def utc(monkeypatch):
    """Show times in UTC so the expected messages don't depend on the machine."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


@pytest.fixture
def environ(tmp_path: Path) -> dict[str, str]:
    fifo = tmp_path / "fifo"
    fifo.write_text("")
    return {
        "QUTE_URL": "https://github.com/login",
        "QUTE_FIFO": str(fifo),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "HOME": str(tmp_path / "home"),
    }


def run(name: str, backend: FakeBackend, environ: dict[str, str]) -> tuple[int, list[list[str]]]:
    """Run subcommand ``name`` against ``backend``; return exit code and FIFO lines."""

    def make_context(config, env) -> Context:
        return Context(
            config=config, environ=env, qute=Qute.from_environ(env), backend=backend,
            picker=FakePicker(), clipboard=None,
            runtime_dir=Path(env["XDG_RUNTIME_DIR"]) / "qutewarden",
            cache_dir=Path(env["XDG_CACHE_HOME"]) / "qutewarden",
            generate_password=lambda cfg: "QWSECRET-generated",
        )

    code = cli.main([name], environ=environ, make_context=make_context)
    lines = Path(environ["QUTE_FIFO"]).read_text().splitlines()
    return code, [shlex.split(line) for line in lines]


def test_status_shows_unlocked_and_last_sync(environ):
    code, lines = run("status", FakeBackend(unlocked=True), environ)
    assert code == 0
    assert lines == [["message-info",
                      "qutewarden: vault unlocked, last sync 2026-01-02 03:04"]]


def test_status_shows_locked(environ):
    code, lines = run("status", FakeBackend(unlocked=False), environ)
    assert code == 0
    assert lines == [["message-info", "qutewarden: vault locked, last sync 2026-01-02 03:04"]]


def test_status_without_a_known_last_sync(environ):
    backend = FakeBackend(unlocked=False, logged_in=False)
    code, lines = run("status", backend, environ)
    assert code == 0
    assert lines == [["message-info", "qutewarden: vault locked, last sync unknown"]]


def test_unlock_unlocks_a_locked_vault(environ):
    backend = FakeBackend(unlocked=False)
    code, lines = run("unlock", backend, environ)
    assert code == 0
    assert backend.unlocked
    assert lines == [["message-info", "qutewarden: vault unlocked"]]


class FailingBackend(FakeBackend):
    """A FakeBackend whose every vault-control call raises ``error``."""

    def __init__(self, error: BackendError) -> None:
        super().__init__(unlocked=False)
        self.error = error

    def unlock(self):
        raise self.error

    def lock(self):
        raise self.error

    def sync(self):
        raise self.error

    def status(self):
        raise self.error


@pytest.mark.parametrize("name", ["unlock", "lock", "sync", "status"])
@pytest.mark.parametrize("error, expected", [
    (NotLoggedIn("rbw isn't logged in", hint="run `rbw login`"),
     "qutewarden: rbw isn't logged in (run `rbw login`)"),
    (BackendUnavailable("can't run rbw", hint="install rbw >= 1.15"),
     "qutewarden: can't run rbw (install rbw >= 1.15)"),
    (UnlockFailed("rbw couldn't unlock the vault"),
     "qutewarden: rbw couldn't unlock the vault"),
])
def test_backend_errors_become_a_message_error_saying_what_to_do(name, error, expected, environ):
    code, lines = run(name, FailingBackend(error), environ)
    assert code == 1
    assert lines == [["message-error", expected]]


def test_unlock_without_login_tells_the_user_to_log_in(environ):
    code, lines = run("unlock", FakeBackend(unlocked=False, logged_in=False), environ)
    assert code == 1
    assert lines == [["message-error",
                      "qutewarden: not logged in (log in to the fake backend)"]]


def test_lock_locks_an_unlocked_vault(environ):
    backend = FakeBackend(unlocked=True)
    code, lines = run("lock", backend, environ)
    assert code == 0
    assert not backend.unlocked
    assert lines == [["message-info", "qutewarden: vault locked"]]


def test_sync_syncs_the_vault(environ):
    backend = FakeBackend(unlocked=True)
    code, lines = run("sync", backend, environ)
    assert code == 0
    assert backend.calls == ["sync"]
    assert lines == [["message-info", "qutewarden: vault synced"]]
