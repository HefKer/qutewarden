"""`vault`: pick from every Login item; Mismatch fill after confirmation; opt-in copy (#9)."""

from __future__ import annotations

import dataclasses

import pytest

from fakes.picker import FakePicker
from qutewarden import cli
from qutewarden.backend.fake import FakeBackend, fake_password
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"


@pytest.fixture
def vault(ctx, fake_qutebrowser):
    """Run ``qutewarden vault [flags]`` on ``url``; return the exit code."""

    def vault(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
              picker: FakePicker | None = None, clipboard: object = ...) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
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
    assert "Yes" not in sum(picker.lines, [])
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling GitHub (work) (alice-work)")]


def test_a_mismatch_fill_asks_first_showing_the_items_uris_next_to_the_page_origin(
        vault, fake_qutebrowser):
    picker = FakePicker(choices=[5], confirm=True)  # Elsewhere: https://other.test
    assert vault(picker=picker) == 0
    assert picker.prompts[-1] == "Fill Elsewhere (erin) on https://github.com?"
    assert picker.lines[-1] == ["Page: https://github.com", "Item: https://other.test",
                                "Yes", "No"]
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
    assert picker.lines[-1] == ["Page: https://github.com", "Item: https://github.com/login",
                                "Yes", "No"]


def test_a_mismatch_with_an_item_that_has_no_uris_says_so(vault):
    from qutewarden.model import LoginItem
    backend = FakeBackend([LoginItem(id="bare", name="Bare", username="zoe")])
    picker = FakePicker(confirm=False)
    vault(picker=picker, backend=backend)
    assert picker.lines[-1] == ["Page: https://github.com", "Item: (no URIs)", "Yes", "No"]
