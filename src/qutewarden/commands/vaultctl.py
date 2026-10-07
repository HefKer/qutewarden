"""`unlock`, `lock`, `sync`, `status`: thin Backend wrappers (#10). Stubs for now."""

from __future__ import annotations

import argparse

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
    return not_implemented(ctx, "status")
