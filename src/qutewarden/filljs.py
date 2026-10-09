"""Render the fill JavaScript that qutebrowser runs in the page.

The script body lives in ``js/fill.js`` (package data). It defines
``qutewardenFill(a)``; we append one call with the arguments as a JSON
literal and wrap everything in an IIFE, so nothing leaks into the world's
globals and nothing comes back as a ``jseval`` result.

The rendered script contains secrets: it must only ever travel through the
fill route (ADR-0002), never through a qutebrowser command.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from importlib import resources
from typing import Literal, get_args

from qutewarden.model import CardSecrets, CustomField, IdentitySecrets

FillMode = Literal["auto", "login", "otp", "new_password"]

_FILL_MODES = frozenset(get_args(FillMode))


def _fill_script() -> str:
    return resources.files("qutewarden").joinpath("js/fill.js").read_text(encoding="utf-8")


def _render(args: dict[str, object]) -> str:
    # ensure_ascii also escapes U+2028/U+2029, which some JS parsers reject in strings.
    call = f"qutewardenFill({json.dumps(args, ensure_ascii=True)});"
    return f"(function () {{\n{_fill_script()}\n{call}\n}})();\nvoid 0;\n"


def render_fill_js(
    *,
    expected_origin: str,
    mode: FillMode,
    username: str | None = None,
    password: str | None = None,
    totp: str | None = None,
    submit: bool = False,
    probe_nonce: str | None = None,
    fields: Sequence[CustomField] = (),
) -> str:
    """Return the fill script for a page whose origin must be ``expected_origin``.

    ``expected_origin`` is ``scheme://host[:port]`` exactly as the page's
    ``location.origin``; on any other origin the script does nothing.
    ``fields`` are the Item's Custom fields; they fill the document the built-in
    fill chose, never a field it filled, and before any submit.
    """
    if mode not in _FILL_MODES:
        raise ValueError(f"unknown fill mode: {mode!r}")
    if probe_nonce is not None:
        _check_nonce(probe_nonce)
    return _render({
        "origin": expected_origin,
        "mode": mode,
        "username": username,
        "password": password,
        "totp": totp,
        "submit": submit,
        "probeNonce": probe_nonce,
        "fields": _fields(fields),
    })


def render_card_fill_js(*, expected_origin: str, card: CardSecrets) -> str:
    """Return the script that fills a Card item into the page's payment form.

    It never submits the form (ADR-0005). The expiry is passed as a 2-digit
    month and a 4-digit year; the script formats it for each field. Values the
    Item doesn't have (or can't be read, like a month of 13) are null, and the
    script leaves their fields alone.
    """
    given, family = _split_name(card.cardholder_name)
    return _render({
        "origin": expected_origin,
        "mode": "card",
        "card": {
            "name": card.cardholder_name or None,
            "givenName": given,
            "familyName": family,
            "number": card.number or None,
            "brand": card.brand or None,
            "expMonth": _month(card.exp_month),
            "expYear": _year(card.exp_year),
            "code": card.code or None,
        },
        "fields": _fields(card.fields),
        "submit": False,
    })


def render_identity_fill_js(*, expected_origin: str, identity: IdentitySecrets) -> str:
    """Return the script that fills an Identity item into the page's address form.

    It never submits the form (ADR-0005). Only the values some field kind
    takes are passed (not the SSN, licence or passport number); values the
    Item doesn't have are null, and the script leaves their fields alone.
    """
    lines = [line for line in (identity.address1, identity.address2, identity.address3) if line]
    return _render({
        "origin": expected_origin,
        "mode": "identity",
        "identity": {
            "honorificPrefix": identity.title or None,
            "givenName": identity.first_name or None,
            "additionalName": identity.middle_name or None,
            "familyName": identity.last_name or None,
            "organization": identity.company or None,
            "streetAddress": ", ".join(lines) or None,
            "addressLine1": identity.address1 or None,
            "addressLine2": identity.address2 or None,
            "addressLine3": identity.address3 or None,
            "addressLevel1": identity.state or None,
            "addressLevel2": identity.city or None,
            "postalCode": identity.postal_code or None,
            "country": identity.country or None,
            "email": identity.email or None,
            "tel": identity.phone or None,
            "username": identity.username or None,
        },
        "fields": _fields(identity.fields),
        "submit": False,
    })


def _fields(fields: Sequence[CustomField]) -> list[dict[str, str]]:
    """The Custom fields that have a value, for the script (``kind`` as Bitwarden names it)."""
    return [{"name": f.name, "kind": f.kind.value, "value": f.value}
            for f in fields if f.value is not None]


def _split_name(name: str | None) -> tuple[str | None, str | None]:
    """(given name, family name): the last word is the family name."""
    words = (name or "").split()
    if len(words) < 2:
        return (words[0] if words else None), None
    return " ".join(words[:-1]), words[-1]


def _month(text: str | None) -> str | None:
    text = (text or "").strip()
    if not text.isdigit() or not 1 <= int(text) <= 12:
        return None
    return f"{int(text):02d}"


def _year(text: str | None) -> str | None:
    text = (text or "").strip()
    if not text.isdigit() or len(text) not in (2, 4):
        return None
    return text if len(text) == 4 else f"20{text}"


def render_probe_js(*, expected_origin: str, nonce: str) -> str:
    """Return a secret-free script that copies the page's username into the DOM.

    It writes the username field's value to the attribute
    ``data-qutewarden-probe-<nonce>`` on ``<html>``, where qutebrowser's
    ``QUTE_HTML`` dump for the next userscript run can read it (#8).
    """
    _check_nonce(nonce)
    return _render({
        "origin": expected_origin,
        "mode": "probe",
        "username": None,
        "password": None,
        "totp": None,
        "submit": False,
        "probeNonce": nonce,
    })


def _check_nonce(nonce: str) -> None:
    # Becomes part of an attribute name: keep it to a known-safe alphabet.
    if not re.fullmatch(r"[0-9a-f]{1,64}", nonce):
        raise ValueError("probe nonce must be lowercase hex")
