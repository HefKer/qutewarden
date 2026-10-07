"""`unlock`, `lock`, `sync`, `status`: thin Backend wrappers (#10). Stubs for now."""

from __future__ import annotations

import argparse
from datetime import datetime

from qutewarden.commands import not_implemented, register
from qutewarden.context import Context


@register("unlock", help="Unlock the vault")
def unlock(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "unlock")


@register("lock", help="Lock the vault")
def lock(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "lock")


@register("sync", help="Sync the vault with the server")
def sync(ctx: Context, args: argparse.Namespace) -> int:
    return not_implemented(ctx, "sync")


@register("status", help="Show locked/unlocked and the last sync time")
def status(ctx: Context, args: argparse.Namespace) -> int:
    st = ctx.backend.status()
    state = "unlocked" if st.unlocked else "locked"
    ctx.qute.message_info(f"vault {state}, {_last_sync(st.last_sync)}")
    return 0


def _last_sync(moment: datetime | None) -> str:
    """The last sync time in local time, to the minute."""
    if moment is None:
        return "last sync unknown"
    return "last sync " + moment.astimezone().strftime("%Y-%m-%d %H:%M")
