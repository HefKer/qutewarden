"""e2e: `fill` in real qutebrowser through real rbw."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from e2e.harness import PageServer, Picker, Pinentry, Qutebrowser, totp_codes, wait_for
from e2e.items import Login, Markers, SeededVault

pytestmark = pytest.mark.e2e

LOGIN = "http://login.example.com/login_single.html"
SINGLE = "http://single.test/login_single.html"


def _filled(fields: dict[str, str]) -> bool:
    return fields.get("password", "") != ""


def test_fill_picks_among_candidates_and_fills_username_and_password(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault, unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("fill")
    # C has match mode never; Re-prompt R is for another site.
    picker.choose(vault.a.line, expect_lines=[vault.a.line, vault.b.line])
    run.wait()
    fields = page.wait_fields(_filled, "the password to be filled")
    assert (fields["username"], fields["password"]) == ("alice", vault.a.password)
    assert run.messages() == [("INFO", "qutewarden: filling Example A (alice)")]
    assert run.entered_insert_mode()


def test_fill_on_a_locked_vault_asks_for_the_master_password_before_the_picker(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry,
        vault: SeededVault, locked: None):
    page = qb.open(pages, LOGIN)
    calls = len(pinentry.calls())
    run = qb.spawn("fill")
    request = picker.next()
    assert len(pinentry.calls()) == calls + 1
    picker.answer(request, vault.b.line)
    run.wait()
    assert page.wait_fields(_filled, "the fill")["password"] == vault.b.password


def test_cancelling_the_picker_fills_nothing(
        qb: Qutebrowser, pages: PageServer, picker: Picker, unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("fill")
    picker.choose(None)
    run.wait()
    assert run.exit_codes == [0]
    assert run.messages() == []
    assert page.fields(after=run.finished_at)["password"] == ""


def test_two_step_login_fills_the_username_then_the_password(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    step1 = qb.open(pages, "http://login.example.com/login_two_step_1.html")
    run = qb.spawn("fill")
    picker.choose(vault.a.line)
    run.wait()
    assert step1.wait_fields(lambda f: f["username"] != "", "the username")["username"] == "alice"

    step2 = qb.open(pages, "http://login.example.com/login_two_step_2.html")
    run = qb.spawn("fill")
    picker.choose(vault.a.line)
    run.wait()
    assert step2.wait_fields(_filled, "the password")["password"] == vault.a.password


def test_fill_on_an_otp_page_fills_the_totp_code(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        markers: Markers, unlocked: None):
    page = qb.open(pages, "http://login.example.com/otp.html")
    run = qb.spawn("fill")
    picker.choose(vault.a.line)
    run.wait()
    code = page.wait_fields(lambda f: f["otp"] != "", "the TOTP code")["otp"]
    markers.add_code(code)
    assert vault.a.totp is not None
    assert code in totp_codes(vault.a.totp)


def test_auto_fill_with_one_candidate_skips_the_picker(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, SINGLE)
    qb.run("fill", "--auto-fill")
    fields = page.wait_fields(_filled, "the fill")
    assert (fields["username"], fields["password"]) == ("sam", vault.single.password)
    assert picker.pending() == []


def test_submit_after_fill_submits_the_form(
        qb: Qutebrowser, pages: PageServer, unlocked: None):
    page = qb.open(pages, SINGLE)
    qb.run("fill", "--auto-fill", "--submit-after-fill")
    wait_for(lambda: page.submitted() == 1, "the form to be submitted")


def test_no_insert_mode_after_fill_stays_in_normal_mode(
        qb: Qutebrowser, pages: PageServer, unlocked: None):
    page = qb.open(pages, SINGLE)
    run = qb.run("fill", "--auto-fill", "--no-insert-mode-after-fill")
    page.wait_fields(_filled, "the fill")
    assert not run.entered_insert_mode()


def test_a_page_without_candidates_names_the_vault_command(
        qb: Qutebrowser, pages: PageServer, unlocked: None):
    qb.open(pages, "http://nothing.test/login_single.html")
    run = qb.run("fill")
    assert run.exit_codes == [1]
    [(level, text)] = run.messages()
    assert level == "ERROR"
    assert "`vault`" in text


def test_fill_on_a_non_http_page_fetches_nothing(
        qb: Qutebrowser, pinentry: Pinentry, locked: None):
    qb.open_internal("qute://version/")
    calls = len(pinentry.calls())
    run = qb.run("fill")
    assert run.exit_codes == [1]
    assert run.messages() == [("ERROR", "qutewarden: not an http(s) page")]
    assert len(pinentry.calls()) == calls


def test_switching_tabs_while_the_picker_is_open_fills_nothing(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    first = qb.open(pages, LOGIN)
    run = qb.spawn("fill")
    request = picker.next()
    other = qb.open(pages, SINGLE, tab=True)
    picker.answer(request, vault.a.line)
    run.wait()
    assert other.fields(after=run.finished_at + 0.3)["password"] == ""
    assert first.fields(after=run.finished_at + 0.3)["password"] == ""


def test_re_prompt_item_asks_for_the_master_password_only_once_picked(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry,
        vault: SeededVault, unlocked: None):
    page = qb.open(pages, "http://reprompt.test/login_single.html")
    calls = len(pinentry.calls())
    run = qb.spawn("fill")
    request = picker.next()
    assert request.lines == [vault.reprompt.line]
    assert len(pinentry.calls()) == calls
    picker.answer(request, vault.reprompt.line)
    run.wait()
    assert page.wait_fields(_filled, "the fill")["password"] == vault.reprompt.password
    assert len(pinentry.calls()) == calls + 1


@pytest.mark.parametrize(("role", "matching", "not_matching"), [
    ("host", "http://a.modes.test/login_single.html", "http://e.modes.test/login_single.html"),
    ("starts_with", "http://b.modes.test/app/login_single.html",
     "http://b.modes.test/other/login_single.html"),
    ("exact", "http://c.modes.test/login_single.html", "http://c.modes.test/x/login_single.html"),
    ("regex", "http://d7.modes.test/login_single.html", "http://dx.modes.test/login_single.html"),
])
def test_each_match_mode_decides_the_candidates(
        qb: Qutebrowser, pages: PageServer, vault: SeededVault, unlocked: None,
        role: str, matching: str, not_matching: str):
    item: Login = getattr(vault, role)
    page = qb.open(pages, matching)
    qb.run("fill", "--auto-fill")
    assert page.wait_fields(_filled, "the fill")["password"] == item.password

    qb.open(pages, not_matching)
    run = qb.run("fill", "--auto-fill")
    assert run.exit_codes == [1]
    assert "no Login item matches" in run.messages()[0][1]


def test_killing_the_userscript_mid_fill_leaves_qutebrowser_responsive(
        qb: Qutebrowser, pages: PageServer, picker: Picker, unlocked: None):
    qb.open(pages, LOGIN)
    run = qb.spawn("fill")
    request = picker.next()
    [pid] = [int(p.parent.name) for p in Path("/proc").glob("[0-9]*/cmdline")
             if _is_qutewarden_fill(p)]
    os.kill(pid, signal.SIGKILL)
    run.wait()
    picker.answer(request, None)
    qb.open(pages, SINGLE)


def _is_qutewarden_fill(cmdline: Path) -> bool:
    try:
        argv = cmdline.read_bytes().split(b"\0")
    except OSError:
        return False
    return any(a.endswith(b"/userscripts/qutewarden") for a in argv) and b"fill" in argv
