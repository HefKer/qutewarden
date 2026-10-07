"""FakePicker: answers picker prompts from a script and records what it was shown."""

from __future__ import annotations

from collections.abc import Sequence


class FakePicker:
    """Stands in for ``qutewarden.picker.Picker``.

    ``choose`` returns the next entry of ``choices`` (an index, or None to
    cancel), then index 0 once they run out. If ``prefer`` is set, a line
    containing it (case-insensitive) wins over both.
    """

    def __init__(self, choices: Sequence[int | None] = (), *, confirm: bool = True,
                 text: str | None = "alice", prefer: str | None = None) -> None:
        self.choices = list(choices)
        self.confirm_answer = confirm
        self.text = text
        self.prefer = prefer
        self.prompts: list[str] = []
        self.lines: list[list[str]] = []

    def choose(self, prompt: str, lines: Sequence[str]) -> int | None:
        self.prompts.append(prompt)
        self.lines.append(list(lines))
        if self.prefer is not None:
            for i, line in enumerate(lines):
                if self.prefer.lower() in line.lower():
                    return i
        if self.choices:
            return self.choices.pop(0)
        return 0 if lines else None

    def ask_text(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        return self.text

    def confirm(self, prompt: str, details: Sequence[str] = ()) -> bool:
        self.prompts.append(prompt)
        self.lines.append([*details, "Yes", "No"])
        return self.confirm_answer
