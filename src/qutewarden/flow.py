"""Steps shared by `fill`, `totp`, `generate` and `vault`.

``select_candidate`` is steps 1–3 of `fill` in the spec: read the page URL,
unlock, work out the Candidates and pick one. ``fill_login`` sends the chosen
Item's secrets to the page through the fill route (ADR-0002).
"""

from __future__ import annotations

from dataclasses import dataclass

from typing import TYPE_CHECKING

from qutewarden import match
from qutewarden.context import Context
from qutewarden.errors import QutewardenError, UserCancelled
from qutewarden.filljs import render_fill_js
from qutewarden.fillroute import send_js
from qutewarden.model import LoginItem

if TYPE_CHECKING:
    from qutewarden.clipboard import Clipboard


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
    ensure_unlocked(ctx)
    found = find_candidates(ctx, page_url)
    if not found:
        raise QutewardenError(f"no Login item matches {origin}; "
                              "use `vault` to pick from every Item")
    if len(found) == 1 and ctx.config.auto_fill:
        return Selection(page_url, origin, found[0])
    index = ctx.picker.choose(prompt, [item_line(item) for item in found])
    if index is None:
        raise UserCancelled()
    return Selection(page_url, origin, found[index])


def ensure_unlocked(ctx: Context) -> None:
    """Unlock the vault if it's locked; the Backend asks for the master password."""
    if not ctx.backend.is_unlocked():
        ctx.backend.unlock()


def find_candidates(ctx: Context, page_url: str) -> list[LoginItem]:
    """The Candidates for the page; if there are none, sync once and look again.

    May return an empty list (callers decide whether that's an error).
    """
    found = _candidates(ctx, page_url)
    if not found:
        ctx.backend.sync()
        found = _candidates(ctx, page_url)
    return found


def _candidates(ctx: Context, page_url: str) -> list[LoginItem]:
    return match.candidates(ctx.backend.list_logins(), page_url,
                            default_mode=ctx.config.matching_default_mode,
                            extractor=_extractor(ctx))


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
    ctx.qute.message_info(f"filling {describe(item)}")
    send_js(ctx.qute, js, runtime_dir=ctx.runtime_dir, timeout=ctx.fill_timeout)
    if ctx.config.insert_mode_after_fill:
        ctx.qute.enter_insert_mode()


def require_clipboard(ctx: Context) -> Clipboard:
    """The clipboard, or an error if neither wl-copy nor xclip was found.

    Call it before fetching the secret you want to copy.
    """
    if ctx.clipboard is None:
        raise QutewardenError("no clipboard tool found (install wl-clipboard for wl-copy, "
                              "or xclip)")
    return ctx.clipboard


def copy_secret(ctx: Context, item: LoginItem, what: str, value: str, *,
                clear_after: int) -> None:
    """Copy one of ``item``'s secrets (``what``: "TOTP", "password"...) and say so.

    The clipboard is cleared after ``clear_after`` seconds if it still holds
    ``value`` (Security rule 4). The message names the Item, never the value.
    """
    require_clipboard(ctx).copy_secret(value, clear_after=clear_after)
    ctx.qute.message_info(f"copied {what} for {describe(item)}; "
                          f"clipboard clears in {clear_after} s")


def describe(item: LoginItem) -> str:
    """The Item for messages: name and username (Security rule 6 allows both)."""
    return f"{item.name} ({item.username})" if item.username else item.name


def _extractor(ctx: Context):
    if ctx.suffix_extractor is None:
        ctx.suffix_extractor = match.make_suffix_extractor(ctx.cache_dir)
    return ctx.suffix_extractor
