"""The built wheel is what the Nix package installs: it must ship the fill JS."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("hatchling")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> zipfile.ZipFile:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    (path,) = out.glob("qutewarden-*.whl")
    with zipfile.ZipFile(path) as zf:
        yield zf


def test_wheel_ships_fill_js_as_package_data(wheel: zipfile.ZipFile) -> None:
    body = wheel.read("qutewarden/js/fill.js").decode()
    assert "function qutewardenFill" in body


def test_wheel_installs_qutewarden_command(wheel: zipfile.ZipFile) -> None:
    (entry_points,) = [n for n in wheel.namelist() if n.endswith(".dist-info/entry_points.txt")]
    assert "qutewarden = qutewarden.cli:main" in wheel.read(entry_points).decode()


def test_wheel_contains_no_tests_or_bytecode(wheel: zipfile.ZipFile) -> None:
    names = wheel.namelist()
    assert not [n for n in names if n.startswith("tests/") or n.endswith(".pyc")]
