"""`generate` subcommand: generate a password, save it to the vault, then fill it (#8).

A new Item needs the username the user typed on the page, and a userscript
can't get a value back from ``jseval``. So that case runs in two stages
(ADR-0004): the first run sends a secret-free probe script that copies the
username field into a ``data-qutewarden-probe-<nonce>`` attribute, then
spawns ``generate --probe-origin <origin> --username-probe <nonce>``.
qutebrowser dumps the DOM to ``QUTE_HTML`` for that second run, which checks
the page is still on that origin, reads the attribute, generates, saves and
fills. The password exists only in the second run.
"""

from __future__ import annotations

import argparse
import os
import re
import secrets
import shlex
import sys
from html.parser import HTMLParser
from urllib.parse import urlsplit

from qutewarden import flow, match
from qutewarden.commands import register
from qutewarden.config import SETTINGS, Setting
from qutewarden.context import Context
from qutewarden.errors import QutewardenError, UserCancelled
from qutewarden.filljs import render_fill_js, render_probe_js
from qutewarden.fillroute import send_js
from qutewarden.model import ItemUri, LoginItem

NEW_ITEM_LINE = "new Item"
_NONCE_RE = re.compile(r"[0-9a-f]{16}")


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    # Internal: set by the first stage when it spawns the second (ADR-0004).
    parser.add_argument("--username-probe", metavar="NONCE", default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument("--probe-origin", metavar="ORIGIN", default=None,
                        help=argparse.SUPPRESS)


@register("generate", help="Generate a password, save it to the vault, then fill it",
          add_arguments=_add_arguments)
def run(ctx: Context, args: argparse.Namespace) -> int:
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    nonce = args.username_probe
    if nonce is not None:
        if not _NONCE_RE.fullmatch(nonce):
            raise QutewardenError("generate: malformed --username-probe")
        if args.probe_origin != origin:
            # The user switched tabs or navigated since stage 1.
            raise QutewardenError("generate: the page changed; nothing saved")
        return _create_item(ctx, page_url, origin, nonce)
    flow.ensure_unlocked(ctx)
    item = _choose_item(ctx, flow.find_candidates(ctx, page_url))
    if item is None:
        _probe_username(ctx, args, origin)
        return 0
    password = ctx.generate_password(ctx.config)
    ctx.backend.update_password(item.id, password)
    _fill(ctx, origin, item, password)
    return 0


def _create_item(ctx: Context, page_url: str, origin: str, nonce: str) -> int:
    """Stage 2: username from the DOM dump (or the picker), then generate, save, fill."""
    username = _probed_username(ctx.environ.get("QUTE_HTML"), nonce)
    if not username:
        username = ctx.picker.ask_text("Username")
        if username is None:
            raise UserCancelled()
    flow.ensure_unlocked(ctx)
    item = LoginItem(id="", name=urlsplit(origin).hostname or origin, username=username or None,
                     uris=(ItemUri(origin),))
    password = ctx.generate_password(ctx.config)
    ctx.backend.create_login(name=item.name, username=item.username, uri=origin,
                             password=password)
    if not flow.is_candidate(ctx, item, page_url):
        # E.g. matching.default_mode = never: saved, but no Fill (Security rule 5).
        ctx.qute.message_info(f"saved new password for {flow.describe(item)}; "
                              "not filled, it doesn't match this page")
        return 0
    _fill(ctx, origin, item, password, probe_nonce=nonce)
    return 0


class _ProbeReader(HTMLParser):
    """Finds the probe attribute on the ``<html>`` element of a DOM dump."""

    def __init__(self, attribute: str) -> None:
        super().__init__()
        self.attribute = attribute
        self.value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "html" and self.value is None:
            self.value = dict(attrs).get(self.attribute)


def _probed_username(dump_path: str | None, nonce: str) -> str | None:
    if not dump_path:
        return None
    try:
        with open(dump_path, encoding="utf-8", errors="replace") as f:
            html = f.read()
    except OSError:
        return None
    reader = _ProbeReader(f"data-qutewarden-probe-{nonce}")
    reader.feed(html)
    reader.close()
    value = (reader.value or "").strip()
    return value or None


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
                               *_settings_flags(args), "--probe-origin", origin,
                               "--username-probe", nonce])


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


def _fill(ctx: Context, origin: str, item: LoginItem, password: str, *,
          probe_nonce: str | None = None) -> None:
    # Only the new-password fields are filled (spec, `generate` step 3).
    js = render_fill_js(expected_origin=origin, mode="new_password", password=password,
                        submit=ctx.config.submit_after_fill, probe_nonce=probe_nonce)
    flow.send_fill(ctx, js, f"saved new password, filling {flow.describe(item)}")
