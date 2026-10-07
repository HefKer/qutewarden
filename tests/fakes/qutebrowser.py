"""FakeQutebrowser: the qutebrowser end of QUTE_FIFO, for tests.

Like qutebrowser it makes QUTE_FIFO a named pipe, holds it open read-write
and reads commands line by line while the userscript runs. For
``jseval ... --file P`` it opens P with a plain blocking ``open()`` and reads
it, as qutebrowser does on its main thread.
"""

from __future__ import annotations

import os
import select
import shlex
import stat
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipeSeen:
    """What the fake observed about a ``--file`` path just before reading it."""

    path: Path
    is_fifo: bool
    mode: int  # permission bits
    dir_mode: int  # permission bits of the containing directory
    uid: int


class FakeQutebrowser:
    def __init__(self, tmp_dir: Path, *, reads_js_files: bool = True) -> None:
        self.fifo_path = Path(tmp_dir) / "qute_fifo"
        os.mkfifo(self.fifo_path, 0o600)
        self.reads_js_files = reads_js_files
        self.commands: list[str] = []
        self.messages: list[tuple[str, str]] = []  # (level, text)
        self.js: list[str] = []
        self.pipes: list[PipeSeen] = []
        self._fd = os.open(self.fifo_path, os.O_RDWR | os.O_NONBLOCK)
        self._buffer = b""
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def environ(self, url: str = "https://github.com/login") -> dict[str, str]:
        return {"QUTE_FIFO": str(self.fifo_path), "QUTE_URL": url}

    def close(self) -> None:
        """Process every command already written, then stop reading."""
        self._stop.set()
        self._thread.join(timeout=10)
        if self._fd >= 0:
            os.close(self._fd)
            self._fd = -1

    def _run(self) -> None:
        while True:
            # Read the flag *before* select: everything written before close()
            # is then already in the pipe, so an empty select really means done.
            stopping = self._stop.is_set()
            ready, _, _ = select.select([self._fd], [], [], 0.01)
            if ready:
                self._buffer += os.read(self._fd, 65536)
                while b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    self._handle(line.decode("utf-8"))
            elif stopping:
                return

    def _handle(self, line: str) -> None:
        self.commands.append(line)
        args = shlex.split(line)
        if args and args[0].startswith("message-") and len(args) >= 2:
            self.messages.append((args[0].removeprefix("message-"), args[-1]))
        elif args and args[0] == "jseval" and "--file" in args and self.reads_js_files:
            path = Path(args[args.index("--file") + 1])
            st = os.stat(path)
            self.pipes.append(PipeSeen(path, stat.S_ISFIFO(st.st_mode), stat.S_IMODE(st.st_mode),
                                       stat.S_IMODE(os.stat(path.parent).st_mode), st.st_uid))
            with open(path, encoding="utf-8") as f:  # blocks until a writer appears
                self.js.append(f.read())
