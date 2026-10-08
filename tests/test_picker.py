"""DmenuPicker and picker auto-detection (#6), against fake dmenu-style programs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from qutewarden.picker import DmenuPicker, detect_picker_argv

FAKE_MENU = """\
import json, sys
from pathlib import Path
here = Path(__file__).parent
stdin = sys.stdin.read()
log = here / "calls.json"
calls = json.loads(log.read_text()) if log.exists() else []
calls.append({"argv": sys.argv[1:], "stdin": stdin})
log.write_text(json.dumps(calls))
answer = json.loads((here / "answer.json").read_text())
sys.stdout.write(answer["out"])
sys.exit(answer["code"])
"""


class FakeMenu:
    """A dmenu-compatible program named ``name`` that prints a scripted answer."""

    def __init__(self, tmp_path: Path, name: str) -> None:
        self.dir = tmp_path / name
        self.dir.mkdir()
        self.path = self.dir / name
        self.path.write_text(f"#!{sys.executable}\n{FAKE_MENU}")
        self.path.chmod(0o755)
        self.answer("", 0)

    def answer(self, out: str, code: int = 0) -> None:
        (self.dir / "answer.json").write_text(json.dumps({"out": out, "code": code}))

    @property
    def calls(self) -> list[dict]:
        log = self.dir / "calls.json"
        return json.loads(log.read_text()) if log.exists() else []


@pytest.fixture
def fuzzel(tmp_path):
    return FakeMenu(tmp_path, "fuzzel")


def test_choose_returns_the_index_of_the_chosen_line(fuzzel):
    fuzzel.answer("GitHub (work) — alice-work\n")
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    assert picker.choose("Fill", ["GitHub — alice", "GitHub (work) — alice-work"]) == 1
    [call] = fuzzel.calls
    assert call["stdin"] == "GitHub — alice\nGitHub (work) — alice-work\n"


@pytest.mark.parametrize("out, code", [("", 1), ("", 0), ("something else\n", 0),
                                       ("GitHub — alice\n", 2)])
def test_a_dismissed_or_unknown_answer_is_cancelled(fuzzel, out, code):
    fuzzel.answer(out, code)
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    assert picker.choose("Fill", ["GitHub — alice"]) is None


def test_duplicate_lines_are_numbered_so_each_maps_back(fuzzel):
    fuzzel.answer("GitHub — alice (2)\n")
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    assert picker.choose("Fill", ["GitHub — alice", "GitHub — alice", "Other"]) == 1
    assert fuzzel.calls[0]["stdin"] == "GitHub — alice\nGitHub — alice (2)\nOther\n"


def test_newlines_in_lines_are_stripped(fuzzel):
    fuzzel.answer("Evil name — bob\n")
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    assert picker.choose("Fill", ["Evil\nname — bob"]) == 0
    assert fuzzel.calls[0]["stdin"] == "Evil name — bob\n"


@pytest.mark.parametrize("name, prompt_args", [
    ("fuzzel", ["--prompt=Fill: "]),
    ("rofi", ["-p", "Fill"]),
    ("dmenu", ["-p", "Fill"]),
    ("wofi", ["-p", "Fill"]),
    ("bemenu", ["-p", "Fill"]),
    ("somethingelse", []),
])
def test_the_prompt_flag_depends_on_the_program(tmp_path, name, prompt_args):
    menu = FakeMenu(tmp_path, name)
    DmenuPicker([str(menu.path), "--x"]).choose("Fill", ["a"])
    assert menu.calls[0]["argv"] == ["--x", *prompt_args]


def test_ask_text_returns_what_the_user_typed(fuzzel):
    fuzzel.answer("alice@example.com\n")
    assert DmenuPicker([str(fuzzel.path), "--dmenu"]).ask_text("Username") == "alice@example.com"
    assert fuzzel.calls[0]["stdin"] == ""


def test_ask_text_cancelled(fuzzel):
    fuzzel.answer("", 1)
    assert DmenuPicker([str(fuzzel.path), "--dmenu"]).ask_text("Username") is None


@pytest.mark.parametrize("out, expected", [("Yes\n", True), ("No\n", False), ("", False),
                                           ("https://github.com\n", False)])
def test_confirm_shows_details_then_yes_and_no(fuzzel, out, expected):
    fuzzel.answer(out)
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    assert picker.confirm("Fill anyway?", ["https://github.com"]) is expected
    assert fuzzel.calls[0]["stdin"] == "https://github.com\nYes\nNo\n"


LONG = "Item: www.365chess.com.evil.example /signup.php?ref=a-rather-long-query-string"


def _width(argv: list[str]) -> int | None:
    widths = [int(a.removeprefix("--width=")) for a in argv if a.startswith("--width=")]
    assert len(widths) <= 1
    return widths[0] if widths else None


def test_confirm_widens_fuzzel_to_fit_the_longest_line(fuzzel):
    DmenuPicker([str(fuzzel.path), "--dmenu"]).confirm("Fill X (x)?", ["Page: a.test", LONG])
    assert _width(fuzzel.calls[0]["argv"]) >= len(LONG)


def test_confirm_widens_fuzzel_to_fit_a_long_prompt(fuzzel):
    prompt = "Fill A rather long Item name (someone@example.com)?"
    DmenuPicker([str(fuzzel.path), "--dmenu"]).confirm(prompt, ["Page: a.test"])
    assert _width(fuzzel.calls[0]["argv"]) >= len(f"{prompt}: ")


def test_confirm_caps_the_fuzzel_width(fuzzel):
    DmenuPicker([str(fuzzel.path), "--dmenu"]).confirm("Fill?", ["Item: " + "a" * 1000])
    assert 80 <= _width(fuzzel.calls[0]["argv"]) < 1000


def test_confirm_leaves_fuzzels_default_width_for_short_lines(fuzzel):
    DmenuPicker([str(fuzzel.path), "--dmenu"]).confirm("Fill?", ["Page: a.test"])
    assert _width(fuzzel.calls[0]["argv"]) is None


@pytest.mark.parametrize("user_width", [["--width=40"], ["--width", "40"], ["-w", "40"], ["-w40"]])
def test_confirm_keeps_a_width_the_user_set_for_fuzzel(fuzzel, user_width):
    DmenuPicker([str(fuzzel.path), "--dmenu", *user_width]).confirm("Fill?", [LONG])
    assert fuzzel.calls[0]["argv"] == ["--dmenu", *user_width, "--prompt=Fill?: "]


@pytest.mark.parametrize("name", ["rofi", "dmenu", "wofi", "bemenu", "somethingelse"])
def test_confirm_adds_no_width_for_other_pickers(tmp_path, name):
    menu = FakeMenu(tmp_path, name)
    DmenuPicker([str(menu.path)]).confirm("Fill?", [LONG])
    assert not any("width" in a or a == "-w" for a in menu.calls[0]["argv"])


def test_choose_and_ask_text_add_no_width(fuzzel):
    picker = DmenuPicker([str(fuzzel.path), "--dmenu"])
    picker.choose("Vault", [LONG])
    picker.ask_text("Username " + LONG)
    assert [_width(call["argv"]) for call in fuzzel.calls] == [None, None]


def test_a_missing_picker_program_is_a_user_facing_error(tmp_path):
    from qutewarden.errors import QutewardenError
    picker = DmenuPicker([str(tmp_path / "no-such-menu"), "--dmenu"])
    with pytest.raises(QutewardenError, match="picker"):
        picker.choose("Fill", ["a"])


@pytest.mark.parametrize("environ, argv", [
    ({"WAYLAND_DISPLAY": "wayland-1", "DISPLAY": ":0"}, ("fuzzel", "--dmenu")),
    ({"WAYLAND_DISPLAY": "wayland-1"}, ("fuzzel", "--dmenu")),
    ({"DISPLAY": ":0"}, ("rofi", "-dmenu")),
    ({}, ("rofi", "-dmenu")),
])
def test_detect_picker_argv(environ, argv):
    assert detect_picker_argv(environ) == argv
