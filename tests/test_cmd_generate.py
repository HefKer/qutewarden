"""`generate`: generate a password, save it to the vault, then fill it (#8)."""

from __future__ import annotations

import dataclasses
import re
import shlex
import sys

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


# --- Several Candidates -------------------------------------------------------

def test_several_candidates_offer_each_item_and_a_new_item(generate, fake_picker):
    generate()
    assert fake_picker.lines[0] == ["GitHub — alice", "GitHub (work) — alice-work", "new Item"]


def test_the_picked_candidate_is_updated_and_filled(generate, fake_qutebrowser):
    backend = FakeBackend()
    assert generate(backend=backend, picker=FakePicker(choices=[1])) == 0
    assert backend.updated == [("github-alt", GENERATED)]
    assert backend.created == []
    [js] = fake_qutebrowser.js
    assert f'"password": "{GENERATED}"' in js
    assert '"username": "alice-work"' in js


def test_a_cancelled_picker_saves_and_fills_nothing(generate, fake_qutebrowser):
    backend = FakeBackend()
    assert generate(backend=backend, picker=FakePicker(choices=[None])) == 0
    assert backend.updated == [] and backend.created == []
    assert fake_qutebrowser.commands == []



# --- No Candidates: read the username back from the page (ADR-0004) -------------

NEW_SITE = "https://new-site.test/signup"
NONCE = "0123456789abcdef"


@pytest.fixture
def argv0(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["/opt/bin/qutewarden", "generate"])
    return "/opt/bin/qutewarden"


def spawned(commands: list[str]) -> list[str]:
    [line] = [c for c in commands if c.startswith("spawn ")]
    return shlex.split(line)


def test_no_candidates_probes_the_page_and_respawns_without_saving(
        generate, ctx, fake_qutebrowser, argv0):
    backend = FakeBackend()
    ctx.generate_password = lambda config: pytest.fail("generated before the second run")
    assert generate(url=NEW_SITE, backend=backend) == 0
    assert backend.created == [] and backend.updated == []
    [js] = fake_qutebrowser.js
    assert "QWSECRET" not in js
    assert '"mode": "probe"' in js
    assert '"origin": "https://new-site.test"' in js
    nonce = re.search(r'"probeNonce": "([0-9a-f]+)"', js).group(1)
    assert len(nonce) == 16
    assert spawned(fake_qutebrowser.commands) == [
        "spawn", "--userscript", argv0, "generate", "--username-probe", nonce]
    kinds = [c.split()[0] for c in fake_qutebrowser.commands]
    assert kinds == ["jseval", "spawn"]


def test_the_second_run_keeps_the_settings_flags(generate, fake_qutebrowser, argv0, tmp_path):
    config = tmp_path / "other.toml"
    config.write_text("")
    generate("--generator-length", "9", "--no-generator-symbols", "--submit-after-fill",
             "--picker", "rofi -dmenu -i", "--config", str(config), url=NEW_SITE)
    argv = spawned(fake_qutebrowser.commands)
    assert argv[:4] == ["spawn", "--userscript", argv0, "generate"]
    flags = argv[4:]
    assert flags[-2] == "--username-probe"
    assert set(_pairs(flags[:-2])) == {
        ("--generator-length", "9"), ("--no-generator-symbols", None),
        ("--submit-after-fill", None), ("--picker", "rofi -dmenu -i"),
        ("--config", str(config))}


def _pairs(flags: list[str]):
    i = 0
    while i < len(flags):
        if i + 1 < len(flags) and not flags[i + 1].startswith("--"):
            yield flags[i], flags[i + 1]
            i += 2
        else:
            yield flags[i], None
            i += 1


def test_choosing_new_item_among_several_candidates_probes_the_page(
        generate, fake_qutebrowser, argv0):
    backend = FakeBackend()
    assert generate(backend=backend, picker=FakePicker(choices=[2])) == 0
    assert backend.created == [] and backend.updated == []
    assert spawned(fake_qutebrowser.commands)[-2] == "--username-probe"
