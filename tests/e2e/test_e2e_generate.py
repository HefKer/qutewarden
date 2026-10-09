"""e2e: `generate`, both stages and replace (ADR-0004).

Each test that creates an Item uses its own host, since the new Item is named after it.
"""

from __future__ import annotations

import json
import re
import string

import pytest

from e2e.harness import PageServer, Picker, Pinentry, Qutebrowser, Rbw
from e2e.items import Markers, SeededVault

pytestmark = pytest.mark.e2e


def _new_password(fields: dict[str, str]) -> bool:
    return fields["password"] != "" and fields["confirm"] != ""


def _type_username(qb: Qutebrowser, username: str) -> None:
    qb.command(f"jseval --quiet document.getElementById('username').value = '{username}'")


def _saved(rbw: Rbw, name: str) -> dict:
    return json.loads(rbw.run("get", "--raw", name).stdout)


def test_generate_without_an_item_probes_the_username_then_saves_and_fills(
        qb: Qutebrowser, pages: PageServer, rbw: Rbw, markers: Markers, unlocked: None):
    page = qb.open(pages, "http://signup1.test/signup.html")
    _type_username(qb, "newbie")
    page.wait_fields(lambda f: f["username"] == "newbie", "the typed username")
    run = qb.run("generate", processes=2)
    assert run.exit_codes == [0, 0]
    spawn = [c for c in run.commands() if c.startswith("spawn --userscript ")]
    assert len(spawn) == 1
    assert re.search(r" generate --probe-origin http://signup1\.test --username-probe "
                     r"[0-9a-f]{16}$", spawn[0])
    fields = page.wait_fields(_new_password, "the new password")
    markers.add(fields["password"])
    assert fields["confirm"] == fields["password"]
    saved = _saved(rbw, "signup1.test")
    assert saved["data"]["username"] == "newbie"
    assert saved["data"]["password"] == fields["password"]
    assert [u["uri"] for u in saved["data"]["uris"]] == ["http://signup1.test"]
    assert ("INFO", "qutewarden: saved new password, filling signup1.test (newbie)"
            ) in run.messages()


def test_generate_flags_reach_the_second_stage(
        qb: Qutebrowser, pages: PageServer, rbw: Rbw, markers: Markers, unlocked: None):
    page = qb.open(pages, "http://signup2.test/signup.html")
    _type_username(qb, "flagged")
    page.wait_fields(lambda f: f["username"] == "flagged", "the typed username")
    qb.run("generate", "--generator-length", "32", "--no-generator-symbols", processes=2)
    password = page.wait_fields(_new_password, "the new password")["password"]
    markers.add(password)
    assert len(password) == 32
    assert set(password) <= set(string.ascii_letters + string.digits)
    assert _saved(rbw, "signup2.test")["data"]["password"] == password


def test_generate_with_an_empty_username_field_asks_for_one(
        qb: Qutebrowser, pages: PageServer, picker: Picker, rbw: Rbw, markers: Markers,
        unlocked: None):
    page = qb.open(pages, "http://signup3.test/signup.html")
    run = qb.spawn("generate", processes=2)
    request = picker.choose("typed-in-picker")
    run.wait()
    assert (request.prompt, request.lines) == ("Username", [])
    fields = page.wait_fields(_new_password, "the new password")
    markers.add(fields["password"])
    assert fields["username"] == "typed-in-picker"
    assert _saved(rbw, "signup3.test")["data"]["username"] == "typed-in-picker"


def test_generate_replaces_the_password_of_the_one_candidate_after_yes(
        qb: Qutebrowser, pages: PageServer, picker: Picker, rbw: Rbw, vault: SeededVault,
        markers: Markers, unlocked: None):
    page = qb.open(pages, "http://replace.test/signup.html")
    before = _saved(rbw, vault.replace.name)["data"]["password"]
    run = qb.spawn("generate")
    confirm = picker.choose("Yes")
    run.wait()
    assert confirm.prompt == "Replace password for zoe on Replace Z?"
    assert confirm.lines == ["Yes", "No"]
    fields = page.wait_fields(_new_password, "the new password")
    markers.add(fields["password"])
    saved = _saved(rbw, vault.replace.name)
    assert saved["data"]["password"] == fields["password"] != before
    assert saved["notes"] == vault.replace.notes
    assert before in rbw.run("history", vault.replace.name).stdout


def test_generate_answered_no_saves_and_fills_nothing(
        qb: Qutebrowser, pages: PageServer, picker: Picker, rbw: Rbw, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, "http://replace.test/signup.html")
    before = _saved(rbw, vault.replace.name)["data"]["password"]
    run = qb.spawn("generate")
    picker.choose("No")
    run.wait()
    assert run.exit_codes == [0]
    assert page.fields(after=run.finished_at)["password"] == ""
    assert _saved(rbw, vault.replace.name)["data"]["password"] == before


def test_generate_with_two_candidates_offers_both_and_a_new_item(
        qb: Qutebrowser, pages: PageServer, picker: Picker, rbw: Rbw, vault: SeededVault,
        markers: Markers, unlocked: None):
    page = qb.open(pages, "http://twocands.test/signup.html")
    _type_username(qb, "third")
    page.wait_fields(lambda f: f["username"] == "third", "the typed username")
    run = qb.spawn("generate", processes=2)
    request = picker.choose("new Item")
    run.wait()
    assert request.prompt == "Replace password"
    assert request.lines == [vault.two_1.line, vault.two_2.line, "new Item"]
    password = page.wait_fields(_new_password, "the new password")["password"]
    markers.add(password)
    assert _saved(rbw, "twocands.test")["data"]["password"] == password
    assert _saved(rbw, vault.two_1.name)["data"]["password"] == vault.two_1.password


def test_generate_fills_nothing_when_saving_fails(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry, rbw: Rbw,
        vault: SeededVault, unlocked: None):
    page = qb.open(pages, "http://replace.test/signup.html")
    run = qb.spawn("generate")
    request = picker.next()
    rbw.run("lock")
    pinentry.mode = "cancel"
    picker.answer(request, "Yes")
    run.wait()
    assert run.exit_codes == [1]
    assert run.messages()[-1][0] == "ERROR"
    assert page.fields(after=run.finished_at)["password"] == ""
