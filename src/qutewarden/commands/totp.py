"""`totp` subcommand: fill (or copy) a Candidate's TOTP code (#7)."""

from __future__ import annotations

import argparse

from qutewarden import flow
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import QutewardenError
from qutewarden.filljs import render_fill_js
from qutewarden.fillroute import send_js


@register("totp", help="Fill (or copy) a Candidate's TOTP code")
def run(ctx: Context, args: argparse.Namespace) -> int:
    selection = flow.select_candidate(ctx, prompt="TOTP")
    item = selection.item
    no_totp = QutewardenError(f"{flow.describe(item)} has no TOTP")
    if not item.has_totp:
        raise no_totp
    code = ctx.backend.get_secrets(item.id).totp
    if not code:
        raise no_totp
    js = render_fill_js(expected_origin=selection.origin, mode="otp", totp=code,
                        submit=ctx.config.submit_after_fill)
    ctx.qute.message_info(f"filling TOTP for {flow.describe(item)}")
    send_js(ctx.qute, js, runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)
    if ctx.config.insert_mode_after_fill:
        ctx.qute.enter_insert_mode()
    return 0
