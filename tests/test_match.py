"""URI match (spec "URI match"): Bitwarden-compatible modes, Candidates, origin_of."""

import pytest

from qutewarden.errors import QutewardenError
from qutewarden.match import origin_of


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
