"""URI match: which Login items are Candidates for a page. See GLOSSARY.md.

Behaves like Bitwarden's clients (``LoginUriView.matchesUri`` and
``Utils.getDomain``/``getHost``): base domains use the Public Suffix List
including private domains, so ``foo.github.io`` and ``bar.github.io`` differ.
Pure functions, no Backend dependency. Item names are never used.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from qutewarden.errors import QutewardenError

_DEFAULT_PORTS = {"http": 80, "https": 443}


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
