"""The built wheel is what the Nix package installs: it must ship the package data."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("hatchling")

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def wheel(tmp_path_factory: pytest.TempPathFactory) -> Iterator[zipfile.ZipFile]:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run([sys.executable, "-m", "hatchling", "build", "-t", "wheel", "-d", str(out)],
                   cwd=ROOT, check=True, capture_output=True)
    (path,) = out.glob("qutewarden-*.whl")
    with zipfile.ZipFile(path) as zf:
        yield zf


def test_wheel_ships_fill_js_as_package_data(wheel: zipfile.ZipFile) -> None:
    body = wheel.read("qutewarden/js/fill.js").decode()
    assert "function qutewardenFill" in body


def test_wheel_ships_the_global_equivalent_domains_with_their_source_and_licence(
        wheel: zipfile.ZipFile) -> None:
    data = json.loads(wheel.read("qutewarden/equivalent_domains.json"))
    assert data["source"].startswith("https://github.com/bitwarden/server/blob/")
    assert "AGPL-3.0" in data["license"]
    assert ["youtube.com", "google.com", "gmail.com"] in data["groups"]


def test_wheel_installs_qutewarden_command(wheel: zipfile.ZipFile) -> None:
    (entry_points,) = [n for n in wheel.namelist() if n.endswith(".dist-info/entry_points.txt")]
    assert "qutewarden = qutewarden.cli:main" in wheel.read(entry_points).decode()


def test_wheel_contains_no_tests_or_bytecode(wheel: zipfile.ZipFile) -> None:
    names = wheel.namelist()
    assert not [n for n in names if n.startswith("tests/") or n.endswith(".pyc")]
