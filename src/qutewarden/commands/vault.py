"""`vault` subcommand: pick any Login item from the vault (#9). Stub for now."""

from __future__ import annotations

import argparse

from qutewarden.commands import not_implemented, register
from qutewarden.context import Context


@register("vault", help="Pick any Login item; Mismatch fill after confirmation")
def run(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "vault")
