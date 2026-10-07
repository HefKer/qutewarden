"""Rendering the fill script, without a browser (see test_filljs.py for behaviour)."""

import pytest

from qutewarden.filljs import render_fill_js, render_probe_js

ORIGIN = "https://login.example.test"


def test_unknown_mode_is_refused():
    with pytest.raises(ValueError):
        render_fill_js(expected_origin=ORIGIN, mode="everything", password="QWSECRET-pw")


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
