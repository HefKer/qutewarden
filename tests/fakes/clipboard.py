"""FakeClipboard: records copies in memory instead of touching the real clipboard."""

from __future__ import annotations


class FakeClipboard:
    """Stands in for ``qutewarden.clipboard.Clipboard``."""

    def __init__(self) -> None:
        self.copies: list[tuple[str, int]] = []  # (value, clear_after)

    def copy_secret(self, value: str, *, clear_after: int) -> None:
        self.copies.append((value, clear_after))
