"""`totp` subcommand: fill a Candidate's TOTP code (#7). Stub for now."""

from __future__ import annotations

import argparse

from qutewarden.commands import not_implemented, register
from qutewarden.context import Context


@register("totp", help="Fill (or copy) a Candidate's TOTP code")
def run(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "totp")
