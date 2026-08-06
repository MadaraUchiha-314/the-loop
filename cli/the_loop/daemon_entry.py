"""Programmatic entry point for the ingress daemons (issue-161).

``python -m the_loop.daemon_entry <poller|gh-webhook>`` runs a daemon with the
options its CLI command would default to, read from the CLI config. It exists
so :mod:`the_loop.core.daemons` can start a daemon **without shelling out to
the-loop's own CLI verb** — the transitional adapter the owner asked us to
remove (PR #162). The CLI's ``poll start`` / ``gh-webhook start`` keep running
the daemon in the *foreground*, which is what cron and systemd units expect;
this module is the detached-start path the control plane uses.

Both paths converge on the same command implementation, so there is exactly one
daemon startup sequence — lock acquisition, dependency checks, the run loop.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

DAEMONS = ("poller", "gh-webhook")


def _namespace(daemon: str) -> argparse.Namespace:
    """The option namespace the daemon's own ``start`` parser would produce."""
    from .commands.base import iter_commands

    command_name = "poll" if daemon == "poller" else "gh-webhook"
    command = next(c for c in iter_commands() if c.name == command_name)
    parser = argparse.ArgumentParser(prog=command_name)
    command.add_arguments(parser)
    return parser.parse_args(["start"])


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1 or argv[0] not in DAEMONS:
        print(
            f"usage: python -m the_loop.daemon_entry {{{'|'.join(DAEMONS)}}}",
            file=sys.stderr,
        )
        return 2
    daemon = argv[0]
    args = _namespace(daemon)
    return int(args._action(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
