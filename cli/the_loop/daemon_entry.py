"""Programmatic entry point for the ingress daemons (issue-161, issue-228).

``python -m the_loop.daemon_entry <poller|gh-webhook>`` runs a daemon with the
options the CLI config defaults, in the foreground of *this* process. It is
what the control plane and ``the-loop start`` spawn (detached, with
``start_new_session=True`` and the logfile on fds 1/2 — see
:mod:`the_loop.core.daemons`), and it is also the cron/systemd form: a
``Type=simple`` unit runs it directly, and ``poller --once`` runs a single poll
cycle and exits — the capability the removed ``poll start --once`` provided
(issue-228, R2.3).

The poller is driven through :mod:`the_loop.poller.daemon` — the run loop
itself, relocated when its command was removed. ``gh-webhook`` still resolves
its options through its surviving command's parser, so there is exactly one
startup sequence per daemon either way (NFR1): lock acquisition, dependency
checks, the run loop.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

DAEMONS = ("poller", "gh-webhook")


def _run_gh_webhook() -> int:
    """Run the receiver with the option namespace its own ``start`` parser
    would produce (the command survives issue-228; reuse its one sequence)."""
    from .commands.base import iter_commands

    command = next(c for c in iter_commands() if c.name == "gh-webhook")
    parser = argparse.ArgumentParser(prog="gh-webhook")
    command.add_arguments(parser)
    args = parser.parse_args(["start"])
    return int(args._action(args) or 0)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog="python -m the_loop.daemon_entry",
        description="Run a the-loop ingress daemon in the foreground.",
    )
    parser.add_argument("daemon", choices=DAEMONS)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poller only: run a single poll cycle and exit (cron form).",
    )
    args = parser.parse_args(argv)
    if args.once and args.daemon != "poller":
        parser.error("--once applies to the poller only")
    if args.daemon == "poller":
        from .poller import daemon as poller_daemon

        return poller_daemon.run(poller_daemon.default_options(once=args.once))
    return _run_gh_webhook()


if __name__ == "__main__":
    sys.exit(main())
