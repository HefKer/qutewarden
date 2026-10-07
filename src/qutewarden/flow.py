"""Steps shared by `fill`, `totp`, `generate` and `vault`.

``select_candidate`` is steps 1–3 of `fill` in the spec: read the page URL,
unlock, work out the Candidates and pick one. ``fill_login`` sends the chosen
Item's secrets to the page through the fill route (ADR-0002).
"""

from __future__ import annotations

from dataclasses import dataclass

from qutewarden import match
from qutewarden.context import Context
from qutewarden.errors import UserCancelled
from qutewarden.filljs import render_fill_js
from qutewarden.fillroute import send_js
from qutewarden.model import LoginItem


@dataclass(frozen=True)
class Selection:
    """A Candidate the user (or Auto-fill) chose for the page."""

    page_url: str
    origin: str  # match.origin_of(page_url); the fill script checks it in the page
    item: LoginItem


def select_candidate(ctx: Context, *, prompt: str = "Fill") -> Selection:
    """Steps 1–3 of `fill`: page URL, unlock, Candidates, then Auto-fill or the picker.

    Raises UserCancelled if the picker is dismissed.
    """
    page_url = ctx.qute.url or ""
    origin = match.origin_of(page_url)
    found = match.candidates(ctx.backend.list_logins(), page_url,
                             default_mode=ctx.config.matching_default_mode,
                             extractor=_extractor(ctx))
    index = ctx.picker.choose(prompt, [item_line(item) for item in found])
    if index is None:
        raise UserCancelled()
    return Selection(page_url, origin, found[index])


def item_line(item: LoginItem) -> str:
    """One picker line: the Item name and username."""
    return f"{item.name} — {item.username}" if item.username else item.name


def fill_login(ctx: Context, selection: Selection) -> None:
    """Fill the chosen Item; the script decides between login and OTP in the page."""
    item = selection.item
    secrets = ctx.backend.get_secrets(item.id)
    js = render_fill_js(expected_origin=selection.origin, mode="auto",
                        username=item.username, password=secrets.password,
                        totp=secrets.totp, submit=ctx.config.submit_after_fill)
    ctx.qute.message_info(f"filling {_describe(item)}")
    send_js(ctx.qute, js, runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)


def _describe(item: LoginItem) -> str:
    return f"{item.name} ({item.username})" if item.username else item.name


def _extractor(ctx: Context):
    if ctx.suffix_extractor is None:
        ctx.suffix_extractor = match.make_suffix_extractor(ctx.cache_dir)
    return ctx.suffix_extractor
