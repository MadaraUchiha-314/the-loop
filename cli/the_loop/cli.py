"""Core CLI: builds the argument parser and dispatches to commands."""

from __future__ import annotations

import argparse
from typing import List, Optional

from . import __version__
from .commands import iter_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="the-loop",
        description="Lightweight, extensible CLI for the-loop.",
    )
    parser.add_argument(
        "--version", action="version", version=f"the-loop {__version__}"
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True
    for cmd in iter_commands():
        cp = sub.add_parser(cmd.name, help=cmd.help, description=cmd.help)
        cmd.add_arguments(cp)
        cp.set_defaults(_handler=cmd.run)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "_handler", None)
    if handler is None:  # pragma: no cover - argparse enforces required subcommand
        parser.error("no command given")
    return int(handler(args) or 0)
