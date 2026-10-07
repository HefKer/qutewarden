"""URI match: which Login items are Candidates for a page. See GLOSSARY.md.

Behaves like Bitwarden's clients (``LoginUriView.matchesUri`` and
``Utils.getDomain``/``getHost``): base domains use the Public Suffix List
including private domains, so ``foo.github.io`` and ``bar.github.io`` differ.
Pure functions, no Backend dependency. Item names are never used.
"""

from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urlsplit

import tldextract

from qutewarden.errors import QutewardenError
from qutewarden.model import ItemUri, MatchMode

_DEFAULT_PORTS = {"http": 80, "https": 443}

# Bitwarden's Utils.DomainMatchBlacklist: base domain -> hosts it must not match.
_DOMAIN_MATCH_BLACKLIST = {"google.com": frozenset({"script.google.com"})}


def make_suffix_extractor(cache_dir: Path, *, offline: bool = False) -> tldextract.TLDExtract:
    """Public Suffix List lookup, cached under ``cache_dir/"tldextract"``.

    ``cache_dir`` is ``Context.cache_dir``. ``offline=True`` uses only the PSL
    snapshot bundled with tldextract (no network; for tests).
    """
    kwargs = {"suffix_list_urls": ()} if offline else {}
    return tldextract.TLDExtract(
        cache_dir=str(Path(cache_dir) / "tldextract"),
        include_psl_private_domains=True,
        **kwargs,
    )


def uri_matches(
    item_uri: ItemUri,
    page_url: str,
    *,
    default_mode: MatchMode,
    extractor: tldextract.TLDExtract,
) -> bool:
    """Whether one URI of a Login item matches the page, per its match mode."""
    mode = item_uri.mode or default_mode
    uri = item_uri.uri
    if mode is MatchMode.NEVER:
        return False
    if mode is MatchMode.EXACT:
        return page_url == uri
    if mode is MatchMode.STARTS_WITH:
        return bool(uri) and page_url.startswith(uri)
    if mode is MatchMode.REGULAR_EXPRESSION:
        try:
            return re.search(uri, page_url, re.IGNORECASE) is not None
        except re.error:
            return False
    item, page = _parse(uri), _parse(page_url)
    if item is None or page is None:
        return False
    if mode is MatchMode.HOST:
        return item.host == page.host
    # BASE_DOMAIN
    item_domain = _base_domain(item.hostname, extractor)
    if item_domain is None or item_domain != _base_domain(page.hostname, extractor):
        return False
    return page.hostname not in _DOMAIN_MATCH_BLACKLIST.get(item_domain, ())


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
