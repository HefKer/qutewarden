"""`vault` subcommand: pick any Login item from the vault (#9).

A Candidate is filled as usual. Any other Item is a Mismatch fill: the user
must first confirm, having seen the Item's URIs next to the page's origin
(Security rule 5).
"""

from __future__ import annotations

import argparse

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import UserCancelled
from qutewarden.model import LoginItem


@register("vault", help="Pick any Login item; Mismatch fill after confirmation")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.ensure_unlocked(ctx)
    items = ctx.backend.list_logins()
    index = ctx.picker.choose("Vault", [flow.item_line(item) for item in items])
    if index is None:
        raise UserCancelled()
    item = items[index]
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    if not _is_candidate(ctx, item, page_url) and not _confirm_mismatch(ctx, item, origin):
        raise UserCancelled()
    flow.fill_login(ctx, flow.Selection(page_url, origin, item))
    return 0


def _is_candidate(ctx: Context, item: LoginItem, page_url: str) -> bool:
    return match.is_candidate(item, page_url, default_mode=ctx.config.matching_default_mode,
                              extractor=flow._extractor(ctx))


def _confirm_mismatch(ctx: Context, item: LoginItem, origin: str) -> bool:
    """Ask before a Mismatch fill, showing the Item's URIs next to the page's origin."""
    uris = [f"Item: {u.uri}" for u in item.uris] or ["Item: (no URIs)"]
    return ctx.picker.confirm(f"Fill {flow.describe(item)} on {origin}?",
                              [f"Page: {origin}", *uris])
