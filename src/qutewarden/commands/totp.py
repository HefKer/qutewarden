"""`totp` subcommand: fill (or copy) a Candidate's TOTP code (#7)."""

from __future__ import annotations

import argparse

from qutewarden import flow
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import QutewardenError
from qutewarden.filljs import render_fill_js


@register("totp", help="Fill (or copy) a Candidate's TOTP code")
def run(ctx: Context, args: argparse.Namespace) -> int:
    copy = ctx.config.totp_clipboard
    if copy:
        flow.require_clipboard(ctx)
    selection = flow.select_candidate(ctx, prompt="TOTP")
    item = selection.item
    no_totp = QutewardenError(f"{flow.describe(item)} has no TOTP")
    if not item.has_totp:
        raise no_totp
    code = flow.login_secrets(ctx, item).totp
    if not code:
        raise no_totp
    if copy:
        flow.copy_secret(ctx, item, "TOTP", code,
                         clear_after=ctx.config.totp_clipboard_clear_seconds)
        return 0
    js = render_fill_js(expected_origin=selection.origin, mode="otp", totp=code,
                        submit=ctx.config.submit_after_fill)
    flow.send_fill(ctx, js, f"filling TOTP for {flow.describe(item)}")
    return 0
