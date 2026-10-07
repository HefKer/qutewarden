"""`unlock`, `lock`, `sync`, `status`: thin wrappers around the Backend (#10)."""

import shlex
import time
from pathlib import Path

import pytest

from qutewarden import cli
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
            picker=None, clipboard=None,
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
