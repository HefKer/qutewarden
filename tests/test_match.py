"""URI match (spec "URI match"): Bitwarden-compatible modes, Candidates, origin_of."""

import pytest

from qutewarden.errors import QutewardenError
from qutewarden.match import (
    Candidate,
    candidates,
    is_candidate,
    load_equivalent_domains,
    make_suffix_extractor,
    origin_of,
    uri_matches,
)
from qutewarden.model import ItemUri, LoginItem, MatchMode


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


# --- Candidates ----------------------------------------------------------------

PAGE = "https://github.com/login"


@pytest.mark.parametrize(
    ("default_mode", "expected"),
    [(BD, True), (HOST, False), (NEVER, False)],
)
def test_uri_without_mode_uses_default_mode(extractor, default_mode, expected):
    item_uri = ItemUri("https://gist.github.com")
    assert uri_matches(item_uri, PAGE, default_mode=default_mode, extractor=extractor) is expected


def test_explicit_mode_beats_default_mode(extractor):
    item_uri = ItemUri("https://gist.github.com", MatchMode.BASE_DOMAIN)
    assert uri_matches(item_uri, PAGE, default_mode=NEVER, extractor=extractor)


ITEMS = (
    LoginItem("one", "GitHub", "alice", (ItemUri("https://github.com"),)),
    LoginItem(
        "any",
        "work",
        "bob",
        (ItemUri("https://gitlab.com"), ItemUri("https://github.com/login", MatchMode.EXACT)),
    ),
    LoginItem("never", "GitHub", "carol", (ItemUri("https://github.com", MatchMode.NEVER),)),
    LoginItem("no-uris", "github.com", "dave"),  # name looks right, but names are never used
    LoginItem("other", "github", "erin", (ItemUri("https://other.test"),)),
)


def test_candidates_are_items_with_any_matching_uri(extractor):
    found = candidates(ITEMS, PAGE, default_mode=BD, extractor=extractor)
    assert found == [Candidate(ITEMS[0]), Candidate(ITEMS[1])]


@pytest.mark.parametrize("item", ITEMS, ids=lambda item: item.id)
def test_is_candidate(extractor, item):
    expected = item.id in {"one", "any"}
    assert is_candidate(item, PAGE, default_mode=BD, extractor=extractor) is expected


def test_item_without_uris_is_never_a_candidate(extractor):
    item = LoginItem("no-uris", "github.com")
    for mode in MatchMode:
        assert not is_candidate(item, PAGE, default_mode=mode, extractor=extractor)


# --- Equivalent domains --------------------------------------------------------

GLOBAL = load_equivalent_domains(global_groups=True)
NONE = load_equivalent_domains(global_groups=False)
GOOGLE = LoginItem("g", "Google", "me@gmail.com", (ItemUri("https://accounts.google.com"),))


def test_an_item_is_a_candidate_on_a_domain_in_a_global_group_and_shows_its_domain(extractor):
    [found] = candidates([GOOGLE], "https://www.youtube.com/", default_mode=BD,
                         extractor=extractor, equivalent_domains=GLOBAL)
    assert found == Candidate(GOOGLE, equivalent_domain="google.com")


def test_with_global_groups_off_an_item_is_not_a_candidate_on_an_equivalent_domain(extractor):
    assert not is_candidate(GOOGLE, "https://www.youtube.com/", default_mode=BD,
                            extractor=extractor, equivalent_domains=NONE)


def test_a_users_own_group_makes_its_domains_equivalent(extractor):
    mine = load_equivalent_domains(global_groups=False,
                                   user_groups=[["Example.COM", "example.org"]])
    item = LoginItem("e", "Example", "bob", (ItemUri("https://example.com"),))
    [found] = candidates([item], "https://login.example.org/", default_mode=BD,
                         extractor=extractor, equivalent_domains=mine)
    assert found == Candidate(item, equivalent_domain="example.com")


def test_user_groups_add_to_the_global_ones(extractor):
    both = load_equivalent_domains(global_groups=True, user_groups=[["google.com", "g.test"]])
    for page in ("https://youtube.com/", "https://g.test/"):
        assert is_candidate(GOOGLE, page, default_mode=BD, extractor=extractor,
                            equivalent_domains=both)


@pytest.mark.parametrize("mode", [NEVER, EXACT, HOST, SW, RE])
def test_equivalent_domains_apply_only_to_the_base_domain_mode(extractor, mode):
    item = LoginItem("g", "Google", "me", (ItemUri("https://youtube.com/", mode),))
    assert not is_candidate(item, "https://google.com/", default_mode=BD, extractor=extractor,
                            equivalent_domains=GLOBAL)


@pytest.mark.parametrize(("default_mode", "expected"), [(BD, True), (HOST, False)])
def test_uris_without_a_mode_use_equivalent_domains_only_under_a_base_domain_default(
        extractor, default_mode, expected):
    assert is_candidate(GOOGLE, "https://youtube.com/", default_mode=default_mode,
                        extractor=extractor, equivalent_domains=GLOBAL) is expected


def test_an_item_with_a_direct_uri_match_is_not_shown_as_equivalent(extractor):
    item = LoginItem("g", "Google", "me", (ItemUri("https://google.com"),
                                           ItemUri("https://youtube.com")))
    [found] = candidates([item], "https://youtube.com/", default_mode=BD, extractor=extractor,
                         equivalent_domains=GLOBAL)
    assert found.equivalent_domain is None

