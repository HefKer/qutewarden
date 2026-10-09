"""Rendering the fill script, without a browser (see test_filljs.py for behaviour)."""

import pytest

from qutewarden.filljs import (
    render_card_fill_js,
    render_fill_js,
    render_identity_fill_js,
    render_probe_js,
)
from qutewarden.model import CardSecrets, IdentitySecrets

ORIGIN = "https://login.example.test"


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        render_fill_js(expected_origin=ORIGIN, password="QWSECRET-pw",
                       mode="everything")  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("nonce", ["", "0123ABCD", "x-y", "ab cd", "ab'cd"])
def test_probe_nonce_must_be_lowercase_hex(nonce):
    with pytest.raises(ValueError):
        render_probe_js(expected_origin=ORIGIN, nonce=nonce)
    with pytest.raises(ValueError):
        render_fill_js(expected_origin=ORIGIN, mode="new_password", password="p",
                       probe_nonce=nonce)


def test_values_are_embedded_as_inert_json_strings():
    nasty = 'p"); alert(1); (" </script>'
    js = render_fill_js(expected_origin=ORIGIN, mode="login", password=nasty)
    assert 'alert(1); ("' not in js
    assert " " not in js
    assert "\\u2028" in js


def test_probe_script_has_no_value_slots():
    js = render_probe_js(expected_origin=ORIGIN, nonce="0123abcd")
    assert '"password": null' in js
    assert '"totp": null' in js
    assert '"username": null' in js


@pytest.mark.parametrize(("month", "year", "expected"), [
    ("3", "2030", '"expMonth": "03", "expYear": "2030"'),
    ("12", "31", '"expMonth": "12", "expYear": "2031"'),
    (" 07 ", "2029", '"expMonth": "07", "expYear": "2029"'),
    ("13", "203", '"expMonth": null, "expYear": null'),
    (None, "", '"expMonth": null, "expYear": null'),
])
def test_card_expiry_is_passed_as_2_digit_month_and_4_digit_year(month, year, expected):
    js = render_card_fill_js(expected_origin=ORIGIN,
                             card=CardSecrets(exp_month=month, exp_year=year))
    assert expected in js


def test_card_script_never_asks_to_submit():
    js = render_card_fill_js(expected_origin=ORIGIN, card=CardSecrets(number="4242"))
    assert '"mode": "card"' in js
    assert '"submit": false' in js


def test_identity_script_never_asks_to_submit():
    js = render_identity_fill_js(expected_origin=ORIGIN,
                                 identity=IdentitySecrets(first_name="Alice"))
    assert '"mode": "identity"' in js
    assert '"submit": false' in js


def test_identity_street_address_joins_the_address_lines_it_has():
    js = render_identity_fill_js(expected_origin=ORIGIN, identity=IdentitySecrets(
        address1="1 Main St", address3="Floor 3"))
    assert '"streetAddress": "1 Main St, Floor 3"' in js
    assert '"addressLine2": null' in js


def test_identity_numbers_no_field_takes_are_left_out_of_the_script():
    js = render_identity_fill_js(expected_origin=ORIGIN, identity=IdentitySecrets(
        ssn="SSN-1", license_number="LIC-1", passport_number="PASS-1"))
    assert not any(value in js for value in ("SSN-1", "LIC-1", "PASS-1"))
