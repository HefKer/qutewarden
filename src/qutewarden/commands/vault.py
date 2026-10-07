"""`vault` subcommand: pick any Login item from the vault (#9).

A Candidate is filled as usual. Any other Item is a Mismatch fill: the user
must first confirm, having seen the Item's URIs next to the page's origin
(Security rule 5). With ``vault.allow_copy`` on, a second menu also offers
copying a single field instead (Security rule 4).
"""

from __future__ import annotations

import argparse

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import QutewardenError, UserCancelled
from qutewarden.model import LoginItem


FILL = "Fill"


@register("vault", help="Pick any Login item; Mismatch fill after confirmation")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.ensure_unlocked(ctx)
    items = ctx.backend.list_logins()
    index = ctx.picker.choose("Vault", [flow.item_line(item) for item in items])
    if index is None:
        raise UserCancelled()
    item = items[index]
    if ctx.config.vault_allow_copy:
        actions = _actions(item)
        choice = ctx.picker.choose(item.name, actions)
        if choice is None:
            raise UserCancelled()
        if actions[choice] != FILL:
            _copy(ctx, item, actions[choice].removeprefix("Copy "))
            return 0
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    if not _is_candidate(ctx, item, page_url) and not _confirm_mismatch(ctx, item, origin):
        raise UserCancelled()
    flow.fill_login(ctx, flow.Selection(page_url, origin, item))
    return 0


def _actions(item: LoginItem) -> list[str]:
    actions = [FILL, "Copy password"]
    if item.has_totp:
        actions.append("Copy TOTP")
    if item.username:
        actions.append("Copy username")
    return actions


def _copy(ctx: Context, item: LoginItem, field: str) -> None:
    """Copy one field; the clipboard is cleared after ``vault.copy_clear_seconds``."""
    flow.require_clipboard(ctx)
    if field == "username":
        value = item.username
    else:
        secrets = ctx.backend.get_secrets(item.id)
        value = secrets.totp if field == "TOTP" else secrets.password
    if not value:
        raise QutewardenError(f"{flow.describe(item)} has no {field}")
    flow.copy_secret(ctx, item, field, value, clear_after=ctx.config.vault_copy_clear_seconds)


def _is_candidate(ctx: Context, item: LoginItem, page_url: str) -> bool:
    return match.is_candidate(item, page_url, default_mode=ctx.config.matching_default_mode,
                              extractor=flow._extractor(ctx))


def _confirm_mismatch(ctx: Context, item: LoginItem, origin: str) -> bool:
    """Ask before a Mismatch fill, showing the Item's URIs next to the page's origin."""
    uris = [f"Item: {u.uri}" for u in item.uris] or ["Item: (no URIs)"]
    return ctx.picker.confirm(f"Fill {flow.describe(item)} on {origin}?",
                              [f"Page: {origin}", *uris])
