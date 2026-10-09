"""`card`: pick a Card item and fill the page's payment form (ADR-0005)."""

from __future__ import annotations

import dataclasses

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.fake import FAKE_CARDS, FakeBackend
from qutewarden.qute import Qute

CHECKOUT = "https://shop.test/checkout"


@pytest.fixture
def card(ctx, fake_qutebrowser):
    """Run ``qutewarden card [flags]`` on ``url``; return the exit code."""

    def card(*flags: str, url: str = CHECKOUT, backend: FakeBackend | None = None,
             picker: FakePicker | None = None) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker)

        try:
            return cli.main(["card", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return card


def test_every_card_item_is_offered_with_brand_and_last_4_digits(card, fake_picker):
    assert card() == 0
    assert fake_picker.prompts == ["Card"]
    assert fake_picker.lines == [["Visa — Visa *4242", "Work card — Mastercard *5454",
                                  "Re-prompt card", "No brand — *0005", "Bare card"]]


def test_the_picked_card_is_filled_with_its_values(card, fake_qutebrowser):
    assert card(picker=FakePicker(choices=[1])) == 0
    [js] = fake_qutebrowser.js
    assert '"mode": "card"' in js
    assert '"origin": "https://shop.test"' in js
    assert '"number": "QWSECRET-5454545454545454"' in js
    assert '"code": "QWSECRET-code-work-card"' in js
    assert '"expMonth": "11", "expYear": "2031"' in js


def test_the_picked_cards_custom_fields_go_into_the_script(card, fake_qutebrowser):
    assert card(picker=FakePicker(choices=[1])) == 0
    [js] = fake_qutebrowser.js
    assert ('{"name": "recovery", "kind": "hidden", "value": "QWSECRET-hidden-work-card"}'
            in js)


def test_the_fill_message_names_the_card_only(card, fake_qutebrowser):
    card(picker=FakePicker(choices=[1]))
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling Work card")]


def test_a_single_card_is_never_auto_filled(card, fake_picker, fake_qutebrowser):
    backend = FakeBackend(cards=[FAKE_CARDS[0]])
    assert card("--auto-fill", backend=backend) == 0
    assert fake_picker.lines == [["Visa — Visa *4242"]]
    assert len(fake_qutebrowser.js) == 1


@pytest.mark.parametrize("flags", [(), ("--submit-after-fill",)])
def test_the_form_is_never_submitted(card, fake_qutebrowser, flags):
    assert card(*flags) == 0
    [js] = fake_qutebrowser.js
    assert '"submit": false' in js
    assert '"submit": true' not in js


def test_insert_mode_follows_the_setting(card, fake_qutebrowser):
    card()
    assert fake_qutebrowser.commands[-1] == "mode-enter insert"


def test_insert_mode_can_be_turned_off(card, fake_qutebrowser):
    card("--no-insert-mode-after-fill")
    assert "mode-enter insert" not in fake_qutebrowser.commands
    assert len(fake_qutebrowser.js) == 1


def test_a_cancelled_picker_fills_nothing(card, fake_qutebrowser):
    backend = FakeBackend()
    assert card(backend=backend, picker=FakePicker(choices=[None])) == 0
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.commands == []


def test_a_locked_vault_is_unlocked_before_listing(card):
    backend = FakeBackend(unlocked=False)
    assert card(backend=backend) == 0
    assert backend.calls.index("unlock") < backend.calls.index("list_cards")


def test_a_vault_without_card_items_is_an_error(card, fake_picker, fake_qutebrowser):
    assert card(backend=FakeBackend(cards=[])) == 1
    assert fake_picker.lines == []
    assert fake_qutebrowser.messages == [("error", "qutewarden: the vault has no Card items")]


def test_a_non_http_page_is_refused_before_any_secret_is_fetched(card, fake_qutebrowser):
    backend = FakeBackend()
    assert card(url="qute://settings", backend=backend) == 1
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.js == []
