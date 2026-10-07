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
from importlib import resources
from typing import Literal, get_args

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
) -> str:
    """Return the fill script for a page whose origin must be ``expected_origin``.

    ``expected_origin`` is ``scheme://host[:port]`` exactly as the page's
    ``location.origin``; on any other origin the script does nothing.
    """
    if mode not in _FILL_MODES:
        raise ValueError(f"unknown fill mode: {mode!r}")
    return _render({
        "origin": expected_origin,
        "mode": mode,
        "username": username,
        "password": password,
        "totp": totp,
        "submit": submit,
        "probeNonce": probe_nonce,
    })
