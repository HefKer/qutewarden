"""`identity` subcommand: pick an Identity item and fill the page's address form (#36, ADR-0005).

Like `card`: Identity items have no URIs, so every Identity item is offered and
the user's pick is the only guard (Security rule 5); the origin check inside
the page still runs. There is no Auto-fill, and the form is never submitted,
whatever ``submit_after_fill`` says: an identity fill is usually one step in a
longer form. Every value of an Identity item counts as a secret in messages
(Security rule 6), so picker lines and messages show the Item name only.
"""

from __future__ import annotations

import argparse

from qutewarden import flow
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.filljs import render_identity_fill_js
from qutewarden.model import IdentityItem, IdentitySecrets


@register("identity",
          help="Pick an Identity item and fill the page's address form (never submits)")
def run(ctx: Context, args: argparse.Namespace) -> int:
    flow.pick_and_fill(ctx, item_type="Identity", items=ctx.backend.list_identities,
                       line=_identity_line, secrets_type=IdentitySecrets,
                       render=lambda origin, identity: render_identity_fill_js(
                           expected_origin=origin, identity=identity))
    return 0


def _identity_line(identity: IdentityItem) -> str:
    """The Item name only: every value of an Identity item is a secret (Security rule 6)."""
    return identity.name
