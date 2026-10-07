"""`generate`: generate a password, save it to the vault, then fill it (#8)."""

from __future__ import annotations

import dataclasses

import pytest

from fakes.picker import FakePicker
from qutewarden import cli
from qutewarden.backend.fake import FakeBackend
from qutewarden.qute import Qute

GITHUB = "https://github.com/login"
EXAMPLE = "https://example.com/signin"
GENERATED = "QWSECRET-generated"


@pytest.fixture
def generate(ctx, fake_qutebrowser):
    """Run ``qutewarden generate [flags]`` on ``url``; return the exit code."""

    def generate(*flags: str, url: str = GITHUB, backend: FakeBackend | None = None,
                 picker: FakePicker | None = None, environ: dict | None = None) -> int:
        env = {**ctx.environ, "QUTE_URL": url, **(environ or {})}

        def make_context(config, e):
            return dataclasses.replace(
                ctx, config=config, environ=e, qute=Qute.from_environ(e),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker)

        try:
            return cli.main(["generate", *flags], environ=env, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return generate


# --- One Candidate ------------------------------------------------------------

def test_one_candidate_is_updated_after_confirming_then_filled(generate, fake_qutebrowser):
    backend = FakeBackend()
    picker = FakePicker()
    assert generate(url=EXAMPLE, backend=backend, picker=picker) == 0
    assert picker.prompts == ["Replace password for bob on Example?"]
    assert backend.updated == [("example", GENERATED)]
    [js] = fake_qutebrowser.js
    assert '"mode": "new_password"' in js
    assert f'"password": "{GENERATED}"' in js
    assert '"origin": "https://example.com"' in js


def test_declining_the_replace_question_saves_and_fills_nothing(generate, fake_qutebrowser):
    backend = FakeBackend()
    assert generate(url=EXAMPLE, backend=backend, picker=FakePicker(confirm=False)) == 0
    assert backend.updated == []
    assert fake_qutebrowser.js == []
    assert fake_qutebrowser.commands == []


def test_a_failed_save_fills_nothing_and_shows_an_error(generate, fake_qutebrowser):
    backend = FakeBackend(fail_save=True)
    assert generate(url=EXAMPLE, backend=backend) == 1
    assert fake_qutebrowser.js == []
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error"
    assert "QWSECRET" not in text


def test_the_fill_is_announced_after_saving_and_before_the_script(generate, fake_qutebrowser):
    generate(url=EXAMPLE)
    assert fake_qutebrowser.messages == [
        ("info", "qutewarden: saved new password, filling Example (bob)")]
    commands = fake_qutebrowser.commands
    assert commands[0].startswith("message-info")
    assert commands[1].startswith("jseval")
    assert commands[-1] == "mode-enter insert"


def test_insert_mode_and_submit_follow_the_settings(generate, fake_qutebrowser):
    generate("--no-insert-mode-after-fill", "--submit-after-fill", url=EXAMPLE)
    assert "mode-enter insert" not in fake_qutebrowser.commands
    [js] = fake_qutebrowser.js
    assert '"submit": true' in js


def test_the_password_comes_from_the_generator_settings(generate, ctx, fake_qutebrowser):
    seen = []
    ctx.generate_password = lambda config: seen.append(config.generator_length) or GENERATED
    generate("--generator-length", "9", url=EXAMPLE)
    assert seen == [9]
