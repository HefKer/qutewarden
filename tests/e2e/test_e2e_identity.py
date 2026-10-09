"""e2e: `identity`, an Identity item filled into an address page (#36, ADR-0005)."""

from __future__ import annotations

import pytest

from e2e.harness import PageServer, Picker, Qutebrowser
from e2e.items import SeededVault

pytestmark = pytest.mark.e2e

ADDRESS = "http://address.test/address.html"


def test_identity_fills_the_picked_identity_into_an_address_page_without_submitting(
        qb: Qutebrowser, pages: PageServer, picker: Picker, vault: SeededVault,
        unlocked: None):
    page = qb.open(pages, ADDRESS)
    run = qb.spawn("identity", "--submit-after-fill")
    request = picker.choose(vault.identity.name)
    run.wait()
    assert request.prompt == "Identity"
    assert request.lines == ["Ident I"]
    fields = page.wait_fields(lambda f: f.get("postal-code", "") != "", "the identity fill")
    v = vault.identity.values
    assert {k: fields[k] for k in (
        "title", "given-name", "additional-name", "family-name", "address-line1",
        "address-line2", "address-level2", "address-level1", "postal-code", "country", "email",
        "tel", "username")} == {
        "title": v["title"], "given-name": v["firstName"], "additional-name": v["middleName"],
        "family-name": v["lastName"], "address-line1": v["address1"],
        "address-line2": v["address2"], "address-level2": v["city"],
        "address-level1": v["state"], "postal-code": v["postalCode"], "country": "US",
        "email": v["email"], "tel": v["phone"], "username": v["username"]}
    # rbw 1.15 doesn't pass the company on; nothing else is touched.
    assert {k: fields[k] for k in ("organization", "cc-number", "gift")} == dict.fromkeys(
        ("organization", "cc-number", "gift"), "")
    # The name only: Identity values count as secrets in messages (Security rule 6).
    assert run.messages() == [("INFO", "qutewarden: filling Ident I")]
    assert run.entered_insert_mode()
    assert page.fields(after=run.finished_at + 0.3) == fields
    assert page.submitted() == 0
