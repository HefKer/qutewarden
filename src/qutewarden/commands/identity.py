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

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.context import Context
from qutewarden.errors import QutewardenError
from qutewarden.filljs import render_identity_fill_js
from qutewarden.model import IdentitySecrets


@register("identity",
          help="Pick an Identity item and fill the page's address form (never submits)")
def run(ctx: Context, args: argparse.Namespace) -> int:
    origin = match.origin_of(ctx.qute.url or "")
    flow.ensure_unlocked(ctx)
    identities = ctx.backend.list_identities()
    if not identities:
        raise QutewardenError("the vault has no Identity items")
    identity = identities[flow.pick(ctx, "Identity", [i.name for i in identities])]
    secrets = ctx.backend.get_secrets(identity.id)
    if not isinstance(secrets, IdentitySecrets):
        raise QutewardenError(f"{identity.name} isn't an Identity item")
    flow.send_fill(ctx, render_identity_fill_js(expected_origin=origin, identity=secrets),
                   f"filling {identity.name}")
    return 0
