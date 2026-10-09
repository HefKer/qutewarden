"""Fixtures of the e2e suite (ADR-0007): one isolated stack per session.

``stack`` starts, in order: the session root under ``/tmp``, Vaultwarden
(account registered, Items seeded), rbw logged in with the scripted
pinentry, headless sway and Xvfb, the test page server and qutebrowser.
When the session ends it stops qutebrowser and runs the no-leak scan, which
fails the run if any marker turned up. Tests use the function-scoped
fixtures below, which reset what one test may leave behind.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from e2e import harness, items, seed
from e2e.harness import (
    Dirs,
    Displays,
    PageServer,
    Picker,
    Pinentry,
    ProcSampler,
    Qutebrowser,
    Rbw,
    Vaultwarden,
)


@dataclass
class Stack:
    dirs: Dirs
    markers: items.Markers
    vault: items.SeededVault
    rbw: Rbw
    pinentry: Pinentry
    picker: Picker
    displays: Displays
    pages: PageServer
    qb: Qutebrowser
    sampler: ProcSampler


def _write_qutewarden_config(dirs: Dirs, picker: Picker) -> None:
    config = dirs.home / ".config" / "qutewarden" / "config.toml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        f'picker = ["{picker.path}"]\n'
        f"[totp]\nclipboard_clear_seconds = {harness.CLEAR_SECONDS}\n"
        f"[vault]\ncopy_clear_seconds = {harness.CLEAR_SECONDS}\n")


def _qutebrowser_settings() -> list[tuple[str, str]]:
    # CI only, if lifting the user-namespace restriction isn't enough (spec-v2 "Testing").
    if os.environ.get("QW_E2E_NO_SANDBOX"):
        return [("qt.chromium.sandboxing", "disable-all")]
    return []


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    dirs = Dirs(Path(tempfile.mkdtemp(prefix="qw", dir="/tmp")))
    dirs.make()
    markers = items.Markers()
    master_password = markers.secret("master")
    stops = []
    try:
        server = Vaultwarden(dirs)
        stops.append(server.stop)
        seed.register(server.url, harness.EMAIL, master_password)
        vault = items.build(markers)
        items.seed(seed.VaultClient(server.url, harness.EMAIL, master_password), vault, markers)

        pinentry = Pinentry(dirs, master_password)
        picker = Picker(dirs)
        rbw = Rbw(harness.isolated_environ(dirs))
        stops.append(rbw.stop)
        rbw.setup(server.url, pinentry.path)

        displays = Displays(dirs)
        stops.append(displays.stop)
        pages = PageServer()
        stops.append(pages.stop)
        _write_qutewarden_config(dirs, picker)
        sampler = ProcSampler()
        stops.append(sampler.stop)
        qb = Qutebrowser(dirs, harness.isolated_environ(dirs, displays.environ()), pages.port,
                         extra_settings=_qutebrowser_settings())
        stops.append(qb.stop)
        yield Stack(dirs, markers, vault, rbw, pinentry, picker, displays, pages, qb, sampler)

        qb.stop()
        sampler.stop()
        hits = harness.leak_scan(markers.all(), markers.codes(), log=qb.log_path,
                                 basedir=qb.basedir, runtime_dir=dirs.runtime / "qutewarden",
                                 samples=sampler.blobs)
        if hits:
            pytest.fail("no-leak scan found secrets:\n" + "\n".join(hits), pytrace=False)
    finally:
        for stop in reversed(stops):
            stop()
        if not os.environ.get("QW_E2E_KEEP"):
            shutil.rmtree(dirs.root, ignore_errors=True)


@pytest.fixture
def qb(stack: Stack) -> Iterator[Qutebrowser]:
    """qutebrowser with one tab; fails the test if a picker request went unanswered."""
    stack.pinentry.mode = "ok"
    stack.qb.command("tab-only")
    yield stack.qb
    pending = stack.picker.pending()
    assert not pending, f"picker requests never answered: {pending}"


@pytest.fixture
def pages(stack: Stack) -> PageServer:
    return stack.pages


@pytest.fixture
def picker(stack: Stack) -> Picker:
    return stack.picker


@pytest.fixture
def pinentry(stack: Stack) -> Pinentry:
    return stack.pinentry


@pytest.fixture
def rbw(stack: Stack) -> Rbw:
    return stack.rbw


@pytest.fixture
def vault(stack: Stack) -> items.SeededVault:
    return stack.vault


@pytest.fixture
def markers(stack: Stack) -> items.Markers:
    return stack.markers


@pytest.fixture
def displays(stack: Stack) -> Displays:
    return stack.displays


@pytest.fixture
def unlocked(rbw: Rbw, qb: Qutebrowser) -> None:
    """Start the test with the vault unlocked."""
    if not rbw.is_unlocked():
        assert qb.run("unlock").exit_codes == [0]


@pytest.fixture
def locked(rbw: Rbw) -> None:
    """Start the test with the vault locked."""
    rbw.run("lock")
