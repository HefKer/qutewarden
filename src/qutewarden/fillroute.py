"""The fill route: how JavaScript carrying secrets reaches the page (ADR-0002).

qutebrowser logs every command a userscript sends, so secrets never go into
QUTE_FIFO. Instead ``send_js`` creates a named pipe (0600) in a private
directory (0700) under ``$XDG_RUNTIME_DIR``, sends
``jseval --quiet --world=<id> --file <pipe>`` and writes the JS into the pipe.
The JS never touches disk; the pipe is removed afterwards in every case.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from pathlib import Path

from qutewarden.errors import QutewardenError


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


def send_js(qute, js: str, *, runtime_dir: Path, timeout: float = 5.0) -> None:
    raise NotImplementedError
