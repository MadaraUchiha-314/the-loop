"""Core CLI: builds the argument parser and dispatches to commands."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from . import __version__, cli_config
from .commands import iter_commands


def _peek_config_flag(argv: List[str]) -> Optional[str]:
    """Peek ``--config``/``-c`` before building subcommand parsers.

    Each command's ``add_arguments()`` reads the CLI config to compute its
    OTHER flags' defaults (e.g. ``--host``) — argparse builds every
    subcommand parser (and those defaults) before ``parse_args()`` returns, so
    ``--config``'s value has to be known earlier than a normal parse allows.
    A tiny throwaway parser (``add_help=False``, unknown args ignored) reads
    just that one flag first.
    """
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config", "-c")
    known, _ = pre.parse_known_args(argv)
    return known.config


def _refresh_cli_config_paths() -> None:
    """Re-resolve the CLI config path for commands that cache it at import
    time, so a ``--config``/``-c`` override (set just before this call) takes
    effect before ``add_arguments()`` computes their other flags' defaults."""
    from .commands import gh_webhook, poll

    resolved = cli_config.default_cli_config_path()
    gh_webhook._CONFIG_PATH = resolved
    poll._CONFIG_PATH = resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="the-loop",
        description="Lightweight, extensible CLI for the-loop.",
    )
    parser.add_argument(
        "--version", action="version", version=f"the-loop {__version__}"
    )
    parser.add_argument(
        "--config",
        "-c",
        help="Path to the CLI config file (webhooks/polling/eventLog). Overrides "
        "$THE_LOOP_CLI_CONFIG, ./.the-loop/cli-config.yaml and "
        "~/.the-loop/cli-config.yaml (decision-032). Must precede the subcommand.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    for cmd in iter_commands():
        cp = sub.add_parser(cmd.name, help=cmd.help, description=cmd.help)
        cmd.add_arguments(cp)
        cp.set_defaults(_handler=cmd.run)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    # Always (re-)set, including to None: a stale override from an earlier
    # main() call in the same process (e.g. under test) must not leak.
    cli_config.set_override(_peek_config_flag(argv))
    _refresh_cli_config_paths()
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:  # pragma: no cover - argparse enforces required subcommand
        parser.error("no command given")
    return int(handler(args) or 0)
