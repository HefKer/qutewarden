"""`fill`: pick a Candidate and fill the page (#6), against the fake Backend and FIFO."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.fake import FakeBackend, fake_password, fake_totp
from qutewarden.model import ItemUri, LoginItem
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"
EXAMPLE = "https://example.com/signin"


@pytest.fixture
def fill(ctx, fake_qutebrowser):
    """Run ``qutewarden fill [flags]`` on ``url``; return the exit code."""

    def fill(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
             picker: FakePicker | None = None) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker)

        try:
            return cli.main(["fill", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return fill


def test_several_candidates_are_offered_in_the_picker_with_name_and_username(
        fill, fake_picker, fake_qutebrowser):
    assert fill() == 0
    assert fake_picker.lines == [["GitHub — alice", "GitHub (work) — alice-work"]]


def test_the_picked_candidate_is_filled_with_password_and_totp(fill, fake_qutebrowser):
    assert fill(picker=FakePicker(choices=[1])) == 0
    [js] = fake_qutebrowser.js
    assert f'"password": "{fake_password("github-alt")}"' in js
    assert f'"totp": "{fake_totp("github-alt")}"' in js
    assert '"origin": "https://github.com"' in js
    assert '"mode": "auto"' in js


def test_the_fill_is_announced_before_the_script_is_sent(fill, fake_qutebrowser):
    fill(picker=FakePicker(choices=[1]))
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling GitHub (work) (alice-work)")]
    message = next(i for i, c in enumerate(fake_qutebrowser.commands) if c.startswith("message"))
    jseval = next(i for i, c in enumerate(fake_qutebrowser.commands) if c.startswith("jseval"))
    assert message < jseval


def test_one_candidate_with_auto_fill_is_filled_without_the_picker(
        fill, fake_picker, fake_qutebrowser):
    assert fill("--auto-fill", url=EXAMPLE) == 0
    assert fake_picker.lines == []
    [js] = fake_qutebrowser.js
    assert f'"password": "{fake_password("example")}"' in js


def test_one_candidate_without_auto_fill_still_shows_the_picker(
        fill, fake_picker, fake_qutebrowser):
    assert fill(url=EXAMPLE) == 0
    assert fake_picker.lines == [["Example — bob"]]
    assert len(fake_qutebrowser.js) == 1


def test_several_candidates_with_auto_fill_show_the_picker(fill, fake_picker):
    assert fill("--auto-fill") == 0
    assert fake_picker.lines == [["GitHub — alice", "GitHub (work) — alice-work"]]


NEW_SITE = "https://new-site.test/login"
NEW_ITEM = LoginItem(id="new", name="New site", username="frank",
                     uris=(ItemUri("https://new-site.test"),))


def test_no_candidates_syncs_once_and_tries_again(fill, fake_qutebrowser):
    from qutewarden.backend.fake import FAKE_ITEMS
    backend = FakeBackend(items_after_sync=[*FAKE_ITEMS, NEW_ITEM])
    assert fill(url=NEW_SITE, backend=backend) == 0
    assert backend.calls.count("sync") == 1
    assert backend.calls.index("sync") < backend.calls.index("get_secrets")
    [js] = fake_qutebrowser.js
    assert f'"password": "{fake_password("new")}"' in js


def test_still_no_candidates_after_sync_is_an_error_mentioning_vault(
        fill, fake_picker, fake_qutebrowser):
    backend = FakeBackend()
    assert fill(url=NEW_SITE, backend=backend) == 1
    assert backend.calls.count("sync") == 1
    assert "get_secrets" not in backend.calls
    assert fake_picker.lines == []
    assert fake_qutebrowser.js == []
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error"
    assert "vault" in text
    assert "new-site.test" in text


def test_candidates_found_first_time_do_not_sync(fill):
    backend = FakeBackend()
    fill(backend=backend)
    assert "sync" not in backend.calls


def test_a_cancelled_picker_fills_nothing_and_exits_quietly(fill, fake_qutebrowser):
    backend = FakeBackend()
    assert fill(backend=backend, picker=FakePicker(choices=[None])) == 0
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.js == []
    assert fake_qutebrowser.commands == []


def test_a_locked_vault_is_unlocked_before_listing(fill, fake_qutebrowser):
    backend = FakeBackend(unlocked=False)
    assert fill(backend=backend) == 0
    assert backend.calls.index("unlock") < backend.calls.index("list_logins")
    assert len(fake_qutebrowser.js) == 1


def test_an_unlocked_vault_is_not_unlocked_again(fill):
    backend = FakeBackend()
    fill(backend=backend)
    assert "unlock" not in backend.calls


def test_insert_mode_is_entered_after_the_fill(fill, fake_qutebrowser):
    fill()
    assert fake_qutebrowser.commands[-1] == "mode-enter insert"


def test_insert_mode_can_be_turned_off(fill, fake_qutebrowser):
    fill("--no-insert-mode-after-fill")
    assert "mode-enter insert" not in fake_qutebrowser.commands
    assert len(fake_qutebrowser.js) == 1


@pytest.mark.parametrize("flags, submit", [((), "false"), (("--submit-after-fill",), "true")])
def test_the_form_is_submitted_only_if_configured(fill, fake_qutebrowser, flags, submit):
    fill(*flags)
    [js] = fake_qutebrowser.js
    assert f'"submit": {submit}' in js


@pytest.mark.parametrize("url", ["file:///home/alice/login.html", "qute://settings", ""])
def test_a_non_http_page_is_refused_before_any_secret_is_fetched(fill, fake_qutebrowser, url):
    backend = FakeBackend()
    assert fill(url=url, backend=backend) == 1
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.js == []
    [(level, _)] = fake_qutebrowser.messages
    assert level == "error"


YOUTUBE = "https://www.youtube.com/signin"
GOOGLE = LoginItem(id="google", name="Google", username="me@gmail.com",
                   uris=(ItemUri("https://accounts.google.com"),))
YOUTUBE_ITEM = LoginItem(id="youtube", name="YouTube", username="me",
                         uris=(ItemUri("https://youtube.com"),))


def test_a_candidate_through_equivalent_domains_shows_the_domain_it_matched(
        fill, fake_picker):
    assert fill(url=YOUTUBE, backend=FakeBackend([GOOGLE, YOUTUBE_ITEM])) == 0
    assert fake_picker.lines == [["Google — me@gmail.com (google.com)", "YouTube — me"]]


def test_a_single_candidate_through_equivalent_domains_is_never_auto_filled(
        fill, fake_picker, fake_qutebrowser):
    assert fill("--auto-fill", url=YOUTUBE, backend=FakeBackend([GOOGLE])) == 0
    assert fake_picker.lines == [["Google — me@gmail.com (google.com)"]]
    [js] = fake_qutebrowser.js
    assert f'"password": "{fake_password("google")}"' in js


def test_global_equivalent_domains_can_be_turned_off(fill, fake_picker, fake_qutebrowser):
    assert fill("--no-matching-global-equivalent-domains", url=YOUTUBE,
                backend=FakeBackend([GOOGLE])) == 1
    assert fake_picker.lines == []
    assert fake_qutebrowser.js == []


def test_the_users_own_equivalent_domains_come_from_the_config(ctx, fill, fake_picker):
    config = Path(ctx.environ["XDG_CONFIG_HOME"]) / "qutewarden" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text('[matching]\nequivalent_domains = [["example.com", "example.net"]]\n')
    assert fill(url="https://example.net/") == 0
    assert fake_picker.lines == [["Example — bob (example.com)"]]
