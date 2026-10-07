"""`generate` subcommand: generate a password, save it to the vault, then fill it (#8).

A new Item needs the username the user typed on the page, and a userscript
can't get a value back from ``jseval``. So that case runs in two stages
(ADR-0004): the first run sends a secret-free probe script that copies the
username field into a ``data-qutewarden-probe-<nonce>`` attribute, then
spawns ``generate --username-probe <nonce>``. qutebrowser dumps the DOM to
``QUTE_HTML`` for that second run, which reads the attribute, generates,
saves and fills. The password exists only in the second run.
"""

from __future__ import annotations

import argparse
import os
import secrets
import shlex
import sys

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.config import SETTINGS, Setting
from qutewarden.context import Context
from qutewarden.errors import UserCancelled
from qutewarden.filljs import render_fill_js, render_probe_js
from qutewarden.fillroute import send_js
from qutewarden.model import LoginItem

NEW_ITEM_LINE = "new Item"


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    # Internal: set by the first stage when it spawns the second (ADR-0004).
    parser.add_argument("--username-probe", metavar="NONCE", default=None,
                        help=argparse.SUPPRESS)


@register("generate", help="Generate a password, save it to the vault, then fill it",
          add_arguments=_add_arguments)
def run(ctx: Context, args: argparse.Namespace) -> int:
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    flow.ensure_unlocked(ctx)
    item = _choose_item(ctx, flow.find_candidates(ctx, page_url))
    if item is None:
        _probe_username(ctx, args, origin)
        return 0
    password = ctx.generate_password(ctx.config)
    ctx.backend.update_password(item.id, password)
    _fill(ctx, origin, item, password)
    return 0


def _choose_item(ctx: Context, found: list[LoginItem]) -> LoginItem | None:
    """The Candidate whose password to replace, or None for a new Item."""
    if not found:
        return None
    if len(found) == 1:
        [item] = found
        if not ctx.picker.confirm(f"Replace password for {item.username} on {item.name}?"):
            raise UserCancelled()
        return item
    index = ctx.picker.choose("Replace password",
                              [*(flow.item_line(item) for item in found), NEW_ITEM_LINE])
    if index is None:
        raise UserCancelled()
    return found[index] if index < len(found) else None


def _probe_username(ctx: Context, args: argparse.Namespace, origin: str) -> None:
    """Stage 1: copy the page's username into the DOM, then run stage 2."""
    nonce = secrets.token_hex(8)
    send_js(ctx.qute, render_probe_js(expected_origin=origin, nonce=nonce),
            runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)
    ctx.qute.spawn_userscript([os.path.abspath(sys.argv[0]), "generate",
                               *_settings_flags(args), "--username-probe", nonce])


def _settings_flags(args: argparse.Namespace) -> list[str]:
    """The settings flags this run was given, to pass on to stage 2."""
    given = vars(args)
    flags: list[str] = []
    if given.get("config") is not None:
        flags += ["--config", str(given["config"])]
    for setting in SETTINGS:
        if setting.attr in given:
            flags += _flag(setting, given[setting.attr])
    return flags


def _flag(setting: Setting, value: object) -> list[str]:
    if setting.type is bool:
        return [setting.flag if value else "--no-" + setting.flag.removeprefix("--")]
    if setting.type is tuple:
        return [setting.flag, shlex.join(value)]
    return [setting.flag, str(value)]


def _fill(ctx: Context, origin: str, item: LoginItem, password: str) -> None:
    js = render_fill_js(expected_origin=origin, mode="new_password",
                        username=item.username, password=password,
                        submit=ctx.config.submit_after_fill)
    ctx.qute.message_info(f"saved new password, filling {_describe(item)}")
    send_js(ctx.qute, js, runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)
    if ctx.config.insert_mode_after_fill:
        ctx.qute.enter_insert_mode()


def _describe(item: LoginItem) -> str:
    return f"{item.name} ({item.username})" if item.username else item.name
