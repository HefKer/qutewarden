"""e2e: `card`, a Card item filled into a checkout page (#35, ADR-0005)."""

from __future__ import annotations

import pytest

from e2e.harness import PageServer, Picker, Pinentry, Qutebrowser
from e2e.items import SeededVault

pytestmark = pytest.mark.e2e

CHECKOUT = "http://shop.test/checkout.html"


def _filled(fields: dict[str, str]) -> bool:
    return fields.get("cc-number", "") != ""


def test_card_fills_the_picked_card_into_a_checkout_page_without_submitting(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry,
        vault: SeededVault, unlocked: None):
    page = qb.open(pages, CHECKOUT)
    calls = len(pinentry.calls())
    run = qb.spawn("card", "--submit-after-fill")
    request = picker.choose(vault.card.line)
    run.wait()
    assert request.prompt == "Card"
    # Brand and last 4 digits only; the Re-prompt Card item isn't decrypted to list it.
    assert sorted(request.lines) == ["Card C — Visa *4242", "Card R"]
    assert len(pinentry.calls()) == calls
    fields = page.wait_fields(_filled, "the card fill")
    card = vault.card
    assert {k: fields[k] for k in ("cc-name", "cc-number", "cc-exp", "cc-csc")} == {
        "cc-name": card.cardholder, "cc-number": card.number, "cc-exp": "01/30",
        "cc-csc": card.code}
    assert {k: fields[k] for k in ("first", "last", "email", "phone", "promo")} == dict.fromkeys(
        ("first", "last", "email", "phone", "promo"), "")
    assert run.messages() == [("INFO", "qutewarden: filling Card C")]
    assert run.entered_insert_mode()
    assert page.fields(after=run.finished_at + 0.3) == fields
    assert page.submitted() == 0


def test_a_re_prompt_card_asks_for_the_master_password_only_once_picked(
        qb: Qutebrowser, pages: PageServer, picker: Picker, pinentry: Pinentry,
        vault: SeededVault, unlocked: None):
    page = qb.open(pages, CHECKOUT)
    calls = len(pinentry.calls())
    run = qb.spawn("card")
    request = picker.next()
    assert len(pinentry.calls()) == calls
    picker.answer(request, vault.card_reprompt.line)
    run.wait()
    fields = page.wait_fields(_filled, "the card fill")
    assert fields["cc-number"] == vault.card_reprompt.number
    assert fields["cc-exp"] == "12/31"
    # rbw asks once per protected field it decrypts: the number and the security code.
    assert len(pinentry.calls()) == calls + 2
