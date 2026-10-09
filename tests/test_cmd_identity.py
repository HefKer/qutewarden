"""`identity`: pick an Identity item and fill the page's address form (ADR-0005)."""

from __future__ import annotations

import dataclasses

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.fake import FAKE_IDENTITIES, FakeBackend
from qutewarden.qute import Qute

SIGNUP = "https://shop.test/address"


@pytest.fixture
def identity(ctx, fake_qutebrowser):
    """Run ``qutewarden identity [flags]`` on ``url``; return the exit code."""

    def identity(*flags: str, url: str = SIGNUP, backend: FakeBackend | None = None,
                 picker: FakePicker | None = None) -> int:
        environ = {**ctx.environ, "QUTE_URL": url}

        def make_context(config, env):
            return dataclasses.replace(
                ctx, config=config, environ=env, qute=Qute.from_environ(env),
                backend=backend if backend is not None else ctx.backend,
                picker=picker if picker is not None else ctx.picker)

        try:
            return cli.main(["identity", *flags], environ=environ, make_context=make_context)
        finally:
            fake_qutebrowser.close()

    return identity


def test_every_identity_item_is_offered_by_name(identity, fake_picker):
    assert identity() == 0
    assert fake_picker.prompts == ["Identity"]
    assert fake_picker.lines == [["Me", "Work identity", "Re-prompt identity"]]


def test_the_picked_identitys_custom_fields_go_into_the_script(identity, fake_qutebrowser):
    assert identity(picker=FakePicker(choices=[0])) == 0
    [js] = fake_qutebrowser.js
    assert '{"name": "team", "kind": "text", "value": "QWSECRET-text-me"}' in js


def test_the_picked_identity_is_filled_with_its_values(identity, fake_qutebrowser):
    assert identity(picker=FakePicker(choices=[0])) == 0
    [js] = fake_qutebrowser.js
    assert '"mode": "identity"' in js
    assert '"origin": "https://shop.test"' in js
    assert '"givenName": "QWSECRET-Alice"' in js
    assert '"postalCode": "QWSECRET-62701"' in js
    assert '"country": "QWSECRET-US"' in js


def test_values_no_field_kind_takes_never_reach_the_page(identity, fake_qutebrowser):
    identity(picker=FakePicker(choices=[0]))
    [js] = fake_qutebrowser.js
    assert "000-00-0000" not in js  # the SSN


def test_the_fill_message_names_the_identity_only(identity, fake_qutebrowser):
    identity(picker=FakePicker(choices=[1]))
    assert fake_qutebrowser.messages == [("info", "qutewarden: filling Work identity")]


def test_a_single_identity_is_never_auto_filled(identity, fake_picker, fake_qutebrowser):
    backend = FakeBackend(identities=[FAKE_IDENTITIES[0]])
    assert identity("--auto-fill", backend=backend) == 0
    assert fake_picker.lines == [["Me"]]
    assert len(fake_qutebrowser.js) == 1


@pytest.mark.parametrize("flags", [(), ("--submit-after-fill",)])
def test_the_form_is_never_submitted(identity, fake_qutebrowser, flags):
    assert identity(*flags) == 0
    [js] = fake_qutebrowser.js
    assert '"submit": false' in js
    assert '"submit": true' not in js


def test_insert_mode_follows_the_setting(identity, fake_qutebrowser):
    identity()
    assert fake_qutebrowser.commands[-1] == "mode-enter insert"


def test_insert_mode_can_be_turned_off(identity, fake_qutebrowser):
    identity("--no-insert-mode-after-fill")
    assert "mode-enter insert" not in fake_qutebrowser.commands
    assert len(fake_qutebrowser.js) == 1


def test_a_cancelled_picker_fills_nothing(identity, fake_qutebrowser):
    backend = FakeBackend()
    assert identity(backend=backend, picker=FakePicker(choices=[None])) == 0
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.commands == []


def test_a_locked_vault_is_unlocked_before_listing(identity):
    backend = FakeBackend(unlocked=False)
    assert identity(backend=backend) == 0
    assert backend.calls.index("unlock") < backend.calls.index("list_identities")


def test_a_vault_without_identity_items_is_an_error(identity, fake_picker, fake_qutebrowser):
    assert identity(backend=FakeBackend(identities=[])) == 1
    assert fake_picker.lines == []
    assert fake_qutebrowser.messages == [
        ("error", "qutewarden: the vault has no Identity items")]


def test_a_non_http_page_is_refused_before_any_secret_is_fetched(identity, fake_qutebrowser):
    backend = FakeBackend()
    assert identity(url="qute://settings", backend=backend) == 1
    assert "get_secrets" not in backend.calls
    assert fake_qutebrowser.js == []
