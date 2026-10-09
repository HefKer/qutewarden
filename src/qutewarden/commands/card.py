"""`card` subcommand: pick a Card item and fill the page's payment form (#35, ADR-0005).

Card items have no URIs, so every Card item is offered and the user's pick is
the only guard (Security rule 5); the origin check inside the page still runs.
There is no Auto-fill, and the form is never submitted, whatever
``submit_after_fill`` says: an unwanted submit can be a purchase.
"""

from __future__ import annotations

import argparse

from qutewarden import flow
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.filljs import render_card_fill_js
from qutewarden.model import CardItem, CardSecrets


@register("card", help="Pick a Card item and fill the page's payment form (never submits)")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.pick_and_fill(ctx, item_type="Card", items=ctx.backend.list_cards, line=card_line,
                       secrets_type=CardSecrets,
                       render=lambda origin, card: render_card_fill_js(expected_origin=origin,
                                                                       card=card))
    return 0


def card_line(card: CardItem) -> str:
    """``<name> — <brand> *<last 4>``; Security rule 6 allows no more of the card."""
    shown = " ".join(part for part in (card.brand, card.last4 and f"*{card.last4}") if part)
    return f"{card.name} — {shown}" if shown else card.name
