"""``the-loop state paths|migrate`` — where the daemon keeps its runtime state.

All of it now lives under ``.the-loop/state/`` (issue-98 review, decision-039).
``paths`` answers "where is my session registry / event log / pidfile?" —
including which entries are still on their pre-move path — and ``migrate``
moves those over when the operator is ready.

Migration is deliberately a **command**, not something a daemon does on start:
moving a live registry or pidfile out from under a running process is how you
end up with two daemons that each believe they own the same work item. So
``migrate`` refuses while a daemon looks alive, and until it is run the
pre-move paths keep being read exactly as before.

Spec: docs/specs/issue-98/design.md §11.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .base import Command, register
from .. import state


@register
class StateCommand(Command):
    name = "state"
    help = "Show or consolidate where the-loop keeps its runtime state"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        paths = actions.add_parser(
            "paths", help="Show every runtime-state path and which layout is in use"
        )
        paths.set_defaults(_action=self._paths)

        migrate = actions.add_parser(
            "migrate", help=f"Move pre-move state files under {state.STATE_DIR}/"
        )
        migrate.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would move; write nothing.",
        )
        migrate.add_argument(
            "--force",
            action="store_true",
            help="Migrate even though a daemon looks like it is running (unsafe).",
        )
        migrate.set_defaults(_action=self._migrate)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # -- actions ---------------------------------------------------------------

    def _paths(self, args: argparse.Namespace) -> int:
        rows = [("What", "Path", "Layout", "Exists")]
        legacy_in_use = False
        for path in state.PATHS:
            resolved = state.resolve(path.current)
            layout = "current" if resolved == path.current else "pre-move"
            legacy_in_use = legacy_in_use or layout == "pre-move"
            rows.append(
                (
                    path.description,
                    resolved,
                    layout,
                    "yes" if Path(resolved).exists() else "no",
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            print("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))
        print(
            "\nAn explicitly configured path always wins; only defaults fall back "
            "to a pre-move location."
        )
        if legacy_in_use:
            print(
                "\nsome state is still on its pre-move path — run "
                "`the-loop state migrate` (with the daemons stopped) to "
                f"consolidate it under {state.STATE_DIR}/",
                file=sys.stderr,
            )
        return 0

    def _migrate(self, args: argparse.Namespace) -> int:
        if not args.dry_run and not args.force:
            live = state.running_daemons()
            if live:
                print(
                    "error: a the-loop daemon looks like it is running "
                    f"({'; '.join(live)}). Stop it first (`the-loop poll stop` / "
                    "`the-loop gh-webhook stop`) — moving a live registry or "
                    "pidfile can leave two daemons owning the same work item. "
                    "Pass --force to override.",
                    file=sys.stderr,
                )
                return 1
        steps = state.migrate(dry_run=args.dry_run)
        moved = failed = 0
        for step in steps:
            if step.action in ("moved", "would-move"):
                verb = "would move" if step.action == "would-move" else "moved"
                print(f"{verb} {step.path.legacy} -> {step.path.current}")
                moved += 1
            elif step.action == "skipped-target-exists":
                print(
                    f"skipped {step.path.legacy}: {step.path.current} already "
                    "exists — state in both layouts, resolve it by hand",
                    file=sys.stderr,
                )
                failed += 1
            elif step.action == "failed":
                print(f"error: {step.path.legacy}: {step.error}", file=sys.stderr)
                failed += 1
        if not moved and not failed:
            print(f"nothing to migrate — all state is already under {state.STATE_DIR}/")
        elif args.dry_run:
            print(f"\n{moved} path(s) would move; nothing was written")
        else:
            print(f"\nmigrated {moved} path(s)")
        return 1 if failed else 0
