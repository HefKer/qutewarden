"""URI match (spec "URI match"): Bitwarden-compatible modes, Candidates, origin_of."""

import pytest

from qutewarden.errors import QutewardenError
from qutewarden.match import make_suffix_extractor, origin_of, uri_matches
from qutewarden.model import ItemUri, MatchMode


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://github.com/login?x=1#y", "https://github.com"),
        ("HTTPS://GitHub.COM/Login", "https://github.com"),
        ("https://example.com:443/", "https://example.com"),
        ("http://example.com:80/", "http://example.com"),
        ("https://example.com:8443/a", "https://example.com:8443"),
        ("http://localhost:8080/", "http://localhost:8080"),
        ("https://bücher.example/", "https://xn--bcher-kva.example"),
        ("https://user:pw@example.com/", "https://example.com"),
    ],
)
def test_origin_of(url, origin):
    assert origin_of(url) == origin


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "about:blank", "qute://settings", "data:text/html,x", "", "https://"]
)
def test_origin_of_rejects_non_http_urls(url):
    with pytest.raises(QutewardenError):
        origin_of(url)


# --- URI match ---------------------------------------------------------------

BD, HOST, SW, EXACT, RE, NEVER = (
    MatchMode.BASE_DOMAIN,
    MatchMode.HOST,
    MatchMode.STARTS_WITH,
    MatchMode.EXACT,
    MatchMode.REGULAR_EXPRESSION,
    MatchMode.NEVER,
)


@pytest.fixture(scope="module")
def extractor(tmp_path_factory):
    # Bundled PSL snapshot: no network in tests.
    return make_suffix_extractor(tmp_path_factory.mktemp("cache"), offline=True)


URI_CASES = [
    # (item uri, mode, page url, expected)
    # base_domain: same registrable domain, any subdomain, scheme or port
    ("https://github.com", BD, "https://github.com/login", True),
    ("https://github.com", BD, "https://gist.github.com/x", True),
    ("https://www.github.com/a", BD, "http://github.com:8080/", True),
    ("github.com", BD, "https://github.com/login", True),  # no scheme -> http:// assumed
    ("https://github.com", BD, "https://gitlab.com/", False),
    ("https://github.com", BD, "https://github.com.evil.test/", False),
    ("https://evilgithub.com", BD, "https://github.com/", False),
    # multi-part public suffixes
    ("https://www.bbc.co.uk", BD, "https://login.bbc.co.uk/", True),
    ("https://bbc.co.uk", BD, "https://itv.co.uk/", False),
    ("https://example.com.au", BD, "https://shop.example.com.au/", True),
    # private PSL domains count (Bitwarden: tldts allowPrivateDomains: true)
    ("https://foo.github.io", BD, "https://foo.github.io/x", True),
    ("https://foo.github.io", BD, "https://bar.github.io/", False),
    # IPs and localhost compare whole host (port ignored)
    ("http://192.168.1.1", BD, "http://192.168.1.1:8080/", True),
    ("http://192.168.1.1", BD, "http://192.168.1.2/", False),
    ("http://localhost:3000", BD, "http://localhost:8080/", True),
    # hosts under a TLD not on the PSL: the PSL default rule "*" applies
    ("https://a.corp.internal", BD, "https://b.corp.internal/", True),
    ("https://a.corp.internal", BD, "https://a.lab.internal/", False),
    # IDN item URI matches the punycode host qutebrowser reports
    ("https://bücher.de", BD, "https://shop.xn--bcher-kva.de/", True),
    # Bitwarden's DomainMatchBlacklist
    ("https://google.com", BD, "https://script.google.com/", False),
    ("https://google.com", BD, "https://accounts.google.com/", True),
    # host: hostname and port must match; subdomains don't
    ("https://github.com", HOST, "https://github.com/login", True),
    ("https://github.com", HOST, "http://github.com/", True),
    ("https://github.com:443", HOST, "https://github.com/", True),
    ("https://github.com", HOST, "https://gist.github.com/", False),
    ("https://example.com", HOST, "https://example.com:8443/", False),
    ("https://example.com:8443", HOST, "https://example.com:8443/a", True),
    ("https://example.com:8443", HOST, "https://example.com:9443/a", False),
    ("example.com:8443", HOST, "https://example.com:8443/", True),
    # starts_with: plain string prefix of the full page URL
    ("https://example.com/app", SW, "https://example.com/app/login", True),
    ("https://example.com/app", SW, "https://example.com/other", False),
    ("https://example.com/app", SW, "http://example.com/app", False),
    ("https://example.com", SW, "https://example.com.evil.test/", True),  # Bitwarden semantics
    # exact: whole URL, string equality
    ("https://example.com/login", EXACT, "https://example.com/login", True),
    ("https://example.com/login", EXACT, "https://example.com/login?next=/", False),
    ("https://example.com/login", EXACT, "https://example.com/login/", False),
    # regular_expression: case-insensitive search over the full URL
    (r"^https://(www\.)?example\.com/", RE, "https://www.example.com/login", True),
    (r"^https://(www\.)?example\.com/", RE, "HTTPS://EXAMPLE.COM/", True),
    (r"example\.com", RE, "https://evil.test/?example.com", True),
    (r"^https://example\.com/", RE, "https://example.org/", False),
    (r"([", RE, "https://example.com/", False),  # invalid regex: no match, no crash
    # never
    ("https://github.com", NEVER, "https://github.com/login", False),
    # unparseable item URIs never match by host/domain
    ("", BD, "https://example.com/", False),
    ("not a url", BD, "https://example.com/", False),
    ("", HOST, "https://example.com/", False),
]


@pytest.mark.parametrize(("uri", "mode", "page", "expected"), URI_CASES)
def test_uri_matches(extractor, uri, mode, page, expected):
    item_uri = ItemUri(uri, mode)
    assert uri_matches(item_uri, page, default_mode=BD, extractor=extractor) is expected
