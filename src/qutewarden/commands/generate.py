"""`generate` subcommand: generate a password, save it, then fill it (#8). Stub for now."""

from __future__ import annotations

import argparse

from qutewarden.commands import not_implemented, register
from qutewarden.context import Context


@register("generate", help="Generate a password, save it to the vault, then fill it")
def run(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "generate")
