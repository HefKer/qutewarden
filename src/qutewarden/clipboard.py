"""Copy a secret to the clipboard and clear it again later (Security rule 4).

The value reaches the clipboard tool (wl-copy or xclip) through stdin only,
never argv or the environment (Security rule 2). Each copy also starts a
detached ``python -m qutewarden.clipboard_clear`` that waits, then clears the
clipboard only if it still holds the value, so a later copy by the user is
left alone. Used by `totp` (``totp.clipboard``) and `vault` (``vault.allow_copy``).
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Mapping
from typing import ClassVar, Protocol

from qutewarden import proc

# kind (argv[1] of the clearer) -> argv that puts stdin on the clipboard
COPY_ARGV: dict[str, tuple[str, ...]] = {
    "wayland": ("wl-copy", "--sensitive", "--trim-newline"),
    "x11": ("xclip", "-selection", "clipboard"),
}


class Clipboard(Protocol):
    def copy_secret(self, value: str, *, clear_after: int) -> None:
        """Put ``value`` on the clipboard; clear it after ``clear_after`` seconds."""


class _ToolClipboard:
    kind: ClassVar[str]

    def copy_secret(self, value: str, *, clear_after: int) -> None:
        # wl-copy and xclip keep running to serve the selection, so they're
        # detached rather than waited for.
        proc.spawn_detached(COPY_ARGV[self.kind], input=value)
        proc.spawn_detached([sys.executable, "-m", "qutewarden.clipboard_clear",
                             self.kind, str(int(clear_after))], input=value)


class WaylandClipboard(_ToolClipboard):
    kind = "wayland"


class X11Clipboard(_ToolClipboard):
    kind = "x11"


def detect_clipboard(environ: Mapping[str, str]) -> Clipboard | None:
    """wl-copy on Wayland, else xclip on X11; None if neither is usable."""
    path = environ.get("PATH")
    if (environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy", path=path)
            and shutil.which("wl-paste", path=path)):
        return WaylandClipboard()
    if environ.get("DISPLAY") and shutil.which("xclip", path=path):
        return X11Clipboard()
    return None
