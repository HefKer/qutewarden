"""Password generator for `generate` (#8), using the ``secrets`` module.

Character classes match Bitwarden's generator: A–Z, a–z, 0–9 and ``!@#$%^&*``.
Every enabled class appears at least once.
"""

from __future__ import annotations

import secrets
import string

from qutewarden.config import Config, ConfigError

SYMBOLS = "!@#$%^&*"


def generate_password(*, length: int = 24, uppercase: bool = True, lowercase: bool = True,
                      digits: bool = True, symbols: bool = True) -> str:
    classes = [chars for enabled, chars in (
        (uppercase, string.ascii_uppercase), (lowercase, string.ascii_lowercase),
        (digits, string.digits), (symbols, SYMBOLS)) if enabled]
    if not classes:
        raise ConfigError("generator: enable at least one character class")
    if length < len(classes):
        raise ConfigError(f"generator.length must be at least {len(classes)}")
    alphabet = "".join(classes)
    chars = [secrets.choice(c) for c in classes]
    chars += [secrets.choice(alphabet) for _ in range(length - len(chars))]
    # Fisher–Yates with a CSPRNG so the guaranteed characters aren't always first.
    for i in range(len(chars) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        chars[i], chars[j] = chars[j], chars[i]
    return "".join(chars)


def generate_password_from_config(config: Config) -> str:
    return generate_password(length=config.generator_length,
                             uppercase=config.generator_uppercase,
                             lowercase=config.generator_lowercase,
                             digits=config.generator_digits,
                             symbols=config.generator_symbols)
