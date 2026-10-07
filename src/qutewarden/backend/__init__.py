"""Backends: programs that give access to the Vault. See backend/base.py."""

from __future__ import annotations

from collections.abc import Mapping

from qutewarden.backend.base import Backend
from qutewarden.config import ConfigError


def make_backend(name: str, environ: Mapping[str, str]) -> Backend:
    if name == "rbw":
        from qutewarden.backend.rbw import RbwBackend
        return RbwBackend(environ)
    raise ConfigError(f"unknown backend {name!r} (only 'rbw' is supported)")
