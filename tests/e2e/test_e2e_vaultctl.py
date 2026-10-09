"""e2e: `unlock`, `lock`, `status` and `sync`."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from e2e.harness import PageServer, Pinentry, Qutebrowser, Rbw

pytestmark = pytest.mark.e2e

STATUS = re.compile(r"qutewarden: vault (locked|unlocked), last sync \d{4}-\d\d-\d\d \d\d:\d\d")


def _db_file(rbw: Rbw) -> Path:
    [path] = (Path(rbw.env["XDG_CACHE_HOME"]) / f"rbw-{rbw.env['RBW_PROFILE']}").glob("*.json")
    return path


def test_lock_locks_the_vault(qb: Qutebrowser, rbw: Rbw, unlocked: None):
    run = qb.run("lock")
    assert run.exit_codes == [0]
    assert ("INFO", "qutewarden: vault locked") in run.messages()
    assert not rbw.is_unlocked()


def test_status_says_locked_and_shows_the_last_sync(qb: Qutebrowser, locked: None):
    [(level, text)] = qb.run("status").messages()
    assert level == "INFO"
    assert STATUS.fullmatch(text)
    assert text.startswith("qutewarden: vault locked, ")


def test_unlock_asks_for_the_master_password_once(qb: Qutebrowser, rbw: Rbw,
                                                   pinentry: Pinentry, locked: None):
    calls = len(pinentry.calls())
    run = qb.run("unlock")
    assert run.exit_codes == [0]
    assert ("INFO", "qutewarden: vault unlocked") in run.messages()
    assert len(pinentry.calls()) == calls + 1
    assert rbw.is_unlocked()
    assert qb.run("status").messages()[0][1].startswith("qutewarden: vault unlocked, ")


def test_unlock_while_unlocked_asks_nothing(qb: Qutebrowser, pinentry: Pinentry,
                                            unlocked: None):
    calls = len(pinentry.calls())
    run = qb.run("unlock")
    assert run.exit_codes == [0]
    assert run.messages() == [("INFO", "qutewarden: vault unlocked")]
    assert len(pinentry.calls()) == calls


def test_sync_refreshes_the_local_copy_of_the_vault(qb: Qutebrowser, rbw: Rbw,
                                                    unlocked: None):
    before = _db_file(rbw).stat().st_mtime_ns
    run = qb.run("sync")
    assert run.exit_codes == [0]
    assert ("INFO", "qutewarden: vault synced") in run.messages()
    assert _db_file(rbw).stat().st_mtime_ns > before


@pytest.mark.parametrize("answer", ["cancel", "wrong"])
def test_failed_unlock_shows_a_readable_error_and_qutebrowser_stays_usable(
        qb: Qutebrowser, pages: PageServer, rbw: Rbw, pinentry: Pinentry, locked: None,
        answer: str):
    pinentry.mode = answer
    run = qb.run("unlock")
    assert run.exit_codes == [1]
    [(level, text)] = run.messages()
    assert level == "ERROR"
    assert text.startswith("qutewarden: ")
    assert "Traceback" not in text
    assert not rbw.is_unlocked()
    qb.open(pages, "http://login.example.com/login_single.html")  # still responsive
