"""The repo-wide no-leak test (spec: Security rules).

Runs every registered subcommand, under several config variants, against the
fake Backend and fails if a placeholder secret (``SECRET_MARKER``) shows up
anywhere it must not: lines sent to QUTE_FIFO (messages included), picker
prompts and lines, a child process's argv or environment, or our own
stdout/stderr. The fake Card items' numbers and security codes, and every value
of the fake Identity items, carry the marker too; only a card's last 4 digits
may reach a picker line.

Subcommands are taken from ``all_commands()`` at collection time, so a new
``commands/*.py`` is covered without touching this file.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys
from dataclasses import dataclass, field

import pytest
from fakes.children import ChildRecorder
from fakes.clipboard import FakeClipboard
from fakes.picker import FakePicker
from fakes.qutebrowser import FakeQutebrowser

from qutewarden import cli, commands
from qutewarden.backend.fake import SECRET_MARKER
from qutewarden.commands import Command, all_commands
from qutewarden.context import Context

# Subcommands whose job is to get a secret into the page (or, if configured,
# the clipboard). For these the test also checks that the marker *did* reach
# one of those sinks, which proves the test is wired up.
FILL_TYPE = {"fill", "totp", "generate", "vault", "card", "identity"}

# config variant -> (flags, FakePicker keyword arguments)
VARIANTS: dict[str, tuple[list[str], dict]] = {
    "defaults": ([], {}),
    "auto_fill": (["--auto-fill"], {}),
    "totp_clipboard": (["--totp-clipboard"], {}),
    "vault_allow_copy": (["--vault-allow-copy"], {"prefer": "copy"}),
}


@dataclass
class Observed:
    exit_code: int | None
    fifo_lines: list[str]
    messages: list[tuple[str, str]]
    children: list
    stdout: str
    stderr: str
    js: list[str]
    clipboard: list[str]
    leaks: list[str] = field(default_factory=list)


def run_subcommand(name: str, flags: list[str], picker: FakePicker, ctx: Context,
                   qb: FakeQutebrowser, recorder: ChildRecorder, clipboard: FakeClipboard,
                   capfd: pytest.CaptureFixture[str]) -> Observed:
    def make_context(config, environ):
        return dataclasses.replace(ctx, config=config, environ=environ, picker=picker)

    exit_code = None
    try:
        exit_code = cli.main([name, *flags], environ=ctx.environ, make_context=make_context)
    except SystemExit as e:  # argparse
        exit_code = e.code if isinstance(e.code, int) else 2
    finally:
        qb.close()
    out, err = capfd.readouterr()
    observed = Observed(exit_code, list(qb.commands), list(qb.messages), list(recorder.children),
                        out, err, list(qb.js), [value for value, _ in clipboard.copies])
    if any(SECRET_MARKER in line for line in observed.fifo_lines):
        observed.leaks.append("QUTE_FIFO line")
    if any(SECRET_MARKER in text for _, text in observed.messages):
        observed.leaks.append("message")
    shown = [*picker.prompts, *(line for lines in picker.lines for line in lines)]
    if any(SECRET_MARKER in text for text in shown):
        observed.leaks.append("picker")
    for child in observed.children:
        if any(SECRET_MARKER in arg for arg in child.argv):
            observed.leaks.append(f"argv of {child.argv[0]}")
        if any(SECRET_MARKER in k or SECRET_MARKER in v for k, v in child.env.items()):
            observed.leaks.append(f"environment of {child.argv[0]}")
    if SECRET_MARKER in out:
        observed.leaks.append("stdout")
    if SECRET_MARKER in err:
        observed.leaks.append("stderr")
    return observed


@pytest.fixture
def observe(ctx, fake_qutebrowser, child_recorder, fake_clipboard, capfd):
    def observe(name: str, variant: str) -> Observed:
        flags, picker_kwargs = VARIANTS[variant]
        return run_subcommand(name, flags, FakePicker(**picker_kwargs), ctx, fake_qutebrowser,
                              child_recorder, fake_clipboard, capfd)
    return observe


@pytest.mark.parametrize("variant", VARIANTS)
@pytest.mark.parametrize("name", sorted(all_commands()))
def test_no_secret_leaks(name, variant, observe):
    observed = observe(name, variant)

    assert observed.leaks == [], (
        f"{name} ({variant}) leaked a secret via: {', '.join(observed.leaks)}")
    if name in FILL_TYPE and observed.exit_code == 0:
        sinks = observed.js + observed.clipboard
        assert any(SECRET_MARKER in s for s in sinks), (
            f"{name} ({variant}) exited 0 but no secret reached the page or clipboard; "
            "is the no-leak test still wired up?")


def test_every_registered_subcommand_is_covered():
    # The parametrization above is all_commands(); this pins the v1 set so a
    # broken registry (empty or partial) can't make the no-leak test vacuous.
    assert {"fill", "totp", "generate", "vault", "card", "identity", "unlock", "lock", "sync",
            "status"} <= set(
        all_commands())


# --- the detector itself ---------------------------------------------------

SECRET = f"{SECRET_MARKER}-password-github"


def _leaky(how: str):
    def run(ctx: Context, args: argparse.Namespace) -> int:
        if how == "message":
            ctx.qute.message_info(f"your password is {SECRET}")
        elif how == "picker":
            ctx.picker.choose("Card", [f"Visa *{SECRET}"])
        elif how == "fifo":
            ctx.qute.send(f"jseval --quiet fill('{SECRET}')")
        elif how == "argv":
            subprocess.run(["wl-copy", SECRET], check=False)
        elif how == "env":
            subprocess.run(["wl-copy"], env={**os.environ, "PW": SECRET}, check=False)
        elif how == "inherited env":
            os.environ["QUTEWARDEN_TEST_LEAK"] = SECRET
            subprocess.Popen(["true"]).wait()
        elif how == "stdout":
            print(SECRET)
        elif how == "stderr":
            print(SECRET, file=sys.stderr)
        return 0
    return run


@pytest.mark.parametrize("how, channel", [
    ("message", "message"), ("picker", "picker"), ("fifo", "QUTE_FIFO line"),
    ("argv", "argv of wl-copy"), ("env", "environment of wl-copy"),
    ("inherited env", "environment of true"),
    ("stdout", "stdout"), ("stderr", "stderr"),
])
def test_detector_catches_each_leak_channel(how, channel, observe, monkeypatch):
    monkeypatch.setenv("QUTEWARDEN_TEST_LEAK", "")  # restored afterwards
    monkeypatch.setitem(commands._REGISTRY, "leaky", Command("leaky", "leaks", _leaky(how)))
    observed = observe("leaky", "defaults")
    assert channel in observed.leaks


def test_secrets_in_the_pipe_are_not_leaks(observe, ctx, monkeypatch):
    from qutewarden.fillroute import send_js

    def run(c: Context, args: argparse.Namespace) -> int:
        send_js(c.qute, f"fill('{SECRET}')", runtime_dir=c.runtime_dir, timeout=c.fill_timeout)
        return 0

    monkeypatch.setitem(commands._REGISTRY, "pipe", Command("pipe", "fills", run))
    observed = observe("pipe", "defaults")
    assert observed.leaks == []
    assert observed.js == [f"fill('{SECRET}')"]
