"""Command-line entry point: ``qutewarden [--version] <subcommand> [flags]``.

Settings flags come after the subcommand (``spawn --userscript qutewarden fill
--auto-fill``). They are generated from ``config.SETTINGS`` and default to
``argparse.SUPPRESS``, so an absent flag never overrides the config file.
"""

from __future__ import annotations

import argparse
import os
import shlex
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from qutewarden import __version__
from qutewarden.commands import all_commands
from qutewarden.config import (
    SETTINGS,
    Config,
    Setting,
    default_config_path,
    load_config,
)
from qutewarden.context import Context
from qutewarden.errors import QutewardenError, UserCancelled
from qutewarden.model import MatchMode
from qutewarden.qute import Qute


def _settings_parser() -> argparse.ArgumentParser:
    """Parent parser holding ``--config`` and one flag per Setting."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", metavar="PATH", type=Path, default=None,
                        help="config file (default: $XDG_CONFIG_HOME/qutewarden/config.toml)")
    group = parser.add_argument_group("settings (override the config file)")
    for setting in SETTINGS:
        _add_setting_flag(group, setting)
    return parser


def _add_setting_flag(group: argparse._ArgumentGroup, setting: Setting) -> None:
    common: dict[str, Any] = {
        "dest": setting.attr, "default": argparse.SUPPRESS, "help": setting.help}
    if setting.type is bool:
        group.add_argument(setting.flag, action=argparse.BooleanOptionalAction, **common)
    elif setting.type is int:
        group.add_argument(setting.flag, type=int, metavar="N", **common)
    elif setting.type is MatchMode:
        group.add_argument(setting.flag, choices=[m.value for m in MatchMode],
                           metavar="MODE", **common)
    elif setting.type is tuple:
        group.add_argument(setting.flag, type=shlex.split, metavar="CMD", **common)
    else:
        group.add_argument(setting.flag, metavar=setting.attr.upper(), **common)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qutewarden",
        description="Bitwarden logins in qutebrowser (run as a userscript).")
    parser.add_argument("--version", action="version", version=f"qutewarden {__version__}")
    parents = [_settings_parser()]
    sub = parser.add_subparsers(dest="command", metavar="<subcommand>", required=True)
    for command in all_commands().values():
        sp = sub.add_parser(command.name, help=command.help, description=command.help,
                            parents=parents)
        if command.add_arguments is not None:
            command.add_arguments(sp)
    return parser


def main(argv: Sequence[str] | None = None, *,
         environ: Mapping[str, str] | None = None,
         make_context: Callable[[Config, Mapping[str, str]], Context] | None = None) -> int:
    """Run one subcommand. Exit codes: 0 ok/cancelled, 1 handled error, 2 usage error."""
    if environ is None:
        environ = os.environ
    if make_context is None:
        make_context = Context.from_environ
    args = build_parser().parse_args(argv)
    qute = Qute.from_environ(environ)
    try:
        path = args.config or default_config_path(environ)
        config = load_config(path, vars(args))
        ctx = make_context(config, environ)
        return all_commands()[args.command].run(ctx, args)
    except UserCancelled:
        return 0
    except QutewardenError as e:
        _report_error(qute, str(e))
        return 1


def _report_error(qute: Qute, text: str) -> None:
    """Show ``text`` in qutebrowser, or on stderr when not run as a userscript."""
    try:
        qute.message_error(text)
    except QutewardenError:
        print(f"qutewarden: {text}", file=sys.stderr)
