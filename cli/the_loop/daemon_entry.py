"""Programmatic entry point for the ingress daemons (issue-161, issue-228).

``python -m the_loop.daemon_entry <poller|gh-webhook>`` runs a daemon with the
options the CLI config defaults, in the foreground of *this* process. It is
what the control plane and ``the-loop start`` spawn (detached, with
``start_new_session=True`` and the logfile on fds 1/2 — see
:mod:`the_loop.core.daemons`), and it is also the cron/systemd form: a
``Type=simple`` unit runs it directly, and ``poller --once`` runs a single poll
cycle and exits — the capability the removed ``poll start --once`` provided
(issue-228, R2.3).

Both daemons are driven through their own runtime modules —
:mod:`the_loop.poller.daemon` and :mod:`the_loop.webhook.daemon`, the run
loops relocated when their commands were removed (the owner's review on
PR #229 folded ``gh-webhook`` in alongside ``poll``) — so there is exactly one
startup sequence per daemon (NFR1): lock acquisition, dependency checks, the
run loop.
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

DAEMONS = ("poller", "gh-webhook")


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
    from .webhook import daemon as webhook_daemon

    return webhook_daemon.run(webhook_daemon.default_options())


if __name__ == "__main__":
    sys.exit(main())
