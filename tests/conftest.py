from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from fakes.children import ChildRecorder
from fakes.clipboard import FakeClipboard
from fakes.picker import FakePicker
from fakes.qutebrowser import FakeQutebrowser

from qutewarden.backend.fake import FakeBackend
from qutewarden.config import load_config
from qutewarden.context import Context
from qutewarden.match import make_suffix_extractor
from qutewarden.qute import Qute


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--e2e", action="store_true",
                     help="also run the e2e suite in tests/e2e (ADR-0007)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the e2e tests unless --e2e is given."""
    if config.getoption("--e2e"):
        return
    e2e = [item for item in items if item.get_closest_marker("e2e")]
    if e2e:
        config.hook.pytest_deselected(items=e2e)
        items[:] = [item for item in items if not item.get_closest_marker("e2e")]


@pytest.fixture
def fake_qutebrowser(tmp_path: Path) -> Iterator[FakeQutebrowser]:
    qb = FakeQutebrowser(tmp_path)
    yield qb
    qb.close()


@pytest.fixture
def fake_backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def fake_picker() -> FakePicker:
    return FakePicker()


@pytest.fixture
def fake_clipboard() -> FakeClipboard:
    return FakeClipboard()


@pytest.fixture
def child_recorder(monkeypatch: pytest.MonkeyPatch) -> ChildRecorder:
    """Record (instead of start) every child process."""
    recorder = ChildRecorder()
    monkeypatch.setattr(subprocess, "Popen", recorder.popen)
    return recorder


@pytest.fixture
def qute_environ(tmp_path: Path, fake_qutebrowser: FakeQutebrowser) -> dict[str, str]:
    """A userscript environment: QUTE_* from the fake qutebrowser, XDG dirs under tmp_path."""
    run = tmp_path / "run"
    run.mkdir(mode=0o700)
    html = tmp_path / "qute_html"
    html.write_text("<html><body></body></html>")
    return {
        **fake_qutebrowser.environ(),
        "QUTE_HTML": str(html),
        "XDG_RUNTIME_DIR": str(run),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "HOME": str(tmp_path / "home"),
    }


@pytest.fixture
def ctx(qute_environ: dict[str, str], fake_backend: FakeBackend, fake_picker: FakePicker,
        fake_clipboard: FakeClipboard) -> Context:
    """A Context of fakes with default settings."""
    return Context(
        config=load_config(None, {}),
        environ=qute_environ,
        qute=Qute.from_environ(qute_environ),
        backend=fake_backend,
        picker=fake_picker,
        clipboard=fake_clipboard,
        runtime_dir=Path(qute_environ["XDG_RUNTIME_DIR"]) / "qutewarden",
        cache_dir=Path(qute_environ["XDG_CACHE_HOME"]) / "qutewarden",
        generate_password=lambda config: "QWSECRET-generated",
        fill_timeout=2.0,
        suffix_extractor=make_suffix_extractor(Path(qute_environ["XDG_CACHE_HOME"]), offline=True),
    )
