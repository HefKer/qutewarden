"""Detached clipboard clearer: ``python -m qutewarden.clipboard_clear KIND SECONDS``.

Started by ``qutewarden.clipboard`` after each copy, in its own session, with
the copied value on stdin (never argv). It waits ``SECONDS``, reads the
clipboard and clears it only if it still holds that value, so anything the
user copied in the meantime is left alone. Prints nothing.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from typing import TextIO

from qutewarden import proc

PASTE_ARGV: dict[str, tuple[str, ...]] = {
    "wayland": ("wl-paste", "--no-newline"),
    "x11": ("xclip", "-selection", "clipboard", "-o"),
}


def main(argv: Sequence[str] | None = None, *, stdin: TextIO | None = None,
         sleep: Callable[[float], None] = time.sleep) -> int:
    """Clear the clipboard if it still holds the value; return the exit code.

    0 when done (cleared or left alone), 1 if the clipboard couldn't be read, 2 on bad args.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2 or args[0] not in PASTE_ARGV or not args[1].isdigit():
        return 2
    kind, seconds = args[0], int(args[1])
    value = (sys.stdin if stdin is None else stdin).read()
    sleep(seconds)
    try:
        current = proc.run(PASTE_ARGV[kind], timeout=5, check=False).stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        return 1
    if current != value:
        return 0
    if kind == "wayland":
        proc.run(["wl-copy", "--clear"], timeout=5, check=False)
    else:
        # xclip stays running to own the selection, so don't wait for it.
        proc.spawn_detached(["xclip", "-selection", "clipboard"], input="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
