"""`fill`: pick a Candidate and fill the page (#6), against the fake Backend and FIFO."""

from __future__ import annotations

import dataclasses

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
