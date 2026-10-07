"""Clipboard: copy a secret through stdin, then clear it later in a detached process (#7)."""

from __future__ import annotations

import sys

import pytest

from qutewarden.clipboard import WaylandClipboard, X11Clipboard, detect_clipboard

SECRET = "QWSECRET-totp-github"


def test_wayland_copy_gives_the_value_to_wl_copy_on_stdin(child_recorder):
    WaylandClipboard().copy_secret(SECRET, clear_after=30)
    copy = child_recorder.children[0]
    assert copy.argv == ["wl-copy", "--sensitive", "--trim-newline"]
    assert copy.stdin == [SECRET]


def test_x11_copy_gives_the_value_to_xclip_on_stdin(child_recorder):
    X11Clipboard().copy_secret(SECRET, clear_after=30)
    copy = child_recorder.children[0]
    assert copy.argv == ["xclip", "-selection", "clipboard"]
    assert copy.stdin == [SECRET]


@pytest.mark.parametrize("clipboard, kind", [(WaylandClipboard(), "wayland"),
                                             (X11Clipboard(), "x11")])
def test_copy_starts_a_detached_clearer_that_gets_the_value_on_stdin(
        child_recorder, clipboard, kind):
    clipboard.copy_secret(SECRET, clear_after=45)
    clearer = child_recorder.children[1]
    assert clearer.argv == [sys.executable, "-m", "qutewarden.clipboard_clear", kind, "45"]
    assert clearer.stdin == [SECRET]


def test_the_secret_is_never_in_argv_or_environment(child_recorder):
    WaylandClipboard().copy_secret(SECRET, clear_after=30)
    X11Clipboard().copy_secret(SECRET, clear_after=30)
    for child in child_recorder.children:
        assert not any(SECRET in a for a in child.argv)
        assert not any(SECRET in v for v in child.env.values())


@pytest.fixture
def bin_dir(tmp_path):
    def make(*names: str) -> str:
        for name in names:
            tool = tmp_path / name
            tool.write_text("#!/bin/sh\n")
            tool.chmod(0o755)
        return str(tmp_path)
    return make


def test_detect_prefers_wayland_when_wl_copy_is_available(bin_dir):
    path = bin_dir("wl-copy", "wl-paste", "xclip")
    clipboard = detect_clipboard({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0", "PATH": path})
    assert isinstance(clipboard, WaylandClipboard)


def test_detect_uses_xclip_on_x11(bin_dir):
    path = bin_dir("xclip")
    assert isinstance(detect_clipboard({"DISPLAY": ":0", "PATH": path}), X11Clipboard)


def test_detect_falls_back_to_xclip_on_wayland_without_wl_copy(bin_dir):
    path = bin_dir("xclip")
    clipboard = detect_clipboard({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0", "PATH": path})
    assert isinstance(clipboard, X11Clipboard)


@pytest.mark.parametrize("environ", [
    {},  # no display at all
    {"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"},  # display but no tools on PATH
])
def test_detect_finds_nothing(bin_dir, environ):
    assert detect_clipboard({**environ, "PATH": bin_dir()}) is None
