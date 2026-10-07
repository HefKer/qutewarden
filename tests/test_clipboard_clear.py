"""The detached clearer: wait, then clear the clipboard only if it still holds the value (#7)."""

from __future__ import annotations

import io
import subprocess

import pytest

from qutewarden import clipboard_clear, proc

SECRET = "QWSECRET-totp-github"


class SystemClipboard:
    """Stands in for wl-copy/wl-paste/xclip behind ``proc``; holds the clipboard text."""

    def __init__(self, contents: str) -> None:
        self.contents = contents
        self.argvs: list[list[str]] = []
        self.events: list[str] = []

    def run(self, argv, *, input=None, timeout=None, check=True):
        argv = list(argv)
        self.argvs.append(argv)
        if argv in (["wl-paste", "--no-newline"], ["xclip", "-selection", "clipboard", "-o"]):
            self.events.append("read")
            return subprocess.CompletedProcess(argv, 0, self.contents, "")
        if argv == ["wl-copy", "--clear"]:
            self.events.append("clear")
            self.contents = ""
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise AssertionError(f"unexpected run {argv}")

    def spawn_detached(self, argv, *, input=None):
        argv = list(argv)
        self.argvs.append(argv)
        assert argv == ["xclip", "-selection", "clipboard"], argv
        self.events.append("clear")
        self.contents = input


@pytest.fixture
def system(monkeypatch):
    def make(contents: str) -> SystemClipboard:
        fake = SystemClipboard(contents)
        monkeypatch.setattr(proc, "run", fake.run)
        monkeypatch.setattr(proc, "spawn_detached", fake.spawn_detached)
        return fake
    return make


def clear(kind: str, seconds: str, value: str = SECRET, slept: list | None = None,
          events: list | None = None) -> int:
    def sleep(s):
        if slept is not None:
            slept.append(s)
        if events is not None:
            events.append("sleep")
    return clipboard_clear.main([kind, seconds], stdin=io.StringIO(value), sleep=sleep)


@pytest.mark.parametrize("kind", ["wayland", "x11"])
def test_the_clipboard_is_cleared_after_the_wait_if_it_still_holds_the_value(system, kind):
    fake = system(SECRET)
    slept: list = []
    assert clear(kind, "30", slept=slept, events=fake.events) == 0
    assert slept == [30]
    assert fake.events == ["sleep", "read", "clear"]
    assert fake.contents == ""


@pytest.mark.parametrize("kind", ["wayland", "x11"])
def test_something_the_user_copied_since_is_left_alone(system, kind):
    fake = system("something the user copied")
    assert clear(kind, "30") == 0
    assert "clear" not in fake.events
    assert fake.contents == "something the user copied"


def test_the_value_never_appears_in_an_argv(system):
    fake = system(SECRET)
    clear("wayland", "1")
    clear("x11", "1")
    assert fake.argvs
    assert not any(SECRET in a for argv in fake.argvs for a in argv)


def test_a_failing_read_clears_nothing(system, monkeypatch):
    fake = system(SECRET)

    def broken(argv, **kw):
        raise OSError("wl-paste is gone")
    monkeypatch.setattr(proc, "run", broken)
    assert clear("wayland", "1") == 1
    assert fake.contents == SECRET


@pytest.mark.parametrize("argv", [[], ["wayland"], ["beos", "30"], ["wayland", "soon"]])
def test_bad_arguments_exit_2_without_touching_the_clipboard(system, argv):
    fake = system(SECRET)
    assert clipboard_clear.main(argv, stdin=io.StringIO(SECRET), sleep=lambda s: None) == 2
    assert fake.argvs == []
