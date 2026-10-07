import shlex
from pathlib import Path

import pytest

from qutewarden.errors import QutewardenError
from qutewarden.qute import FILL_WORLD_ID, Qute, quote_arg, sanitize_message


@pytest.fixture
def fifo(tmp_path: Path) -> Path:
    # A regular file stands in for QUTE_FIFO: Qute only appends lines to it.
    path = tmp_path / "fifo"
    path.write_text("")
    return path


def lines(path: Path) -> list[str]:
    return path.read_text().splitlines()


def test_from_environ_reads_url_and_fifo(fifo: Path):
    qute = Qute.from_environ({"QUTE_URL": "https://github.com/login", "QUTE_FIFO": str(fifo)})
    assert qute.url == "https://github.com/login"
    assert qute.fifo_path == fifo


def test_from_environ_without_qutebrowser():
    qute = Qute.from_environ({})
    assert qute.url is None
    assert qute.fifo_path is None


def test_send_appends_one_line_per_command(fifo: Path):
    qute = Qute.from_environ({"QUTE_FIFO": str(fifo)})
    qute.send("mode-enter insert")
    qute.send("message-info hi")
    assert lines(fifo) == ["mode-enter insert", "message-info hi"]


def test_send_refuses_newlines(fifo: Path):
    qute = Qute.from_environ({"QUTE_FIFO": str(fifo)})
    with pytest.raises(QutewardenError):
        qute.send("message-info a\nopen evil")
    assert fifo.read_text() == ""


def test_send_without_fifo_raises():
    with pytest.raises(QutewardenError, match="QUTE_FIFO unset"):
        Qute.from_environ({}).send("message-info hi")


@pytest.mark.parametrize("method,command", [
    ("message_info", "message-info"),
    ("message_warning", "message-warning"),
    ("message_error", "message-error"),
])
def test_messages_are_prefixed_and_quoted(fifo: Path, method: str, command: str):
    qute = Qute.from_environ({"QUTE_FIFO": str(fifo)})
    getattr(qute, method)("filling GitHub (alice's account)")
    [line] = lines(fifo)
    assert shlex.split(line) == [command, "qutewarden: filling GitHub (alice's account)"]


def test_message_cannot_inject_a_second_command(fifo: Path):
    qute = Qute.from_environ({"QUTE_FIFO": str(fifo)})
    qute.message_info("evil;;open https://attacker.test\nline two")
    [line] = lines(fifo)
    assert ";;" not in line


def test_enter_insert_mode(fifo: Path):
    Qute.from_environ({"QUTE_FIFO": str(fifo)}).enter_insert_mode()
    assert lines(fifo) == ["mode-enter insert"]


def test_jseval_file_uses_quiet_isolated_world_and_absolute_path(fifo: Path, tmp_path: Path):
    script = tmp_path / "dir with space" / "fill-abc.js"
    Qute.from_environ({"QUTE_FIFO": str(fifo)}).jseval_file(script)
    [line] = lines(fifo)
    assert shlex.split(line) == ["jseval", "--quiet", f"--world={FILL_WORLD_ID}", "--file", str(script)]


def test_jseval_file_rejects_relative_path(fifo: Path):
    with pytest.raises(QutewardenError):
        Qute.from_environ({"QUTE_FIFO": str(fifo)}).jseval_file(Path("fill.js"))


def test_spawn_userscript_quotes_each_arg(fifo: Path):
    Qute.from_environ({"QUTE_FIFO": str(fifo)}).spawn_userscript(
        ["/usr/bin/qutewarden", "generate", "--picker", "rofi -dmenu"])
    [line] = lines(fifo)
    assert shlex.split(line) == [
        "spawn", "--userscript", "/usr/bin/qutewarden", "generate", "--picker", "rofi -dmenu"]


@pytest.mark.parametrize("raw,expected", [
    ("plain text", "plain text"),
    ("a\r\nb\nc", "abc"),
    ("x;;y", "x; ;y"),
    ("x;;;;y", "x; ; ; ;y"),
    ("{clipboard}", "{{clipboard}}"),
    ("{url:password} and {title}", "{{url:password}} and {{title}}"),
    ("{notavar}", "{notavar}"),
])
def test_sanitize_message(raw: str, expected: str):
    assert sanitize_message(raw) == expected


def test_quote_arg_round_trips_through_shell_lexing():
    text = "it's \"quoted\" $HOME `x`"
    assert shlex.split(quote_arg(text)) == [text]
