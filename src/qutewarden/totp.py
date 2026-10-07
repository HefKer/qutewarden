"""Compute a TOTP code from an Item's seed, locally.

Accepts the same seed formats as rbw (``rbw code``): ``otpauth://totp/...``
URIs (``secret``, ``algorithm`` SHA1/SHA256/SHA512, ``digits``, ``period``),
``steam://<base32>`` (5-character Steam Guard codes) and bare base32. We compute
the code here instead of calling ``rbw code`` so one ``rbw get`` is the only
decryption (each decryption of a Re-prompt item asks for the master password).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

_STEAM_ALPHABET = "23456789BCDFGHJKMNPQRTVWXY"
_ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}


@dataclass(frozen=True)
class _Params:
    key: bytes
    algorithm: str = "SHA1"
    digits: int = 6
    period: int = 30
    steam: bool = False


def totp_code(secret: str, now: float | None = None) -> str:
    """Return the current code for ``secret``. Raises ValueError (secret-free text) if invalid."""
    p = _parse(secret)
    counter = int((time.time() if now is None else now) // p.period)
    mac = hmac.new(p.key, struct.pack(">Q", counter), _ALGORITHMS[p.algorithm]).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF
    if p.steam:
        chars = []
        for _ in range(5):
            value, index = divmod(value, len(_STEAM_ALPHABET))
            chars.append(_STEAM_ALPHABET[index])
        return "".join(chars)
    return str(value % 10**p.digits).zfill(p.digits)


def _parse(secret: str) -> _Params:
    stripped = secret.strip()
    scheme, sep, _ = stripped.partition("://")
    if not sep:
        return _Params(_b32decode(stripped))
    parts = urlsplit(stripped)
    if scheme.lower() == "steam":
        return _Params(_b32decode(parts.netloc), steam=True)
    if scheme.lower() != "otpauth" or parts.netloc.lower() != "totp":
        raise ValueError("TOTP secret URI must be otpauth://totp/... or steam://...")
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    if "secret" not in query:
        raise ValueError("TOTP secret URI has no secret")
    algorithm = query.get("algorithm", "SHA1").upper()
    if algorithm not in _ALGORITHMS:
        raise ValueError("unsupported TOTP algorithm")
    try:
        digits = int(query.get("digits", "6"))
        period = int(query.get("period", "30"))
    except ValueError:
        raise ValueError("TOTP digits/period must be integers") from None
    if not 1 <= digits <= 10 or period < 1:
        raise ValueError("TOTP digits/period out of range")
    return _Params(_b32decode(query["secret"]), algorithm, digits, period)


def _b32decode(text: str) -> bytes:
    cleaned = text.strip().replace(" ", "").rstrip("=").upper()
    try:
        key = base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))
    except (binascii.Error, ValueError):
        raise ValueError("TOTP secret is not valid base32") from None
    if not key:
        raise ValueError("TOTP secret is empty")
    return key
