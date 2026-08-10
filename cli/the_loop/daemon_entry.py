"""Programmatic entry point for the ingress daemons (issue-161).

``python -m the_loop.daemon_entry <poller|gh-webhook>`` runs a daemon with the
options its CLI command would default to, read from the CLI config. It exists
so :mod:`the_loop.core.daemons` can start a daemon **without shelling out to
the-loop's own CLI verb** — the transitional adapter the owner asked us to
remove (PR #162). The CLI's ``poll start`` / ``gh-webhook start`` run the daemon
in the *foreground* by default, which is what cron and systemd units expect;
this module is the detached-start path the **control plane** uses. Since
issue-191 ``poll start --daemon`` can also detach on its own — which is why the
namespace built here forces ``daemon`` off: this process has already been
detached by its spawner, and a second double-fork would orphan the pid the
control plane reported.

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
    args = parser.parse_args(["start"])
    # Never daemonize from here (issue-191): the control plane has already
    # detached this process with `start_new_session=True` and redirected its
    # output, so a second double-fork would only orphan the pid it reported.
    if hasattr(args, "daemon"):
        args.daemon = False
    return args


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
