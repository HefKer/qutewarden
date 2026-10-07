"""Context: the bundle of dependencies every subcommand receives.

Production code builds it with ``Context.from_environ``; tests build one from
fakes and pass it to ``cli.main(make_context=...)`` or call a command directly.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from qutewarden.config import Config
from qutewarden.qute import Qute

if TYPE_CHECKING:
    from tldextract import TLDExtract

    from qutewarden.backend.base import Backend
    from qutewarden.clipboard import Clipboard
    from qutewarden.picker import Picker


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
        make_backend = _provided("qutewarden.backend", "make_backend")
        dmenu_picker = _provided("qutewarden.picker", "DmenuPicker")
        detect_picker_argv = _provided("qutewarden.picker", "detect_picker_argv")
        detect_clipboard = _provided("qutewarden.clipboard", "detect_clipboard")
        generate = _provided("qutewarden.generator", "generate_password_from_config")

        picker = None
        if dmenu_picker is not None and detect_picker_argv is not None:
            picker = dmenu_picker(config.picker or detect_picker_argv(environ))

        return cls(
            config=config,
            environ=environ,
            qute=Qute.from_environ(environ),
            backend=make_backend(config.backend, environ) if make_backend else None,
            picker=picker,
            clipboard=detect_clipboard(environ) if detect_clipboard else None,
            runtime_dir=_runtime_dir(environ),
            cache_dir=_cache_dir(environ),
            generate_password=generate if generate else _no_generator,
        )


def _runtime_dir(environ: Mapping[str, str]) -> Path:
    base = environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(base) / "qutewarden"


def _cache_dir(environ: Mapping[str, str]) -> Path:
    base = environ.get("XDG_CACHE_HOME") or ""
    if not base:
        base = str(Path(environ.get("HOME") or Path.home()) / ".cache")
    return Path(base) / "qutewarden"


def _provided(module: str, name: str) -> Any:
    """Return ``module.name``, or None if that module doesn't exist yet.

    The v1 modules land ticket by ticket; until one exists its dependency is
    None and only the stub subcommands (which don't use it) can run.
    """
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise
        return None
    return getattr(mod, name, None)


def _no_generator(config: Config) -> str:
    raise NotImplementedError("password generator not implemented yet")
