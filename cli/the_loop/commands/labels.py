"""``the-loop labels ensure`` — create the labels the daemon reacts to (issue-98).

the-loop is driven from the GitHub UI by two labels: the **auto-execute** label
(work this item autonomously) and the **paused** label (stop working it). Both
are useless until they exist in the repo, so onboarding creates them — this is
the command `/the-loop:init`'s label step and the docs point at.

Idempotent by construction: existing labels are listed first and only the
missing ones are created. Names come from the CLI config, so a renamed label is
created under the name the daemon actually reads.

Spec: docs/specs/issue-98/design.md §7.
"""

from __future__ import annotations

import argparse
import sys

from .base import Command, register
from .gh_webhook import _load_config_defaults
from ..labels import GitHubLabeler, LabelError, default_specs
from ..poller.github import RepoSpec
from ..sessions import DEFAULT_PAUSED_LABEL


def _routing() -> dict:
    return _load_config_defaults().get("routing") or {}


@register
class LabelsCommand(Command):
    name = "labels"
    help = "Create the GitHub labels the-loop reacts to (auto-execute, paused)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        ensure = actions.add_parser(
            "ensure", help="Create any of the-loop's labels the repo is missing"
        )
        ensure.add_argument(
            "--repo",
            required=True,
            action="append",
            metavar="OWNER/REPO",
            help="Repository to create the labels in (repeatable).",
        )
        ensure.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created; write nothing.",
        )
        ensure.add_argument("--gh-binary", default="gh")
        ensure.set_defaults(_action=self._ensure)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    def _ensure(self, args: argparse.Namespace) -> int:
        routing = _routing()
        specs = default_specs(
            auto_execute_label=str(
                routing.get("autoExecuteLabel", "the-loop: auto-execute")
            ),
            paused_label=str(routing.get("pausedLabel", DEFAULT_PAUSED_LABEL)),
        )
        if not specs:
            print("error: no label names configured; nothing to do", file=sys.stderr)
            return 1
        labeler = GitHubLabeler(gh_binary=args.gh_binary)
        exit_code = 0
        for value in args.repo:
            try:
                spec = RepoSpec.parse(value)
                results = labeler.ensure(
                    spec.owner, spec.repo, specs, dry_run=args.dry_run
                )
            except (ValueError, LabelError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                exit_code = 1
                continue
            for result in results:
                print(f"{spec.full_name}  {result.detail}")
        return exit_code
