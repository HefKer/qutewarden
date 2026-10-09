"""`card` subcommand: pick a Card item and fill the page's payment form (#35, ADR-0005).

Card items have no URIs, so every Card item is offered and the user's pick is
the only guard (Security rule 5); the origin check inside the page still runs.
There is no Auto-fill, and the form is never submitted, whatever
``submit_after_fill`` says: an unwanted submit can be a purchase.
"""

from __future__ import annotations

import argparse

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import QutewardenError
from qutewarden.filljs import render_card_fill_js
from qutewarden.model import CardItem, CardSecrets


@register("card", help="Pick a Card item and fill the page's payment form (never submits)")
def run(ctx: Context, args: argparse.Namespace) -> int:
    origin = match.origin_of(ctx.qute.url or "")
    flow.ensure_unlocked(ctx)
    cards = ctx.backend.list_cards()
    if not cards:
        raise QutewardenError("the vault has no Card items")
    card = cards[flow.pick(ctx, "Card", [card_line(c) for c in cards])]
    secrets = ctx.backend.get_secrets(card.id)
    if not isinstance(secrets, CardSecrets):
        raise QutewardenError(f"{card.name} isn't a Card item")
    flow.send_fill(ctx, render_card_fill_js(expected_origin=origin, card=secrets),
                   f"filling {card.name}")
    return 0


def card_line(card: CardItem) -> str:
    """``<name> — <brand> *<last 4>``; Security rule 6 allows no more of the card."""
    shown = " ".join(part for part in (card.brand, card.last4 and f"*{card.last4}") if part)
    return f"{card.name} — {shown}" if shown else card.name
