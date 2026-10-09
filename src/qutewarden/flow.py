"""Steps shared by the subcommands that fill: `fill`, `totp`, `generate`, `vault`, `card`,
`identity`.

``select_candidate`` is steps 1–3 of `fill` in the spec: read the page URL,
unlock, work out the Candidates and pick one. ``fill_login`` sends the chosen
Item's secrets to the page through the fill route (ADR-0002). ``pick_and_fill``
is the whole of `card` and `identity`, whose Items have no URIs (ADR-0005).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, TypeVar

from qutewarden import match
from qutewarden.context import Context
from qutewarden.errors import QutewardenError, UserCancelled
from qutewarden.filljs import render_fill_js
from qutewarden.fillroute import send_js
from qutewarden.model import ItemSecrets, LoginItem, LoginSecrets

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
    if len(found) == 1 and ctx.config.auto_fill and found[0].equivalent_domain is None:
        # Never Auto-fill through Equivalent domains (ADR-0006).
        return Selection(page_url, origin, found[0].item)
    index = pick(ctx, prompt, [candidate_line(c) for c in found])
    return Selection(page_url, origin, found[index].item)


def pick(ctx: Context, prompt: str, lines: list[str]) -> int:
    """The index of the line the user picked; raises UserCancelled if dismissed."""
    index = ctx.picker.choose(prompt, lines)
    if index is None:
        raise UserCancelled()
    return index


def ensure_unlocked(ctx: Context) -> None:
    """Unlock the vault if it's locked; the Backend asks for the master password."""
    if not ctx.backend.is_unlocked():
        ctx.backend.unlock()


def find_candidates(ctx: Context, page_url: str) -> list[match.Candidate]:
    """The Candidates for the page; if there are none, sync once and look again.

    May return an empty list (callers decide whether that's an error).
    """
    found = _candidates(ctx, page_url)
    if not found:
        ctx.backend.sync()
        found = _candidates(ctx, page_url)
    return found


def _candidates(ctx: Context, page_url: str) -> list[match.Candidate]:
    return match.candidates(ctx.backend.list_logins(), page_url,
                            default_mode=ctx.config.matching_default_mode,
                            extractor=_extractor(ctx),
                            equivalent_domains=_equivalent_domains(ctx))


def is_candidate(ctx: Context, item: LoginItem, page_url: str) -> bool:
    """Whether ``item`` is a Candidate for the page (Security rule 5)."""
    return match.is_candidate(item, page_url, default_mode=ctx.config.matching_default_mode,
                              extractor=_extractor(ctx),
                              equivalent_domains=_equivalent_domains(ctx))


def item_line(item: LoginItem) -> str:
    """One picker line: the Item name and username."""
    return f"{item.name} — {item.username}" if item.username else item.name


def candidate_line(candidate: match.Candidate) -> str:
    """A Candidate's picker line, plus the domain it matched through Equivalent domains."""
    line = item_line(candidate.item)
    domain = candidate.equivalent_domain
    return f"{line} ({domain})" if domain else line


def fill_login(ctx: Context, selection: Selection) -> None:
    """Fill the chosen Item and its Custom fields; the script decides between login and
    OTP in the page."""
    item = selection.item
    secrets = login_secrets(ctx, item)
    js = render_fill_js(expected_origin=selection.origin, mode="auto",
                        username=item.username, password=secrets.password,
                        totp=secrets.totp, submit=ctx.config.submit_after_fill,
                        fields=secrets.fields)
    send_fill(ctx, js, f"filling {describe(item)}")


class _PickableItem(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def name(self) -> str: ...


ItemT = TypeVar("ItemT", bound=_PickableItem)
SecretsT = TypeVar("SecretsT", bound=ItemSecrets)


def pick_and_fill(ctx: Context, *, item_type: str, items: Callable[[], Sequence[ItemT]],
                  line: Callable[[ItemT], str], secrets_type: type[SecretsT],
                  render: Callable[[str, SecretsT], str]) -> None:
    """Unlock, pick one of ``items()`` and fill it; for Items picked without URI match.

    The pick is the only guard (Security rule 5); ``render(origin, secrets)``
    returns the fill script, which checks the origin again in the page.
    """
    origin = match.origin_of(ctx.qute.url or "")
    ensure_unlocked(ctx)
    choices = items()
    if not choices:
        raise QutewardenError(f"the vault has no {item_type} items")
    item = choices[pick(ctx, item_type, [line(choice) for choice in choices])]
    secrets = ctx.backend.get_secrets(item.id)
    if not isinstance(secrets, secrets_type):
        article = "an" if item_type[0] in "AEIOU" else "a"
        raise QutewardenError(f"{item.name} isn't {article} {item_type} item")
    send_fill(ctx, render(origin, secrets), f"filling {item.name}")


def login_secrets(ctx: Context, item: LoginItem) -> LoginSecrets:
    """``get_secrets`` for a Login item; an error if the Vault says it's another type."""
    secrets = ctx.backend.get_secrets(item.id)
    if not isinstance(secrets, LoginSecrets):
        raise QutewardenError(f"{describe(item)} isn't a Login item")
    return secrets


def send_fill(ctx: Context, js: str, message: str) -> None:
    """Announce a Fill, send its script through the fill route, then insert mode.

    qutewarden gets no reply from the page, so ``message`` is shown first and
    must be neutral. Insert mode follows ``insert_mode_after_fill``.
    """
    ctx.qute.message_info(message)
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


def _equivalent_domains(ctx: Context) -> match.EquivalentDomains:
    return match.load_equivalent_domains(
        global_groups=ctx.config.matching_global_equivalent_domains,
        user_groups=ctx.config.matching_equivalent_domains)


def _extractor(ctx: Context):
    if ctx.suffix_extractor is None:
        ctx.suffix_extractor = match.make_suffix_extractor(ctx.cache_dir)
    return ctx.suffix_extractor
