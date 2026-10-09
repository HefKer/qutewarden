"""URI match: which Login items are Candidates for a page. See GLOSSARY.md.

Behaves like Bitwarden's clients (``LoginUriView.matchesUri`` and
``Utils.getDomain``/``getHost``): base domains use the Public Suffix List
including private domains, so ``foo.github.io`` and ``bar.github.io`` differ.
Equivalent domains (ADR-0006) widen only the base-domain match mode.
Pure functions, no Backend dependency. Item names are never used.
"""

from __future__ import annotations

import functools
import ipaddress
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

import tldextract

from qutewarden.errors import QutewardenError
from qutewarden.model import ItemUri, LoginItem, MatchMode

_DEFAULT_PORTS = {"http": 80, "https": 443}

# Bitwarden's Utils.DomainMatchBlacklist: base domain -> hosts it must not match.
_DOMAIN_MATCH_BLACKLIST = {"google.com": frozenset({"script.google.com"})}


def make_suffix_extractor(cache_dir: Path, *, offline: bool = False) -> tldextract.TLDExtract:
    """Public Suffix List lookup, cached under ``cache_dir/"tldextract"``.

    ``cache_dir`` is ``Context.cache_dir``. ``offline=True`` uses only the PSL
    snapshot bundled with tldextract (no network; for tests).
    """
    kwargs: dict[str, Any] = {"suffix_list_urls": ()} if offline else {}
    return tldextract.TLDExtract(
        cache_dir=str(Path(cache_dir) / "tldextract"),
        include_psl_private_domains=True,
        **kwargs,
    )


class EquivalentDomains:
    """Groups of base domains treated as one site for the base-domain match mode."""

    def __init__(self, groups: Iterable[Iterable[str]] = ()) -> None:
        self._others: dict[str, set[str]] = {}
        for group in groups:
            domains = {_normalize_domain(d) for d in group} - {""}
            for domain in domains:
                self._others.setdefault(domain, set()).update(domains - {domain})

    def equivalent(self, a: str, b: str) -> bool:
        """Whether base domains ``a`` and ``b`` (both normalised) share a group."""
        return b in self._others.get(a, ())


NO_EQUIVALENT_DOMAINS = EquivalentDomains()


def load_equivalent_domains(*, global_groups: bool,
                            user_groups: Iterable[Iterable[str]] = ()) -> EquivalentDomains:
    """Bitwarden's global groups (if ``global_groups``) plus the user's own."""
    groups = [*(_global_groups() if global_groups else ()), *user_groups]
    return EquivalentDomains(groups)


@functools.cache
def _global_groups() -> tuple[tuple[str, ...], ...]:
    """The vendored global groups, ``equivalent_domains.json`` (ADR-0006)."""
    text = resources.files("qutewarden").joinpath("equivalent_domains.json").read_text("utf-8")
    return tuple(tuple(group) for group in json.loads(text)["groups"])


def _normalize_domain(domain: str) -> str:
    domain = domain.strip().lower().rstrip(".")
    try:
        return domain.encode("idna").decode("ascii")
    except UnicodeError:
        return domain


@dataclass(frozen=True)
class Candidate:
    """A Candidate for a page, and whether it is one only through Equivalent domains."""

    item: LoginItem
    # The base domain of the Item's URI when no URI matches the page directly,
    # only through Equivalent domains; None for a direct URI match.
    equivalent_domain: str | None = None


def candidates(
    items: Iterable[LoginItem],
    page_url: str,
    *,
    default_mode: MatchMode,
    extractor: tldextract.TLDExtract,
    equivalent_domains: EquivalentDomains = NO_EQUIVALENT_DOMAINS,
) -> list[Candidate]:
    """The Candidates among ``items`` for the page, in their original order."""
    found = []
    for item in items:
        candidate = _candidate(item, page_url, default_mode=default_mode, extractor=extractor,
                               equivalent_domains=equivalent_domains)
        if candidate is not None:
            found.append(candidate)
    return found


def is_candidate(
    item: LoginItem,
    page_url: str,
    *,
    default_mode: MatchMode,
    extractor: tldextract.TLDExtract,
    equivalent_domains: EquivalentDomains = NO_EQUIVALENT_DOMAINS,
) -> bool:
    """An Item is a Candidate when any of its URIs match. Its name is never used."""
    return _candidate(item, page_url, default_mode=default_mode, extractor=extractor,
                      equivalent_domains=equivalent_domains) is not None


def _candidate(item: LoginItem, page_url: str, *, default_mode: MatchMode,
               extractor: tldextract.TLDExtract,
               equivalent_domains: EquivalentDomains) -> Candidate | None:
    """A direct URI match wins over one through Equivalent domains."""
    via: str | None = None
    for uri in item.uris:
        result = _uri_match(uri, page_url, default_mode=default_mode, extractor=extractor,
                            equivalent_domains=equivalent_domains)
        if result is _DIRECT:
            return Candidate(item)
        if result is not None and via is None:
            via = result
    return None if via is None else Candidate(item, equivalent_domain=via)


def uri_matches(
    item_uri: ItemUri,
    page_url: str,
    *,
    default_mode: MatchMode,
    extractor: tldextract.TLDExtract,
    equivalent_domains: EquivalentDomains = NO_EQUIVALENT_DOMAINS,
) -> bool:
    """Whether one URI of a Login item matches the page, per its match mode."""
    return _uri_match(item_uri, page_url, default_mode=default_mode, extractor=extractor,
                      equivalent_domains=equivalent_domains) is not None


_DIRECT = ""  # _uri_match's result for a direct match (never a base domain)


def _uri_match(item_uri: ItemUri, page_url: str, *, default_mode: MatchMode,
               extractor: tldextract.TLDExtract,
               equivalent_domains: EquivalentDomains) -> str | None:
    """None: no match; _DIRECT; or the Item URI's base domain, equivalent to the page's."""
    mode = item_uri.mode or default_mode
    uri = item_uri.uri
    if mode is MatchMode.NEVER:
        return None
    if mode is MatchMode.EXACT:
        return _DIRECT if page_url == uri else None
    if mode is MatchMode.STARTS_WITH:
        return _DIRECT if uri and page_url.startswith(uri) else None
    if mode is MatchMode.REGULAR_EXPRESSION:
        try:
            return _DIRECT if re.search(uri, page_url, re.IGNORECASE) is not None else None
        except re.error:
            return None
    item, page = _parse(uri), _parse(page_url)
    if item is None or page is None:
        return None
    if mode is MatchMode.HOST:
        return _DIRECT if item.host == page.host else None
    # BASE_DOMAIN
    item_domain = _base_domain(item.hostname, extractor)
    page_domain = _base_domain(page.hostname, extractor)
    if item_domain is None or page_domain is None:
        return None
    if page.hostname in _DOMAIN_MATCH_BLACKLIST.get(item_domain, ()):
        return None
    if item_domain == page_domain:
        return _DIRECT
    if equivalent_domains.equivalent(item_domain, page_domain):
        return item_domain
    return None


class _Parsed(NamedTuple):
    hostname: str  # lowercase, IDNA
    host: str  # hostname[:port], default port omitted (WHATWG URL.host)


def _parse(uri: str) -> _Parsed | None:
    """Parse like Bitwarden's Utils.getUrl: no scheme + a dot -> assume http://."""
    uri = uri.strip()
    if "://" not in uri:
        if "." not in uri:
            return None
        uri = "http://" + uri
    try:
        parts = urlsplit(uri)
        hostname = parts.hostname
        port = parts.port
        if not hostname or any(c.isspace() for c in hostname):
            return None
        hostname = hostname.encode("idna").decode("ascii")
    except (ValueError, UnicodeError):
        return None
    shown = f"[{hostname}]" if ":" in hostname else hostname
    if port is None or port == _DEFAULT_PORTS.get(parts.scheme.lower()):
        return _Parsed(hostname, shown)
    return _Parsed(hostname, f"{shown}:{port}")


def _base_domain(hostname: str, extractor: tldextract.TLDExtract) -> str | None:
    """Registrable domain like Bitwarden's Utils.getDomain (tldts, private domains on)."""
    if hostname == "localhost" or _is_ip(hostname):
        return hostname
    result = extractor(hostname)
    if result.top_domain_under_public_suffix:
        return result.top_domain_under_public_suffix
    if not result.suffix:
        # TLD not on the PSL: the PSL's default rule "*" makes it the suffix.
        labels = hostname.rstrip(".").split(".")
        if len(labels) >= 2 and all(labels[-2:]):
            return ".".join(labels[-2:])
    return None


def _is_ip(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def origin_of(url: str) -> str:
    """``scheme://host[:port]`` as ``location.origin`` would give it.

    Lowercase, IDNA (punycode) host, default port omitted. Only http/https;
    anything else raises QutewardenError.
    """
    try:
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise QutewardenError("not an http(s) page") from None
    if scheme not in _DEFAULT_PORTS or not host:
        raise QutewardenError("not an http(s) page")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        raise QutewardenError("not an http(s) page") from None
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"
