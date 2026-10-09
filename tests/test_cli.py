import shlex
from pathlib import Path

import pytest
from fakes.picker import FakePicker

from qutewarden import cli
from qutewarden.backend.fake import FakeBackend
from qutewarden.commands import all_commands
from qutewarden.config import Config
from qutewarden.context import Context
from qutewarden.match import make_suffix_extractor
from qutewarden.model import MatchMode
from qutewarden.qute import Qute

SUBCOMMANDS = ["fill", "totp", "generate", "vault", "unlock", "lock", "sync", "status"]


@pytest.fixture
def fifo(tmp_path: Path) -> Path:
    path = tmp_path / "fifo"
    path.write_text("")
    return path


@pytest.fixture
def environ(tmp_path: Path, fifo: Path) -> dict[str, str]:
    return {
        "QUTE_URL": "https://github.com/login",
        "QUTE_FIFO": str(fifo),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "HOME": str(tmp_path / "home"),
    }


class Recorder:
    """make_context that records the Config main() resolved."""

    def __init__(self) -> None:
        self._config: Config | None = None

    @property
    def config(self) -> Config:
        assert self._config is not None, "make_context was never called"
        return self._config

    def __call__(self, config: Config, environ) -> Context:
        self._config = config
        return Context(
            config=config, environ=environ, qute=Qute.from_environ(environ),
            backend=FakeBackend(), picker=FakePicker(choices=[None]), clipboard=None,
            runtime_dir=Path(environ["XDG_RUNTIME_DIR"]) / "qutewarden",
            cache_dir=Path(environ["XDG_CACHE_HOME"]) / "qutewarden",
            generate_password=lambda cfg: "QWSECRET-generated",
            suffix_extractor=make_suffix_extractor(Path(environ["XDG_CACHE_HOME"]), offline=True),
        )


def messages(fifo: Path) -> list[list[str]]:
    return [shlex.split(line) for line in fifo.read_text().splitlines()]


def write_config(environ: dict[str, str], text: str) -> None:
    path = Path(environ["XDG_CONFIG_HOME"]) / "qutewarden" / "config.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text)


def test_help_lists_every_subcommand(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"], environ={})
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for name in SUBCOMMANDS:
        assert name in out


def test_help_has_no_backend_flag(capsys):
    with pytest.raises(SystemExit):
        cli.main(["fill", "--help"], environ={})
    assert "--backend" not in capsys.readouterr().out


def test_registry_has_every_subcommand():
    assert sorted(all_commands()) == sorted(SUBCOMMANDS)


def test_missing_subcommand_is_a_usage_error(environ, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([], environ=environ, make_context=Recorder())
    assert exc.value.code == 2


def test_defaults_when_no_config_file(environ):
    rec = Recorder()
    cli.main(["fill"], environ=environ, make_context=rec)
    assert rec.config == Config()


def test_config_file_from_xdg_config_home(environ):
    write_config(environ, "auto_fill = true\n[generator]\nlength = 40\n")
    rec = Recorder()
    cli.main(["fill"], environ=environ, make_context=rec)
    assert rec.config.auto_fill is True
    assert rec.config.generator_length == 40


def test_flags_override_config_file(environ):
    write_config(environ, "auto_fill = true\n[generator]\nlength = 40\nsymbols = false\n")
    rec = Recorder()
    cli.main(["generate", "--no-auto-fill", "--generator-length", "16", "--generator-symbols",
              "--matching-default-mode", "exact", "--picker", "rofi -dmenu -i"],
             environ=environ, make_context=rec)
    assert rec.config.auto_fill is False
    assert rec.config.generator_length == 16
    assert rec.config.generator_symbols is True
    assert rec.config.matching_default_mode is MatchMode.EXACT
    assert rec.config.picker == ("rofi", "-dmenu", "-i")


def test_absent_flags_keep_config_file_values(environ):
    write_config(environ, "submit_after_fill = true\n")
    rec = Recorder()
    cli.main(["fill", "--auto-fill"], environ=environ, make_context=rec)
    assert rec.config.submit_after_fill is True
    assert rec.config.auto_fill is True


def test_every_setting_has_a_flag_on_every_subcommand(environ):
    rec = Recorder()
    for name in SUBCOMMANDS:
        cli.main([name, "--totp-clipboard", "--vault-copy-clear-seconds", "5",
                  "--no-insert-mode-after-fill"],
                 environ=environ, make_context=rec)
        assert rec.config.totp_clipboard is True
        assert rec.config.vault_copy_clear_seconds == 5
        assert rec.config.insert_mode_after_fill is False


def test_global_equivalent_domains_can_be_turned_off_by_flag(environ):
    rec = Recorder()
    cli.main(["fill", "--no-matching-global-equivalent-domains"], environ=environ,
             make_context=rec)
    assert rec.config.matching_global_equivalent_domains is False


def test_user_equivalent_domains_have_no_flag(environ):
    with pytest.raises(SystemExit) as exc:
        cli.main(["fill", "--matching-equivalent-domains", "a.test"], environ=environ,
                 make_context=Recorder())
    assert exc.value.code == 2


def test_config_flag_selects_another_file(environ, tmp_path):
    other = tmp_path / "other.toml"
    other.write_text("vault.allow_copy = true\n")
    rec = Recorder()
    cli.main(["vault", "--config", str(other)], environ=environ, make_context=rec)
    assert rec.config.vault_allow_copy is True


def test_invalid_mode_flag_is_a_usage_error(environ):
    with pytest.raises(SystemExit) as exc:
        cli.main(["fill", "--matching-default-mode", "fuzzy"], environ=environ,
                 make_context=Recorder())
    assert exc.value.code == 2


def test_config_error_is_shown_with_message_error(environ, fifo):
    write_config(environ, "colour = 'red'\n")
    assert cli.main(["fill"], environ=environ, make_context=Recorder()) == 1
    [[command, text]] = messages(fifo)
    assert command == "message-error"
    assert "colour" in text


def test_bad_flag_value_is_shown_with_message_error(environ, fifo):
    assert cli.main(["generate", "--generator-length", "2"], environ=environ,
                    make_context=Recorder()) == 1
    [[command, _]] = messages(fifo)
    assert command == "message-error"


def test_error_outside_qutebrowser_goes_to_stderr(environ, capsys):
    del environ["QUTE_FIFO"]
    write_config(environ, "colour = 'red'\n")
    assert cli.main(["fill"], environ=environ, make_context=Recorder()) == 1
    assert "colour" in capsys.readouterr().err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"], environ={})
    assert exc.value.code == 0
    assert "0.1.0" in capsys.readouterr().out
