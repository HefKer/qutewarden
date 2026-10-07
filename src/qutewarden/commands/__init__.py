"""Subcommand registry.

Each module in this package registers its subcommands with ``@register``.
``all_commands()`` imports every module here, so adding ``commands/foo.py``
with ``@register("foo", ...)`` is all a new subcommand needs: the CLI and the
no-leak test pick it up.
"""

from __future__ import annotations

import argparse
import importlib
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qutewarden.context import Context

RunFn = Callable[["Context", argparse.Namespace], int]
AddArgumentsFn = Callable[[argparse.ArgumentParser], None]


@dataclass(frozen=True)
class Command:
    name: str
    help: str
    run: RunFn
    add_arguments: AddArgumentsFn | None = None


_REGISTRY: dict[str, Command] = {}


def register(name: str, help: str, add_arguments: AddArgumentsFn | None = None
             ) -> Callable[[RunFn], RunFn]:
    """Decorator: register ``run`` as subcommand ``name``."""

    def decorator(run: RunFn) -> RunFn:
        if name in _REGISTRY and _REGISTRY[name].run is not run:
            raise RuntimeError(f"subcommand {name!r} registered twice")
        _REGISTRY[name] = Command(name, help, run, add_arguments)
        return run

    return decorator


def all_commands() -> dict[str, Command]:
    """Import every module in this package and return the registry."""
    for module in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{module.name}")
    return dict(_REGISTRY)
