"""`fill` subcommand: fill the page's login form from a Candidate (#6)."""

from __future__ import annotations

import argparse

from qutewarden import flow
from qutewarden.commands import register
from qutewarden.context import Context


@register("fill", help="Fill the current page's login form from a Candidate")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.fill_login(ctx, flow.select_candidate(ctx))
    return 0
