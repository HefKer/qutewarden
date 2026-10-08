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
    assert '"username": null' in js


def test_a_cancelled_picker_saves_and_fills_nothing(generate, fake_qutebrowser):
    backend = FakeBackend()
    assert generate(backend=backend, picker=FakePicker(choices=[None])) == 0
    assert backend.updated == [] and backend.created == []
    assert fake_qutebrowser.commands == []



# --- No Candidates: read the username back from the page (ADR-0004) -------------

NEW_SITE = "https://new-site.test/signup"
NONCE = "0123456789abcdef"
STAGE2 = ("--probe-origin", "https://new-site.test", "--username-probe", NONCE)


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
    found = re.search(r'"probeNonce": "([0-9a-f]+)"', js)
    assert found
    nonce = found.group(1)
    assert len(nonce) == 16
    assert spawned(fake_qutebrowser.commands) == [
        "spawn", "--userscript", argv0, "generate",
        "--probe-origin", "https://new-site.test", "--username-probe", nonce]
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
        ("--config", str(config)), ("--probe-origin", "https://new-site.test")}


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


def _dump(tmp_path, html: str) -> dict[str, str]:
    path = tmp_path / "dump.html"
    path.write_text(html)
    return {"QUTE_HTML": str(path)}


def test_second_run_creates_the_item_with_the_username_from_the_page(
        generate, fake_qutebrowser, tmp_path):
    backend = FakeBackend()
    picker = FakePicker()
    html = (f'<!DOCTYPE html><html data-qutewarden-probe-{NONCE}="frank@mail.test">'
            '<body><input type="email"></body></html>')
    assert generate(*STAGE2, url=NEW_SITE, backend=backend, picker=picker,
                    environ=_dump(tmp_path, html)) == 0
    assert backend.created == [{"name": "new-site.test", "username": "frank@mail.test",
                                "uri": "https://new-site.test", "password": GENERATED}]
    assert picker.prompts == []
    [js] = fake_qutebrowser.js
    assert '"mode": "new_password"' in js
    assert f'"password": "{GENERATED}"' in js
    assert f'"probeNonce": "{NONCE}"' in js
    assert '"username": null' in js
    assert fake_qutebrowser.messages == [
        ("info", "qutewarden: saved new password, filling new-site.test (frank@mail.test)")]
    assert not any(c.startswith("spawn") for c in fake_qutebrowser.commands)


def test_the_second_run_creates_even_when_candidates_exist(generate, tmp_path):
    # Stage 1 already offered the Candidates; the user chose "new Item".
    backend = FakeBackend()
    picker = FakePicker()
    assert generate("--probe-origin", "https://github.com", "--username-probe", NONCE,
                    backend=backend, picker=picker,
                    environ=_dump(tmp_path, "<html></html>")) == 0
    assert picker.prompts == ["Username"]
    assert backend.updated == []
    assert backend.created[0]["name"] == "github.com"
    assert backend.created[0]["uri"] == "https://github.com"


def test_the_new_item_has_no_match_mode(generate, tmp_path):
    backend = FakeBackend()
    generate(*STAGE2, url=NEW_SITE, backend=backend,
             environ=_dump(tmp_path, "<html></html>"))
    [created] = [i for i in backend.items if i.name == "new-site.test"]
    assert [u.mode for u in created.uris] == [None]


@pytest.mark.parametrize("html", [
    "<html><body></body></html>",
    f'<html data-qutewarden-probe-{NONCE}=""></html>',
    '<html data-qutewarden-probe-ffffffffffffffff="mallory"></html>',
])
def test_without_a_username_on_the_page_the_picker_asks_for_one(generate, tmp_path, html):
    backend = FakeBackend()
    picker = FakePicker(text="grace")
    assert generate(*STAGE2, url=NEW_SITE, backend=backend, picker=picker,
                    environ=_dump(tmp_path, html)) == 0
    assert picker.prompts == ["Username"]
    assert backend.created[0]["username"] == "grace"


def test_a_username_from_the_picker_is_also_filled_into_the_page(
        generate, fake_qutebrowser, tmp_path):
    # #16: the fill script sets it on the page's username field if that's empty.
    generate(*STAGE2, url=NEW_SITE, picker=FakePicker(text="grace"),
             environ=_dump(tmp_path, "<html></html>"))
    [js] = fake_qutebrowser.js
    assert '"mode": "new_password"' in js
    assert '"username": "grace"' in js


def test_an_empty_picker_answer_fills_no_username(generate, fake_qutebrowser, tmp_path):
    generate(*STAGE2, url=NEW_SITE, picker=FakePicker(text=""),
             environ=_dump(tmp_path, "<html></html>"))
    [js] = fake_qutebrowser.js
    assert '"username": null' in js


def test_a_missing_dump_also_asks_for_the_username(generate):
    backend = FakeBackend()
    picker = FakePicker(text="grace")
    assert generate(*STAGE2, url=NEW_SITE, backend=backend, picker=picker,
                    environ={"QUTE_HTML": "/nonexistent/qute_html"}) == 0
    assert backend.created[0]["username"] == "grace"


def test_an_empty_answer_creates_the_item_without_a_username(generate, tmp_path):
    backend = FakeBackend()
    assert generate(*STAGE2, url=NEW_SITE, backend=backend,
                    picker=FakePicker(text=""), environ=_dump(tmp_path, "<html></html>")) == 0
    assert backend.created[0]["username"] is None


def test_cancelling_the_username_prompt_saves_and_fills_nothing(
        generate, fake_qutebrowser, tmp_path):
    backend = FakeBackend()
    assert generate(*STAGE2, url=NEW_SITE, backend=backend,
                    picker=FakePicker(text=None),
                    environ=_dump(tmp_path, "<html></html>")) == 0
    assert backend.created == []
    assert fake_qutebrowser.commands == []


def test_a_failed_create_fills_nothing(generate, fake_qutebrowser, tmp_path):
    backend = FakeBackend(fail_save=True)
    assert generate(*STAGE2, url=NEW_SITE, backend=backend,
                    environ=_dump(tmp_path, "<html></html>")) == 1
    assert fake_qutebrowser.js == []
    [(level, _)] = fake_qutebrowser.messages
    assert level == "error"


def test_the_second_run_unlocks_a_locked_vault_before_saving(generate, tmp_path):
    backend = FakeBackend(unlocked=False)
    assert generate(*STAGE2, url=NEW_SITE, backend=backend,
                    environ=_dump(tmp_path, "<html></html>")) == 0
    assert backend.calls.index("unlock") < backend.calls.index("create_login")


def test_a_new_item_that_is_no_candidate_is_saved_but_not_filled(
        generate, fake_qutebrowser, tmp_path):
    # The new Item's URI has no match mode, so matching.default_mode applies;
    # with `never` it isn't a Candidate for the page (Security rule 5).
    backend = FakeBackend()
    html = f'<html data-qutewarden-probe-{NONCE}="frank"></html>'
    assert generate("--matching-default-mode", "never", *STAGE2, url=NEW_SITE,
                    backend=backend, environ=_dump(tmp_path, html)) == 0
    assert [c["name"] for c in backend.created] == ["new-site.test"]
    assert fake_qutebrowser.js == []
    assert "mode-enter insert" not in fake_qutebrowser.commands
    [(level, text)] = fake_qutebrowser.messages
    assert level == "info"
    assert text == ("qutewarden: saved new password for new-site.test (frank); "
                    "not filled, it doesn't match this page")


def test_a_malformed_probe_nonce_is_refused(generate):
    backend = FakeBackend()
    assert generate("--probe-origin", "https://new-site.test", "--username-probe", "x;y",
                    url=NEW_SITE, backend=backend) == 1
    assert backend.created == []


@pytest.mark.parametrize("flags", [
    ("--probe-origin", "https://other.test", "--username-probe", NONCE),
    ("--username-probe", NONCE),
])
def test_the_second_run_aborts_if_the_page_origin_changed(
        generate, fake_qutebrowser, tmp_path, flags):
    # The user switched tabs or navigated between the stages.
    backend = FakeBackend()
    html = f'<html data-qutewarden-probe-{NONCE}="frank"></html>'
    assert generate(*flags, url=NEW_SITE, backend=backend,
                    environ=_dump(tmp_path, html)) == 1
    assert backend.created == [] and backend.updated == []
    assert fake_qutebrowser.js == []
    [(level, text)] = fake_qutebrowser.messages
    assert level == "error"
    assert "page changed" in text
    assert "frank" not in text


def test_the_second_stage_keeps_the_password_in_the_pipe(
        generate, fake_qutebrowser, tmp_path, child_recorder, capfd):
    # The first stage never generates (see the probe test); the no-leak test
    # doesn't reach this second stage, so check it here.
    html = f'<html data-qutewarden-probe-{NONCE}="frank"></html>'
    generate(*STAGE2, url=NEW_SITE, environ=_dump(tmp_path, html))
    out, err = capfd.readouterr()
    assert not any("QWSECRET" in c for c in fake_qutebrowser.commands)
    assert child_recorder.children == []
    assert "QWSECRET" not in out + err
    assert any(GENERATED in js for js in fake_qutebrowser.js)
