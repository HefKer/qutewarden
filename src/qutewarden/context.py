"""Context: the bundle of dependencies every subcommand receives.

Production code builds it with ``Context.from_environ``; tests build one from
fakes and pass it to ``cli.main(make_context=...)`` or call a command directly.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from qutewarden.backend import make_backend
from qutewarden.clipboard import Clipboard, detect_clipboard
from qutewarden.config import Config
from qutewarden.generator import generate_password_from_config
from qutewarden.picker import DmenuPicker, Picker, detect_picker_argv
from qutewarden.qute import Qute

if TYPE_CHECKING:
    from tldextract import TLDExtract

    from qutewarden.backend.base import Backend


@dataclass
class Context:
    config: Config
    environ: Mapping[str, str]
    qute: Qute
    backend: Backend
    picker: Picker
    clipboard: Clipboard | None  # None if no wl-copy/xclip and not needed
    runtime_dir: Path  # $XDG_RUNTIME_DIR/qutewarden (created 0700 lazily by fillroute)
    cache_dir: Path  # $XDG_CACHE_HOME/qutewarden
    generate_password: Callable[[Config], str]
    fill_timeout: float = 5.0  # seconds fillroute waits for qutebrowser to open the pipe
    # Public Suffix List lookup for URI match; None = match.make_suffix_extractor(cache_dir).
    # Tests pass an offline one (no network).
    suffix_extractor: TLDExtract | None = None

    @classmethod
    def from_environ(cls, config: Config, environ: Mapping[str, str]) -> Context:
        return cls(
            config=config,
            environ=environ,
            qute=Qute.from_environ(environ),
            backend=make_backend(config.backend, environ),
            picker=DmenuPicker(config.picker or detect_picker_argv(environ)),
            clipboard=detect_clipboard(environ),
            runtime_dir=_runtime_dir(environ),
            cache_dir=_cache_dir(environ),
            generate_password=generate_password_from_config,
        )


def _runtime_dir(environ: Mapping[str, str]) -> Path:
    base = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(base) / "qutewarden"


def _cache_dir(environ: Mapping[str, str]) -> Path:
    base = environ.get("XDG_CACHE_HOME") or ""
    if not base:
        base = str(Path(environ.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "qutewarden"
