"""Settings: defaults < TOML file < command-line flags.

``SETTINGS`` is the single source of truth for TOML keys, flags, defaults and
``Config`` attributes.
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

from qutewarden.errors import QutewardenError
from qutewarden.model import MatchMode


class ConfigError(QutewardenError):
    """Unknown key, wrong type or invalid value in the config."""


@dataclass(frozen=True)
class Setting:
    key: str  # dotted TOML key, e.g. "generator.length"
    attr: str  # Config attribute, e.g. "generator_length"
    type: type  # bool | int | str | MatchMode | tuple (picker)
    default: object
    help: str

    @property
    def flag(self) -> str:
        return "--" + self.key.replace(".", "-").replace("_", "-")


SETTINGS: tuple[Setting, ...] = (
    Setting("picker", "picker", tuple, None,
            "dmenu-style picker command (default: fuzzel --dmenu on Wayland, rofi -dmenu on X11)"),
    Setting("auto_fill", "auto_fill", bool, False,
            "fill without asking when exactly one Candidate matches"),
    Setting("backend", "backend", str, "rbw", "vault backend (only rbw in v1)"),
    Setting("insert_mode_after_fill", "insert_mode_after_fill", bool, True,
            "enter insert mode after filling"),
    Setting("submit_after_fill", "submit_after_fill", bool, False,
            "submit the form after filling"),
    Setting("matching.default_mode", "matching_default_mode", MatchMode, MatchMode.BASE_DOMAIN,
            "URI match mode for URIs without one"),
    Setting("generator.length", "generator_length", int, 24, "generated password length (>= 4)"),
    Setting("generator.uppercase", "generator_uppercase", bool, True, "use uppercase letters"),
    Setting("generator.lowercase", "generator_lowercase", bool, True, "use lowercase letters"),
    Setting("generator.digits", "generator_digits", bool, True, "use digits"),
    Setting("generator.symbols", "generator_symbols", bool, True, "use symbols"),
    Setting("totp.clipboard", "totp_clipboard", bool, False,
            "copy the TOTP code to the clipboard instead of filling it"),
    Setting("totp.clipboard_clear_seconds", "totp_clipboard_clear_seconds", int, 30,
            "seconds before a copied TOTP code is cleared"),
    Setting("vault.allow_copy", "vault_allow_copy", bool, False,
            "offer copying secrets in the vault browser"),
    Setting("vault.copy_clear_seconds", "vault_copy_clear_seconds", int, 30,
            "seconds before a copied secret is cleared"),
)


@dataclass(frozen=True)
class Config:
    picker: tuple[str, ...] | None = None
    auto_fill: bool = False
    backend: str = "rbw"
    insert_mode_after_fill: bool = True
    submit_after_fill: bool = False
    matching_default_mode: MatchMode = MatchMode.BASE_DOMAIN
    generator_length: int = 24
    generator_uppercase: bool = True
    generator_lowercase: bool = True
    generator_digits: bool = True
    generator_symbols: bool = True
    totp_clipboard: bool = False
    totp_clipboard_clear_seconds: int = 30
    vault_allow_copy: bool = False
    vault_copy_clear_seconds: int = 30


def load_config(path: Path | None, overrides: Mapping[str, object]) -> Config:
    """Build a Config: defaults < TOML at ``path`` < ``overrides`` (keyed by attr)."""
    return Config()
