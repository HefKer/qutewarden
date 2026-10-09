"""Seed a Vaultwarden server: register a dummy account and create its Items (ADR-0007).

Neither ``bw`` nor ``rbw`` can register an account or create Card, Identity
or custom-field Items, so this does Bitwarden's client-side crypto itself:
PBKDF2-SHA256 master key, HKDF-expanded enc/mac keys, a random 64-byte user
key and type-2 EncStrings (AES-256-CBC + HMAC-SHA256). The request bodies
follow the Bitwarden web vault; if Vaultwarden stops accepting them, this is
the file to change.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.parse
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives import padding as sympad
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

KDF_ITERATIONS = 600_000


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _enc_string(data: bytes, enc_key: bytes, mac_key: bytes) -> str:
    """A type-2 EncString: ``2.<iv>|<ciphertext>|<mac>``."""
    iv = os.urandom(16)
    padder = sympad.PKCS7(128).padder()
    plain = padder.update(data) + padder.finalize()
    encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    ct = encryptor.update(plain) + encryptor.finalize()
    mac = hmac.new(mac_key, iv + ct, hashlib.sha256).digest()
    return f"2.{_b64(iv)}|{_b64(ct)}|{_b64(mac)}"


def _dec_string(text: str, enc_key: bytes, mac_key: bytes) -> bytes:
    _, rest = text.split(".", 1)
    iv, ct, mac = (base64.b64decode(part) for part in rest.split("|"))
    if not hmac.compare_digest(hmac.new(mac_key, iv + ct, hashlib.sha256).digest(), mac):
        raise ValueError("EncString MAC mismatch")
    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ct) + decryptor.finalize()
    unpadder = sympad.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


class _MasterKey:
    def __init__(self, email: str, password: str) -> None:
        self.key = hashlib.pbkdf2_hmac("sha256", password.encode(), email.lower().encode(),
                                       KDF_ITERATIONS, 32)
        self.password_hash = _b64(hashlib.pbkdf2_hmac("sha256", self.key, password.encode(),
                                                      1, 32))
        self.enc_key = self._expand(b"enc")
        self.mac_key = self._expand(b"mac")

    def _expand(self, info: bytes) -> bytes:
        return HKDFExpand(hashes.SHA256(), 32, info).derive(self.key)


def _request(url: str, data: bytes, headers: Mapping[str, str]) -> Any:
    req = urllib.request.Request(url, data, dict(headers))
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def register(server: str, email: str, password: str) -> None:
    """Create the account (KDF PBKDF2, 600k iterations) with a fresh user key and RSA keypair."""
    master = _MasterKey(email, password)
    user_key = os.urandom(64)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_der = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    private_der = private.private_bytes(
        serialization.Encoding.DER, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    body = {
        "email": email, "name": "e2e", "masterPasswordHash": master.password_hash,
        "masterPasswordHint": None,
        "key": _enc_string(user_key, master.enc_key, master.mac_key),
        "kdf": 0, "kdfIterations": KDF_ITERATIONS,
        "keys": {"publicKey": _b64(public_der),
                 "encryptedPrivateKey": _enc_string(private_der, user_key[:32], user_key[32:])},
    }
    _request(server + "/identity/accounts/register", json.dumps(body).encode(),
             {"Content-Type": "application/json"})


class VaultClient:
    """A logged-in session that creates Items, encrypting every value with the user key."""

    def __init__(self, server: str, email: str, password: str) -> None:
        master = _MasterKey(email, password)
        form = urllib.parse.urlencode({
            "grant_type": "password", "username": email, "password": master.password_hash,
            "scope": "api offline_access", "client_id": "cli", "deviceType": 8,
            "deviceIdentifier": str(uuid.uuid4()), "deviceName": "e2e-seed",
        }).encode()
        token = _request(server + "/identity/connect/token", form,
                         {"Content-Type": "application/x-www-form-urlencoded"})
        user_key = _dec_string(token["Key"], master.enc_key, master.mac_key)
        self._enc_key, self._mac_key = user_key[:32], user_key[32:]
        self._server = server
        self._headers = {"Content-Type": "application/json",
                         "Authorization": "Bearer " + token["access_token"]}

    def encrypt(self, value: str | None) -> str | None:
        if value is None:
            return None
        return _enc_string(value.encode(), self._enc_key, self._mac_key)

    def create_item(self, item: Mapping[str, Any]) -> str:
        """POST an Item whose plaintext strings are already encrypted; returns its id."""
        created = _request(self._server + "/api/ciphers", json.dumps(item).encode(),
                           self._headers)
        return created["id"]
