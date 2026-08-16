"""``the-loop diagnose`` — one self-diagnosis scan, on demand (issue-242).

The manual half of the capability: deployments running neither ingress daemon
still get self-diagnosis, and ``--dry-run`` is how an operator sees exactly
what would leave the machine **before** opting in (it works while the feature
is disabled, and posts nothing).

Local-only, like ``critic run``: it spawns a local agent process, so routing
it through the control-plane service buys nothing yet.
"""

from __future__ import annotations

import argparse
import sys

from .. import cli_config, eventlog
from ..core import selfdiagnosis
from ..state import layout_from_config
from .base import Command, register


@register
class DiagnoseCommand(Command):
    name = "diagnose"
    help = (
        "scan the-loop's own event log for harness failures and file "
        "self-diagnosed issues (opt-in; --dry-run to preview)"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help=(
                "build and print the redacted report(s) without posting; works "
                "while selfDiagnosis is disabled, so you can preview before "
                "opting in"
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        eventlog.configure_from_file("diagnose")
        config_path = cli_config.default_cli_config_path()
        data = cli_config.load_cli_config(config_path)
        config = selfdiagnosis.SelfDiagnosisConfig.from_mapping(data)
        dry_run = bool(getattr(args, "dry_run", False))
        if not config.enabled and not dry_run:
            print(
                "self-diagnosis is off — set selfDiagnosis.enabled: true in "
                f"{config_path} to let the-loop file issues for its own "
                "failures, or preview with --dry-run",
                file=sys.stderr,
            )
            return 2

        layout = layout_from_config(data)
        log_path = (data.get("eventLog") or {}).get("path") or layout.event_log
        outcomes = selfdiagnosis.scan(
            config,
            log_path=log_path,
            state_path=layout.self_diagnosis,
            dry_run=dry_run,
        )
        if not outcomes:
            print("nothing to diagnose — no new failure fingerprints in the log")
            return 0
        for outcome in outcomes:
            self._print(outcome, config)
        return 0

    @staticmethod
    def _print(outcome: dict, config: selfdiagnosis.SelfDiagnosisConfig) -> None:
        action = outcome.get("action")
        if action == "dry-run":
            if outcome.get("body"):
                print(f"--- would file on {config.repo} ---")
                print(outcome.get("title", ""))
                print()
                print(outcome["body"])
            else:
                print(
                    "--- would diagnose (agent unavailable: "
                    f"{outcome.get('error', '')}) ---"
                )
                print(outcome.get("dossier", ""))
        elif action == "posted":
            print(f"filed {outcome.get('url')} — {outcome.get('title')}")
        elif action == "deferred":
            print(
                f"deferred {outcome.get('fingerprint')} — daily cap "
                f"(maxIssuesPerDay: {config.max_issues_per_day}) reached"
            )
        else:
            print(
                f"failed {outcome.get('fingerprint')} — {outcome.get('error')}",
                file=sys.stderr,
            )
