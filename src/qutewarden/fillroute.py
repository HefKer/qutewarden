"""The fill route: how JavaScript carrying secrets reaches the page (ADR-0002).

qutebrowser logs every command a userscript sends, so secrets never go into
QUTE_FIFO. Instead ``send_js`` creates a named pipe (0600) in a private
directory (0700) under ``$XDG_RUNTIME_DIR``, sends
``jseval --quiet --world=<id> --file <pipe>`` and writes the JS into the pipe.
The JS never touches disk; the pipe is removed afterwards in every case.
"""

from __future__ import annotations

import errno
import os
import secrets
import stat
import time
from collections.abc import Mapping
from pathlib import Path

from qutewarden.errors import QutewardenError
from qutewarden.qute import Qute

_POLL_INTERVAL = 0.01  # seconds between attempts to open the pipe for writing


class FillRouteError(QutewardenError):
    """The fill JavaScript couldn't be handed to qutebrowser."""


def pipe_dir(environ: Mapping[str, str]) -> Path:
    """Return ``$XDG_RUNTIME_DIR/qutewarden``, created 0700 and checked."""
    base = environ.get("XDG_RUNTIME_DIR")
    if not base:
        raise FillRouteError("XDG_RUNTIME_DIR is not set; can't create a private pipe")
    return _private_dir(Path(base) / "qutewarden")


def _private_dir(path: Path) -> Path:
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError as e:
        raise FillRouteError(f"can't create {path}: {e.strerror}") from None
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid():
        raise FillRouteError(f"{path} is not a directory owned by you; remove it")
    if stat.S_IMODE(st.st_mode) != 0o700:
        raise FillRouteError(f"{path} has permissions {stat.S_IMODE(st.st_mode):o}, "
                             "expected 700; fix or remove it")
    return path


def send_js(qute: Qute, js: str, *, runtime_dir: Path, timeout: float = 5.0) -> None:
    """Run ``js`` in the page through a private named pipe (ADR-0002).

    qutebrowser reads ``--file`` with a plain blocking ``open()`` on its main
    thread, so a qutebrowser that reached ``open()`` with no writer would
    freeze. We therefore only send the command once the pipe exists, then
    poll a non-blocking write-open until qutebrowser has the pipe open for
    reading, and give up after ``timeout`` seconds. The pipe is removed in
    every case.

    Residual race: if qutebrowser opens the pipe between our last attempt
    and the unlink, its ``open()`` waits for a writer that never comes. The
    window is a few microseconds after a multi-second timeout.
    """
    directory = _private_dir(runtime_dir)
    path = directory / f"fill-{secrets.token_hex(16)}.js"
    try:
        os.mkfifo(path, 0o600)
    except OSError as e:
        raise FillRouteError(f"can't create the fill pipe: {e.strerror}") from None
    try:
        qute.jseval_file(path)
        fd = _open_when_read(path, timeout)
        try:
            os.set_blocking(fd, True)
            data = js.encode("utf-8")
            while data:
                written = os.write(fd, data)
                data = data[written:]
        except OSError as e:  # e.g. qutebrowser closed the pipe early (EPIPE)
            raise FillRouteError(f"can't write the fill script: {e.strerror}") from None
        finally:
            os.close(fd)
    finally:
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass


def _open_when_read(path: Path, timeout: float) -> int:
    """Open ``path`` for writing once a reader has it open, or raise after ``timeout``."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as e:
            if e.errno != errno.ENXIO:  # ENXIO: no reader yet
                raise FillRouteError(f"can't open the fill pipe: {e.strerror}") from None
        if time.monotonic() >= deadline:
            raise FillRouteError("qutebrowser didn't read the fill script; nothing was filled")
        time.sleep(_POLL_INTERVAL)
