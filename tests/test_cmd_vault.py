"""`vault`: pick from every Login item; Mismatch fill after confirmation; opt-in copy (#9)."""

from __future__ import annotations

import dataclasses
import itertools

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.fake import FakeBackend, fake_password, fake_totp
from qutewarden.model import MatchMode
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"


@pytest.fixture
def vault(ctx, fake_qutebrowser):
    """Run ``qutewarden vault [flags]`` on ``url``; return the exit code."""

    def vault(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
              picker: FakePicker | None = None, clipboard: object = ...,
              **config_changes: object) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=dataclasses.replace(config, **config_changes),
                environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker,
                clipboard=ctx.clipboard if clipboard is ... else clipboard)

        try:
            return cli.main(["vault", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return vault


def test_the_picker_lists_every_login_item_not_only_candidates(vault):
    picker = FakePicker(choices=[None])
    assert vault(picker=picker) == 0
    assert picker.lines == [["GitHub — alice", "GitHub (work) — alice-work", "Example — bob",
                             "No TOTP — carol", "Never — dave", "Elsewhere — erin"]]


def test_picking_a_candidate_fills_it_without_asking(vault, fake_qutebrowser):
    picker = FakePicker(choices=[1], confirm=False)
    assert vault(picker=picker) == 0
    [js] = fake_qutebrowser.js
    assert '"mode": "auto"' in js
    assert f'"password": "{fake_password("github-alt")}"' in js
    assert '"origin": "https://github.com"' in js
    assert "Yes" not in itertools.chain.from_iterable(picker.lines)
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling GitHub (work) (alice-work)")]


def test_a_mismatch_fill_asks_first_showing_the_items_uris_next_to_the_page_origin(
        vault, fake_qutebrowser):
    picker = FakePicker(choices=[5], confirm=True)  # Elsewhere: https://other.test
    assert vault(picker=picker) == 0
    assert picker.prompts[-1] == "Fill Elsewhere (erin)?"
    assert picker.lines[-1] == ["Page: github.com", "Item: other.test", "Yes", "No"]
    [js] = fake_qutebrowser.js
    assert f'"password": "{fake_password("elsewhere")}"' in js
    assert '"origin": "https://github.com"' in js


def test_a_declined_mismatch_fill_fills_nothing(vault, fake_qutebrowser):
    backend = FakeBackend()
    assert vault(picker=FakePicker(choices=[5], confirm=False), backend=backend) == 0
    assert fake_qutebrowser.js == []
    assert fake_qutebrowser.messages == []
    assert "get_secrets" not in backend.calls


def test_an_item_whose_uri_is_set_to_never_match_is_a_mismatch(vault):
    picker = FakePicker(choices=[4], confirm=False)  # Never: github.com/login, mode NEVER
    vault(picker=picker)
    assert picker.lines[-1] == ["Page: github.com", "Item: github.com /login", "Yes", "No"]


def test_a_mismatch_with_an_item_that_has_no_uris_says_so(vault):
    from qutewarden.model import LoginItem
    backend = FakeBackend([LoginItem(id="bare", name="Bare", username="zoe")])
    picker = FakePicker(confirm=False)
    vault(picker=picker, backend=backend)
    assert picker.lines[-1] == ["Page: github.com", "Item: (no URIs)", "Yes", "No"]


def _mismatch_lines(vault, url: str, *uris, **config_changes) -> list[str]:
    """The confirmation's Page and Item lines for an Item with ``uris`` on ``url``."""
    from qutewarden.model import ItemUri, LoginItem
    item_uris = tuple(u if isinstance(u, ItemUri) else ItemUri(u, MatchMode.NEVER) for u in uris)
    backend = FakeBackend([LoginItem(id="x", name="X", username="xavier", uris=item_uris)])
    picker = FakePicker(confirm=False)
    vault(picker=picker, backend=backend, url=url, **config_changes)
    return picker.lines[-1][:-2]


@pytest.mark.parametrize("url, page_line", [
    ("https://www.365chess.com/login", "Page: www.365chess.com"),
    ("http://intranet.local:8080/x", "Page: http://intranet.local:8080"),
    ("https://example.com:8443/", "Page: example.com:8443"),
    ("https://example.com:443/", "Page: example.com"),
])
def test_the_page_line_shows_the_host_first_without_https(vault, url, page_line):
    assert _mismatch_lines(vault, url, "https://other.test")[0] == page_line


@pytest.mark.parametrize("uri, item_line", [
    ("https://www.365chess.com/signup.php", "Item: www.365chess.com /signup.php"),
    ("https://www.365chess.com.evil.example/login?next=/a#b",
     "Item: www.365chess.com.evil.example /login?next=/a#b"),
    ("https://WWW.Example.COM", "Item: www.example.com"),
    ("https://example.com/", "Item: example.com /"),
    ("https://example.com:443/x", "Item: example.com /x"),
    ("https://example.com:8443/x", "Item: example.com:8443 /x"),
    ("http://intranet.local/x", "Item: http://intranet.local /x"),
    ("http://intranet.local:8080", "Item: http://intranet.local:8080"),
    ("https://bücher.example/a", "Item: xn--bcher-kva.example /a"),
    # Not a URL with a host, or one that might read differently host-first: verbatim.
    ("github.com/login", "Item: github.com/login"),
    ("androidapp://com.example.app", "Item: androidapp://com.example.app"),
    ("https://www.365chess.com@evil.example/", "Item: https://www.365chess.com@evil.example/"),
    ("https://evil.example\\@www.365chess.com/",
     "Item: https://evil.example\\@www.365chess.com/"),
    ("https://www.365chess.com .evil.example/", "Item: https://www.365chess.com .evil.example/"),
    ("not a url", "Item: not a url"),
    ("https://", "Item: https://"),
])
def test_an_item_uri_shows_its_host_first_or_verbatim(vault, uri, item_line):
    assert _mismatch_lines(vault, GITHUB, uri)[1] == item_line


@pytest.mark.parametrize("mode, default_mode", [
    (MatchMode.REGULAR_EXPRESSION, MatchMode.BASE_DOMAIN),
    (None, MatchMode.REGULAR_EXPRESSION),
])
def test_a_regular_expression_uri_is_shown_verbatim(vault, mode, default_mode):
    from qutewarden.model import ItemUri
    regex = r"^https://www\.365chess\.com/.*"
    assert _mismatch_lines(vault, "https://other.test/", ItemUri(regex, mode),
                           matching_default_mode=default_mode) == [
        "Page: other.test", f"Item: {regex}"]


def test_each_item_uri_gets_its_own_line(vault):
    assert _mismatch_lines(vault, GITHUB, "https://a.test/x", "b.test") == [
        "Page: github.com", "Item: a.test /x", "Item: b.test"]


def test_without_vault_allow_copy_no_copy_action_is_offered(vault):
    picker = FakePicker()
    vault(picker=picker)
    assert picker.prompts == ["Vault"]
    assert not any("Copy" in line for line in itertools.chain.from_iterable(picker.lines))


def test_with_vault_allow_copy_the_actions_follow_the_item_choice(vault):
    picker = FakePicker(choices=[0, None])
    assert vault("--vault-allow-copy", picker=picker) == 0
    assert picker.lines[-1] == ["Fill", "Copy password", "Copy TOTP", "Copy username"]


def test_copying_the_password_puts_it_on_the_clipboard_cleared_later(
        vault, fake_qutebrowser, fake_clipboard):
    picker = FakePicker(choices=[5, 1])  # Elsewhere, "Copy password"
    assert vault("--vault-allow-copy", "--vault-copy-clear-seconds", "9", picker=picker) == 0
    assert fake_clipboard.copies == [(fake_password("elsewhere"), 9)]
    assert fake_qutebrowser.js == []
    assert "mode-enter insert" not in fake_qutebrowser.commands
    assert fake_qutebrowser.messages == [
        ("info", "qutewarden: copied password for Elsewhere (erin); clipboard clears in 9 s")]


def test_copying_the_totp_code(vault, fake_clipboard):
    assert vault("--vault-allow-copy", picker=FakePicker(choices=[0, 2])) == 0
    assert fake_clipboard.copies == [(fake_totp("github"), 30)]


def test_an_item_without_totp_or_username_offers_only_what_it_has(vault):
    from qutewarden.model import LoginItem
    backend = FakeBackend([LoginItem(id="bare", name="Bare")])
    picker = FakePicker(choices=[0, None])
    vault("--vault-allow-copy", picker=picker, backend=backend)
    assert picker.lines[-1] == ["Fill", "Copy password"]


def test_copy_works_on_a_page_that_is_not_http(vault, fake_clipboard):
    assert vault("--vault-allow-copy", url="qute://start/",
                 picker=FakePicker(choices=[0, 1])) == 0
    assert fake_clipboard.copies == [(fake_password("github"), 30)]


def test_copy_without_a_clipboard_tool_is_an_error_before_any_secret_is_read(
        vault, fake_qutebrowser):
    backend = FakeBackend()
    assert vault("--vault-allow-copy", picker=FakePicker(choices=[0, 1]), backend=backend,
                 clipboard=None) == 1
    assert "get_secrets" not in backend.calls
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error" and "wl-copy" in text
