"""Password generator (#8): the `generator.*` settings decide length and character classes."""

from __future__ import annotations

import string

import pytest

from qutewarden.config import ConfigError, load_config
from qutewarden.generator import generate_password, generate_password_from_config

SYMBOLS = "!@#$%^&*"


def test_defaults_give_24_characters_from_every_class():
    for _ in range(50):
        pw = generate_password()
        assert len(pw) == 24
        assert any(c in string.ascii_uppercase for c in pw)
        assert any(c in string.ascii_lowercase for c in pw)
        assert any(c in string.digits for c in pw)
        assert any(c in SYMBOLS for c in pw)


def test_only_enabled_classes_are_used():
    for _ in range(50):
        pw = generate_password(length=12, uppercase=False, symbols=False)
        assert len(pw) == 12
        assert set(pw) <= set(string.ascii_lowercase + string.digits)
        assert any(c in string.digits for c in pw)


def test_digits_only():
    pw = generate_password(length=6, uppercase=False, lowercase=False, symbols=False)
    assert len(pw) == 6 and pw.isdigit()


def test_passwords_differ():
    assert len({generate_password() for _ in range(20)}) == 20


def test_no_class_enabled_is_a_config_error():
    with pytest.raises(ConfigError):
        generate_password(uppercase=False, lowercase=False, digits=False, symbols=False)


def test_from_config_uses_generator_settings():
    config = load_config(None, {"generator_length": 8, "generator_lowercase": False,
                                "generator_symbols": False, "generator_uppercase": False})
    pw = generate_password_from_config(config)
    assert len(pw) == 8 and pw.isdigit()
