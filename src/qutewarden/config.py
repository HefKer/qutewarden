"""Settings: defaults < TOML file < command-line flags.

``SETTINGS`` is the single source of truth for TOML keys, flags, defaults and
``Config`` attributes.
"""

from __future__ import annotations

import shlex
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


def default_config_path(environ: Mapping[str, str]) -> Path:
    """``$XDG_CONFIG_HOME/qutewarden/config.toml``, falling back to ``~/.config``."""
    base = environ.get("XDG_CONFIG_HOME") or ""
    if not base:
        home = environ.get("HOME") or str(Path.home())
        base = str(Path(home) / ".config")
    return Path(base) / "qutewarden" / "config.toml"


_BY_KEY: dict[str, Setting] = {s.key: s for s in SETTINGS}
_BY_ATTR: dict[str, Setting] = {s.attr: s for s in SETTINGS}


def load_config(path: Path | None, overrides: Mapping[str, object]) -> Config:
    """Build a Config: defaults < TOML at ``path`` < ``overrides`` (keyed by attr).

    A missing file means defaults. ``overrides`` may contain unrelated keys
    (e.g. ``vars(namespace)``); only Setting attrs are used.
    """
    values: dict[str, Any] = {}  # each coerced to its Setting's type
    if path is not None:
        for key, raw in _read_toml(path).items():
            setting = _BY_KEY[key]
            values[setting.attr] = _coerce(setting, raw)
    for attr, raw in overrides.items():
        setting = _BY_ATTR.get(attr)
        if setting is not None:
            values[attr] = _coerce(setting, raw)
    return Config(**values)


def _read_toml(path: Path) -> dict[str, object]:
    """Read ``path`` and flatten it to ``{dotted key: value}``."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from None
    except OSError as e:
        raise ConfigError(f"{path}: cannot read: {e.strerror}") from None

    flat: dict[str, object] = {}

    def walk(table: Mapping[str, object], prefix: str) -> None:
        for name, value in table.items():
            key = prefix + name
            if key in _BY_KEY:
                flat[key] = value
            elif isinstance(value, dict) and any(k.startswith(key + ".") for k in _BY_KEY):
                walk(value, key + ".")
            else:
                raise ConfigError(f"{path}: unknown setting {key!r}")

    walk(data, "")
    return flat


def _coerce(setting: Setting, raw: object) -> object:
    """Check ``raw`` against the setting's type and convert it."""
    t = setting.type
    if t is tuple:
        if raw is None:
            return None
        if isinstance(raw, str):
            argv = tuple(shlex.split(raw))
        elif isinstance(raw, (list, tuple)) and all(isinstance(x, str) for x in raw):
            argv = tuple(raw)
        else:
            raise ConfigError(f"{setting.key} must be a command string or a list of strings")
        if not argv:
            raise ConfigError(f"{setting.key} must not be empty")
        return argv
    if t is bool:
        if not isinstance(raw, bool):
            raise ConfigError(f"{setting.key} must be true or false")
        return raw
    if t is int:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise ConfigError(f"{setting.key} must be an integer")
        if setting.attr == "generator_length" and raw < 4:
            raise ConfigError(f"{setting.key} must be at least 4")
        if raw < 0:
            raise ConfigError(f"{setting.key} must not be negative")
        return raw
    if t is MatchMode:
        try:
            return MatchMode(raw)
        except ValueError:
            choices = ", ".join(m.value for m in MatchMode)
            raise ConfigError(f"{setting.key} must be one of: {choices}") from None
    if not isinstance(raw, str):
        raise ConfigError(f"{setting.key} must be a string")
    if setting.attr == "backend" and raw != "rbw":
        raise ConfigError(f"{setting.key}: unknown backend {raw!r} (v1 supports only 'rbw')")
    return raw
