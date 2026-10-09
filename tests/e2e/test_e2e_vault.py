"""e2e: `vault`, Mismatch fill and copy."""

from __future__ import annotations

import pytest

from e2e.harness import CLEAR_SECONDS, Displays, PageServer, Picker, Qutebrowser
from e2e.items import SeededVault

pytestmark = pytest.mark.e2e

LOGIN = "http://login.example.com/login_single.html"


def _filled(fields: dict[str, str]) -> bool:
    return fields.get("password", "") != ""


def test_vault_lists_every_login_item_and_fills_a_candidate_without_asking(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("vault")
    request = picker.choose(vault.b.line)
    run.wait()
    # `generate` tests may have added Items; Cards and Identities are never listed.
    assert {item.line for item in vault.logins()} <= set(request.lines)
    assert not set(vault.others) & set(request.lines)
    assert page.wait_fields(_filled, "the fill")["password"] == vault.b.password
    assert run.messages() == [("INFO", "qutewarden: filling Example B (bob)")]


def test_mismatch_fill_shows_the_item_uris_and_fills_only_after_yes(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("vault")
    picker.choose(vault.c_never.line)
    confirm = picker.choose("No")
    run.wait()
    assert confirm.prompt == "Fill Example C (carol)?"
    assert confirm.lines == ["Page: http://login.example.com", "Item: login.example.com",
                             "Yes", "No"]
    assert page.fields(after=run.finished_at)["password"] == ""

    run = qb.spawn("vault")
    picker.choose(vault.c_never.line)
    picker.choose("Yes")
    run.wait()
    assert page.wait_fields(_filled, "the Mismatch fill")["password"] == vault.c_never.password


def test_vault_allow_copy_copies_one_field_and_clears_it(
        qb: Qutebrowser, pages: PageServer, picker: Picker, displays: Displays,
        vault: SeededVault, unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("vault", "--vault-allow-copy")
    picker.choose(vault.a.line)
    menu = picker.choose("Copy password")
    run.wait()
    assert menu.lines == ["Fill", "Copy password", "Copy TOTP", "Copy username"]
    displays.wait_paste("wayland", lambda text: text == vault.a.password, "the password copied")
    copied = (f"qutewarden: copied password for Example A (alice); "
              f"clipboard clears in {CLEAR_SECONDS} s")
    assert run.messages() == [("INFO", copied)]
    assert page.fields(after=run.finished_at)["password"] == ""
    displays.wait_paste("wayland", lambda text: text == "", "the clipboard to be cleared",
                        timeout=CLEAR_SECONDS + 5)


def test_vault_allow_copy_fill_fills_as_without_the_flag(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, LOGIN)
    run = qb.spawn("vault", "--vault-allow-copy")
    picker.choose(vault.b.line)
    menu = picker.choose("Fill")
    run.wait()
    assert menu.lines == ["Fill", "Copy password", "Copy username"]
    assert page.wait_fields(_filled, "the fill")["password"] == vault.b.password
