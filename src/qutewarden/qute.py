"""Talking to qutebrowser: read QUTE_URL, write commands to QUTE_FIFO.

qutebrowser reads QUTE_FIFO line by line, splits each line on ``;;`` before
looking at quoting, lexes arguments shell-style and then substitutes
``{url}``, ``{clipboard}``, ... in every argument. Free text (Item names,
usernames) therefore goes through ``sanitize_message`` and ``quote_arg``.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path

from qutewarden.errors import QutewardenError

FILL_WORLD_ID = 213  # dedicated isolated JS world for every jseval we send (<= 256)

MESSAGE_PREFIX = "qutewarden: "

# Variables qutebrowser substitutes in command arguments (commands/runners.py).
_QUTE_VARIABLES = (
    "url", "url:pretty", "url:domain", "url:auth", "url:scheme", "url:username",
    "url:password", "url:host", "url:port", "url:path", "url:query", "url:yank",
    "title", "clipboard", "primary",
)
_VARIABLE_RE = re.compile("{(" + "|".join(re.escape(v) for v in _QUTE_VARIABLES) + ")}")


def sanitize_message(text: str) -> str:
    """Make free text safe to embed as one qutebrowser command argument.

    Drops CR/LF (one command per line), breaks up ``;;`` (command separator)
    and escapes ``{var}`` substitutions as ``{{var}}`` (qutebrowser turns that
    back into the literal ``{var}``).
    """
    text = text.replace("\r", "").replace("\n", "")
    while ";;" in text:
        text = text.replace(";;", "; ;")
    return _VARIABLE_RE.sub(r"{{\1}}", text)


def quote_arg(text: str) -> str:
    """Quote one argument; qutebrowser's shell-style lexer accepts shlex quoting."""
    return shlex.quote(text)


class Qute:
    """The qutebrowser side of a userscript run."""

    def __init__(self, url: str | None, fifo_path: Path | None) -> None:
        self.url = url
        self.fifo_path = fifo_path

    @classmethod
    def from_environ(cls, environ: Mapping[str, str]) -> Qute:
        url = environ.get("QUTE_URL") or None
        fifo = environ.get("QUTE_FIFO") or None
        return cls(url, Path(fifo) if fifo else None)

    def send(self, command: str) -> None:
        """Send one command line to qutebrowser."""
        if "\n" in command or "\r" in command:
            raise QutewardenError("refusing to send a command containing a line break")
        if self.fifo_path is None:
            raise QutewardenError("not run as a qutebrowser userscript (QUTE_FIFO unset)")
        with open(self.fifo_path, "a", encoding="utf-8") as fifo:
            fifo.write(command + "\n")

    def _message(self, command: str, text: str) -> None:
        self.send(f"{command} {quote_arg(sanitize_message(MESSAGE_PREFIX + text))}")

    def message_info(self, text: str) -> None:
        self._message("message-info", text)

    def message_warning(self, text: str) -> None:
        self._message("message-warning", text)

    def message_error(self, text: str) -> None:
        self._message("message-error", text)

    def enter_insert_mode(self) -> None:
        self.send("mode-enter insert")

    def jseval_file(self, path: Path) -> None:
        """Run the JS file at ``path`` in our isolated world, without echoing a result."""
        if not path.is_absolute():
            raise QutewardenError("jseval script path must be absolute")
        self.send(f"jseval --quiet --world={FILL_WORLD_ID} --file {quote_arg(str(path))}")

    def spawn_userscript(self, argv: Sequence[str]) -> None:
        self.send("spawn --userscript " + " ".join(quote_arg(a) for a in argv))
