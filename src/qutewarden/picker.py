"""The picker: a dmenu-compatible menu program (fuzzel, rofi, wofi, bemenu, dmenu).

Lines go to the program's stdin, the chosen line comes back on stdout. A
non-zero exit or empty output means the user dismissed it. Lines only ever
carry Item names, usernames, URIs and origins, never secrets.
"""

from __future__ import annotations

import os
import subprocess
import unicodedata
from collections.abc import Mapping, Sequence
from typing import Protocol

from qutewarden import proc
from qutewarden.errors import QutewardenError

_DASH_P = frozenset({"rofi", "dmenu", "wofi", "bemenu"})

# fuzzel's --width is in characters. We always pass one, so a small width in
# fuzzel.ini can't cut a line off; the floor keeps short confirmations from
# looking cramped, and the cap keeps one huge line from asking for a window
# wider than any screen.
_FUZZEL_MIN_WIDTH = 60
_FUZZEL_MAX_WIDTH = 160


class Picker(Protocol):
    def choose(self, prompt: str, lines: Sequence[str]) -> int | None:
        """Index of the chosen line, None if cancelled."""
        ...

    def ask_text(self, prompt: str) -> str | None:
        """Free text typed by the user, None if cancelled."""
        ...

    def confirm(self, prompt: str, details: Sequence[str] = ()) -> bool:
        """Show ``details`` then "Yes" and "No"; True only for "Yes"."""
        ...


def detect_picker_argv(environ: Mapping[str, str]) -> tuple[str, ...]:
    """fuzzel on Wayland, rofi otherwise (X11)."""
    if environ.get("WAYLAND_DISPLAY"):
        return ("fuzzel", "--dmenu")
    return ("rofi", "-dmenu")


class DmenuPicker:
    def __init__(self, argv: Sequence[str]) -> None:
        self.argv = tuple(argv)

    def choose(self, prompt: str, lines: Sequence[str]) -> int | None:
        shown = _unique([_one_line(line) for line in lines])
        answer = self._run(prompt, shown)
        if answer is None:
            return None
        try:
            return shown.index(answer)
        except ValueError:
            return None

    def ask_text(self, prompt: str) -> str | None:
        return self._run(prompt, [])

    def confirm(self, prompt: str, details: Sequence[str] = ()) -> bool:
        lines = [*(_one_line(d) for d in details), "Yes", "No"]
        width = _fuzzel_width_args(self.argv, [f"{prompt}: ", *lines])
        return self._run(prompt, lines, width) == "Yes"

    def _run(self, prompt: str, lines: Sequence[str],
             extra_args: Sequence[str] = ()) -> str | None:
        """Show ``lines``; return the answer without its newline, or None if cancelled."""
        argv = [*self.argv, *_prompt_args(self.argv[0], prompt), *extra_args]
        stdin = "".join(line + "\n" for line in lines)
        try:
            result = proc.run(argv, input=stdin, check=False)
        except OSError as e:
            raise QutewardenError(f"can't run the picker {self.argv[0]!r}: {e.strerror}; "
                                  "set `picker` in the config") from None
        except subprocess.SubprocessError:
            return None
        answer = result.stdout.rstrip("\r\n")
        if result.returncode != 0 or not answer:
            return None
        return answer


def _prompt_args(program: str, prompt: str) -> list[str]:
    name = os.path.basename(program)
    if name == "fuzzel":
        return [f"--prompt={prompt}: "]
    if name in _DASH_P:
        return ["-p", prompt]
    return []


def _fuzzel_width_args(argv: Sequence[str], shown: Sequence[str]) -> list[str]:
    """fuzzel's --width, wide enough that no line ``shown`` (prompt included) is cut off.

    At least _FUZZEL_MIN_WIDTH, at most _FUZZEL_MAX_WIDTH. Nothing for other
    programs, or if the user's argv already sets a width.
    """
    if os.path.basename(argv[0]) != "fuzzel" or any(
            a == "--width" or a.startswith(("-w", "--width=")) for a in argv[1:]):
        return []
    needed = max(_columns(line) for line in shown)
    return [f"--width={min(max(needed, _FUZZEL_MIN_WIDTH), _FUZZEL_MAX_WIDTH)}"]


def _columns(text: str) -> int:
    """Terminal-style display width: wide (CJK, emoji) characters take two columns."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _one_line(text: str) -> str:
    return " ".join(text.replace("\r", "\n").split("\n"))


def _unique(lines: Sequence[str]) -> list[str]:
    """Number repeated lines " (2)", " (3)", ... so each maps back to one index."""
    seen: set[str] = set()
    out = []
    for line in lines:
        candidate, n = line, 1
        while candidate in seen:
            n += 1
            candidate = f"{line} ({n})"
        seen.add(candidate)
        out.append(candidate)
    return out
