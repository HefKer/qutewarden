"""`fill` subcommand: fill the page's login form from a Candidate (#6). Stub for now."""

from __future__ import annotations

import argparse

from qutewarden.commands import not_implemented, register
from qutewarden.context import Context


@register("fill", help="Fill the current page's login form from a Candidate")
def run(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "fill")
