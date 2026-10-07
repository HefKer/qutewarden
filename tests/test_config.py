from pathlib import Path

from qutewarden.config import load_config
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
