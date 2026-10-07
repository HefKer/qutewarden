"""`totp`: pick a Candidate and fill (or copy) its TOTP code (#7)."""

from __future__ import annotations

import dataclasses

import pytest

from fakes.picker import FakePicker
from qutewarden import cli
from qutewarden.backend.fake import FakeBackend, fake_password, fake_totp
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"
NO_TOTP = "https://no-totp.test/login"


@pytest.fixture
def totp(ctx, fake_qutebrowser):
    """Run ``qutewarden totp [flags]`` on ``url``; return the exit code."""

    def totp(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
             picker: FakePicker | None = None, clipboard: object = ...) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker,
                clipboard=ctx.clipboard if clipboard is ... else clipboard)

        try:
            return cli.main(["totp", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return totp


def test_the_picked_candidates_totp_code_is_filled_into_the_otp_field(totp, fake_qutebrowser):
    assert totp(picker=FakePicker(choices=[1])) == 0
    [js] = fake_qutebrowser.js
    assert '"mode": "otp"' in js
    assert f'"totp": "{fake_totp("github-alt")}"' in js
    assert '"origin": "https://github.com"' in js


def test_the_password_does_not_travel_with_the_totp_code(totp, fake_qutebrowser):
    totp()
    [js] = fake_qutebrowser.js
    assert fake_password("github") not in js


def test_an_item_without_totp_shows_a_clear_message_and_fills_nothing(totp, fake_qutebrowser):
    assert totp(url=NO_TOTP) == 1
    assert fake_qutebrowser.js == []
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error"
    assert text == "qutewarden: No TOTP (carol) has no TOTP"


def test_an_item_whose_backend_returns_no_code_shows_the_same_message(totp, fake_qutebrowser):
    from qutewarden.backend.fake import FAKE_ITEMS
    # The listing says it has TOTP but the vault has no code (e.g. stale list).
    stale = [dataclasses.replace(i, has_totp=True) if i.id == "no-totp" else i
             for i in FAKE_ITEMS]
    backend = FakeBackend(stale)
    backend.get_secrets = lambda item_id: FakeBackend().get_secrets(item_id)
    assert totp(url=NO_TOTP, backend=backend) == 1
    assert fake_qutebrowser.js == []
    assert fake_qutebrowser.messages == [("error", "qutewarden: No TOTP (carol) has no TOTP")]


def test_with_totp_clipboard_the_code_is_copied_instead_of_filled(
        totp, fake_qutebrowser, fake_clipboard):
    assert totp("--totp-clipboard", "--totp-clipboard-clear-seconds", "12") == 0
    assert fake_clipboard.copies == [(fake_totp("github"), 12)]
    assert fake_qutebrowser.js == []
    assert "mode-enter insert" not in fake_qutebrowser.commands
    assert fake_qutebrowser.messages == [
        ("info", "qutewarden: copied TOTP for GitHub (alice); clipboard clears in 12 s")]


def test_with_totp_clipboard_but_no_clipboard_tool_it_is_an_error(totp, fake_qutebrowser):
    backend = FakeBackend()
    assert totp("--totp-clipboard", backend=backend, clipboard=None) == 1
    assert "get_secrets" not in backend.calls
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error"
    assert "wl-copy" in text and "xclip" in text
