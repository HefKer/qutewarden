"""`generate` subcommand: generate a password, save it to the vault, then fill it (#8)."""

from __future__ import annotations

import argparse

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import UserCancelled
from qutewarden.filljs import render_fill_js
from qutewarden.fillroute import send_js
from qutewarden.model import LoginItem


@register("generate", help="Generate a password, save it to the vault, then fill it")
def run(ctx: Context, args: argparse.Namespace) -> int:
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    flow.ensure_unlocked(ctx)
    [item] = flow.find_candidates(ctx, page_url)
    if not ctx.picker.confirm(f"Replace password for {item.username} on {item.name}?"):
        raise UserCancelled()
    password = ctx.generate_password(ctx.config)
    ctx.backend.update_password(item.id, password)
    _fill(ctx, origin, item, password)
    return 0


def _fill(ctx: Context, origin: str, item: LoginItem, password: str) -> None:
    js = render_fill_js(expected_origin=origin, mode="new_password",
                        username=item.username, password=password,
                        submit=ctx.config.submit_after_fill)
    ctx.qute.message_info(f"saved new password, filling {_describe(item)}")
    send_js(ctx.qute, js, runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)
    if ctx.config.insert_mode_after_fill:
        ctx.qute.enter_insert_mode()


def _describe(item: LoginItem) -> str:
    return f"{item.name} ({item.username})" if item.username else item.name
