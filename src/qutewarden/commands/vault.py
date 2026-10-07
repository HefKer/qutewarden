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


@register("vault", help="Pick any Login item; Mismatch fill after confirmation")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.ensure_unlocked(ctx)
    items = ctx.backend.list_logins()
    index = ctx.picker.choose("Vault", [flow.item_line(item) for item in items])
    if index is None:
        raise UserCancelled()
    item = items[index]
    page_url = ctx.qute.url or ""
    flow.fill_login(ctx, flow.Selection(page_url, match.origin_of(page_url), item))
    return 0
