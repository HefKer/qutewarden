"""e2e: `totp`, filled and copied."""

from __future__ import annotations

import time

import pytest

from e2e.harness import (
    CLEAR_SECONDS,
    Displays,
    PageServer,
    Picker,
    Pinentry,
    Qutebrowser,
    totp_codes,
)
from e2e.items import Markers, SeededVault

pytestmark = pytest.mark.e2e

OTP = "http://login.example.com/otp.html"
CLIPBOARDS = [("qutewarden", "wayland"), ("qutewarden-x11", "x11")]


def test_totp_fills_the_current_code(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        markers: Markers, unlocked: None):
    page = qb.open(pages, OTP)
    run = qb.spawn("totp")
    request = picker.choose(vault.a.line)
    run.wait()
    assert request.prompt == "TOTP"
    code = page.wait_fields(lambda f: f["otp"] != "", "the TOTP code")["otp"]
    markers.add_code(code)
    assert vault.a.totp is not None
    assert code in totp_codes(vault.a.totp)
    assert run.messages() == [("INFO", "qutewarden: filling TOTP for Example A (alice)")]


@pytest.mark.parametrize(("script", "kind"), CLIPBOARDS)
def test_totp_clipboard_copies_the_code_and_clears_it(
        qb: Qutebrowser, pages: PageServer, picker: Picker, displays: Displays,
        vault: SeededVault, markers: Markers, unlocked: None, script: str, kind: str):
    page = qb.open(pages, OTP)
    run = qb.spawn("totp", "--totp-clipboard", script=script)
    picker.choose(vault.a.line)
    run.wait()
    assert vault.a.totp is not None
    codes = totp_codes(vault.a.totp)
    code = displays.wait_paste(kind, lambda text: text in codes, "the code copied")
    markers.add_code(code)
    copied = (f"qutewarden: copied TOTP for Example A (alice); "
              f"clipboard clears in {CLEAR_SECONDS} s")
    assert run.messages() == [("INFO", copied)]
    assert page.fields(after=run.finished_at)["otp"] == ""
    displays.wait_paste(kind, lambda text: text == "", "the clipboard to be cleared",
                        timeout=CLEAR_SECONDS + 5)


@pytest.mark.parametrize(("script", "kind"), CLIPBOARDS)
def test_totp_clipboard_leaves_a_later_copy_alone(
        qb: Qutebrowser, pages: PageServer, picker: Picker, displays: Displays,
        vault: SeededVault, markers: Markers, unlocked: None, script: str, kind: str):
    qb.open(pages, OTP)
    run = qb.spawn("totp", "--totp-clipboard", script=script)
    picker.choose(vault.a.line)
    run.wait()
    assert vault.a.totp is not None
    codes = totp_codes(vault.a.totp)
    markers.add_code(displays.wait_paste(kind, lambda text: text in codes, "the code copied"))
    displays.copy(kind, "copied by the user")
    time.sleep(CLEAR_SECONDS + 1.5)
    assert displays.paste(kind) == "copied by the user"


def test_totp_for_an_item_without_totp_says_so(
        qb: Qutebrowser, pages: PageServer, unlocked: None):
    qb.open(pages, "http://single.test/otp.html")
    run = qb.run("totp", "--auto-fill")
    assert run.exit_codes == [1]
    assert run.messages() == [("ERROR", "qutewarden: Single S (sam) has no TOTP")]


def test_totp_clipboard_without_a_clipboard_tool_fails_before_any_secret_is_fetched(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry,
        unlocked: None):
    qb.open(pages, "http://reprompt.test/otp.html")
    calls = len(pinentry.calls())
    run = qb.run("totp", "--totp-clipboard", script="qutewarden-noclip")
    assert run.exit_codes == [1]
    [(level, text)] = run.messages()
    assert level == "ERROR"
    assert text.startswith("qutewarden: no clipboard tool found")
    assert len(pinentry.calls()) == calls
    assert picker.pending() == []
