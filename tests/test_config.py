from pathlib import Path

import pytest

from qutewarden.config import SETTINGS, ConfigError, default_config_path, load_config
from qutewarden.model import MatchMode


def test_defaults_match_spec_when_file_missing(tmp_path: Path):
    cfg = load_config(tmp_path / "missing.toml", {})
    assert cfg.picker is None
    assert cfg.auto_fill is False
    assert cfg.backend == "rbw"
    assert cfg.insert_mode_after_fill is True
    assert cfg.submit_after_fill is False
    assert cfg.matching_default_mode is MatchMode.BASE_DOMAIN
    assert cfg.generator_length == 24
    assert cfg.generator_uppercase is True
    assert cfg.generator_lowercase is True
    assert cfg.generator_digits is True
    assert cfg.generator_symbols is True
    assert cfg.totp_clipboard is False
    assert cfg.totp_clipboard_clear_seconds == 30
    assert cfg.vault_allow_copy is False
    assert cfg.vault_copy_clear_seconds == 30


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text)
    return path


def test_toml_values_override_defaults(tmp_path: Path):
    path = write(tmp_path, """
picker = "wofi --dmenu --insensitive"
auto_fill = true

[matching]
default_mode = "host"

[generator]
length = 40
symbols = false

[totp]
clipboard_clear_seconds = 10
""")
    cfg = load_config(path, {})
    assert cfg.picker == ("wofi", "--dmenu", "--insensitive")
    assert cfg.auto_fill is True
    assert cfg.matching_default_mode is MatchMode.HOST
    assert cfg.generator_length == 40
    assert cfg.generator_symbols is False
    assert cfg.totp_clipboard_clear_seconds == 10
    # untouched settings keep their defaults
    assert cfg.backend == "rbw"
    assert cfg.generator_digits is True


def test_overrides_win_over_toml_and_defaults(tmp_path: Path):
    path = write(tmp_path, "auto_fill = true\n[generator]\nlength = 40\n")
    cfg = load_config(path, {"auto_fill": False, "generator_length": 12, "totp_clipboard": True})
    assert cfg.auto_fill is False  # flag beats TOML
    assert cfg.generator_length == 12
    assert cfg.totp_clipboard is True  # flag beats default


def test_overrides_ignore_non_setting_keys():
    cfg = load_config(None, {"command": "fill", "config": "/x", "auto_fill": True})
    assert cfg.auto_fill is True


def test_picker_accepts_toml_list(tmp_path: Path):
    cfg = load_config(write(tmp_path, 'picker = ["fuzzel", "--dmenu"]\n'), {})
    assert cfg.picker == ("fuzzel", "--dmenu")


@pytest.mark.parametrize("text", [
    "nonsense = 1\n",
    "[generator]\ncolour = 'red'\n",
    "[unknown]\nx = 1\n",
    "generator = 3\n",
    "auto_fill = 'yes'\n",
    "[generator]\nlength = '24'\n",
    "[generator]\nlength = 3\n",
    "[matching]\ndefault_mode = 'fuzzy'\n",
    "backend = 'bw'\n",
    "picker = 5\n",
    "this is not toml",
])
def test_invalid_toml_raises_config_error(tmp_path: Path, text: str):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text), {})


def test_default_config_path_uses_xdg_config_home():
    assert default_config_path({"XDG_CONFIG_HOME": "/cfg", "HOME": "/home/u"}) == Path(
        "/cfg/qutewarden/config.toml")


def test_default_config_path_falls_back_to_home():
    assert default_config_path({"HOME": "/home/u"}) == Path("/home/u/.config/qutewarden/config.toml")
    assert default_config_path({"XDG_CONFIG_HOME": "", "HOME": "/home/u"}) == Path(
        "/home/u/.config/qutewarden/config.toml")


def test_setting_flag_names():
    flags = {s.key: s.flag for s in SETTINGS}
    assert flags["auto_fill"] == "--auto-fill"
    assert flags["matching.default_mode"] == "--matching-default-mode"
    assert flags["totp.clipboard_clear_seconds"] == "--totp-clipboard-clear-seconds"
