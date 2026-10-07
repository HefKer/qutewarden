"""`unlock`, `lock`, `sync`, `status`: thin wrappers around the Backend.

Asking for the master password and auto-locking are the Backend's (rbw's) job.
Backend errors reach ``cli.main``, which shows them with message-error,
including the hint on what to do next (e.g. run `rbw login`).
"""

from __future__ import annotations

import argparse
from datetime import datetime

from qutewarden.commands import register
from qutewarden.context import Context


@register("unlock", help="Unlock the vault")
def unlock(ctx: Context, args: argparse.Namespace) -> int:
    ctx.backend.unlock()
    ctx.qute.message_info("vault unlocked")
    return 0


@register("lock", help="Lock the vault")
def lock(ctx: Context, args: argparse.Namespace) -> int:
    ctx.backend.lock()
    ctx.qute.message_info("vault locked")
    return 0


@register("sync", help="Sync the vault with the server")
def sync(ctx: Context, args: argparse.Namespace) -> int:
    ctx.backend.sync()
    ctx.qute.message_info("vault synced")
    return 0


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
