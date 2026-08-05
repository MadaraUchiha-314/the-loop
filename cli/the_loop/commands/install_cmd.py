"""``the-loop install`` / ``the-loop upgrade`` — put the-loop on a machine (issue-152).

Two verbs, one implementation: ``upgrade`` is ``install`` with ``upgrade=True``. Both
build a plan of steps (:mod:`the_loop.install`), print it with the exact argv of every
step, and execute it unless ``--dry-run`` says otherwise. The command layer here owns
only argument parsing, the plan header, rendering and the exit code — the decisions about
*what* to run live in the module, where they are testable without a machine.

Spec: docs/specs/issue-152/  ·  Decision: 057
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Sequence

from .base import Command, register
from .. import install as install_mod
from ..cli_config import default_cli_config_path, load_cli_config

logger = logging.getLogger("the-loop.install")


def _cli_config() -> dict:
    """The CLI config, or ``{}`` with a warning.

    The only value read here is ``routing.harnessPlugins.marketplaceRepo``. A config that
    is unreadable — or that :mod:`the_loop.migrations` refuses as un-migrated — must not
    block an install or an upgrade: upgrading the CLI is frequently the *fix* for a config
    the running version no longer understands.
    """
    try:
        return load_cli_config(default_cli_config_path())
    except Exception as exc:  # noqa: BLE001 - any unreadable config degrades the same way
        logger.warning(
            "could not read the CLI config (%s); using the default marketplace", exc
        )
        return {}


_HEADERS = ["Component", "Outcome", "Step", "Command / file", "Detail"]


def _rows(results: Sequence[install_mod.StepResult]) -> List[List[str]]:
    return [
        [r.component, r.outcome, r.summary, r.command or "—", r.detail or "—"]
        for r in results
    ]


def render_table(results: Sequence[install_mod.StepResult]) -> str:
    """A plain, aligned ASCII table — the same renderer shape as ``instructions``."""
    rows = _rows(results)
    widths = [len(h) for h in _HEADERS]
    for row in rows:
        for column, cell in enumerate(row):
            widths[column] = max(widths[column], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells))

    lines = [fmt(_HEADERS), "  ".join("-" * width for width in widths)]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def render_json(results: Sequence[install_mod.StepResult]) -> str:
    return json.dumps([result.as_dict() for result in results], indent=2)


class _InstallBase(Command):
    """Shared surface; subclasses differ only in ``upgrade``."""

    upgrade = False

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        verb = "upgrade" if self.upgrade else "install"
        parser.add_argument(
            "components",
            nargs="*",
            metavar="COMPONENT",
            help=(
                "What to "
                + verb
                + ": any of "
                + ", ".join(install_mod.COMPONENTS)
                + ", or 'all'. Default: the CLI plus every harness found on PATH."
            ),
        )
        parser.add_argument(
            "--scope",
            choices=("user", "project"),
            default="user",
            help="Install for your user account (default) or for one project only.",
        )
        parser.add_argument(
            "--project-dir",
            default=".",
            help="The project for --scope project (default: current directory).",
        )
        parser.add_argument(
            "--from",
            dest="marketplace_repo",
            default="",
            help=(
                "Marketplace repository as owner/repo. Default: the CLI config's "
                "routing.harnessPlugins.marketplaceRepo, else "
                f"{install_mod.DEFAULT_MARKETPLACE_REPO}."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the plan and change nothing.",
        )
        parser.add_argument(
            "--format",
            choices=("table", "json"),
            default="table",
            help="Output format (default: table).",
        )

    def run(self, args: argparse.Namespace) -> int:
        env = install_mod.default_env()
        try:
            components = install_mod.resolve_components(args.components, env)
        except ValueError as exc:
            logger.error("%s", exc)
            return 2

        repo = install_mod.resolve_marketplace_repo(
            args.marketplace_repo, _cli_config()
        )
        try:
            steps = install_mod.plan(
                components,
                scope=args.scope,
                upgrade=self.upgrade,
                project_dir=Path(args.project_dir),
                marketplace_repo=repo,
                env=env,
            )
        except install_mod.InvalidMarketplace as exc:
            # Installing is code execution: an unvalidated source stops the run rather
            # than being "cleaned up" into something that looks close enough.
            logger.error("%s", exc)
            return 2

        if args.format == "table":
            # The header states what is about to be trusted, before it is trusted —
            # and it prints under --dry-run too, which is the point.
            plural = "s" if len(components) != 1 else ""
            print(
                f"the-loop {'upgrade' if self.upgrade else 'install'} · "
                f"component{plural}: {', '.join(components)} · scope: {args.scope}"
                + (f" ({Path(args.project_dir)})" if args.scope == "project" else "")
                + (
                    f" · marketplace: {repo}"
                    if any(name in install_mod.BINARIES for name in components)
                    else ""
                )
                + (" · dry run" if args.dry_run else "")
            )

        results = install_mod.execute(steps, dry_run=args.dry_run)
        print(render_json(results) if args.format == "json" else render_table(results))
        return install_mod.exit_code(results)


@register
class InstallCommand(_InstallBase):
    name = "install"
    help = "Install the-loop's CLI and its Claude Code / Cursor plugin (user or project scope)"
    upgrade = False


@register
class UpgradeCommand(_InstallBase):
    name = "upgrade"
    help = "Upgrade the-loop's CLI and its Claude Code / Cursor plugin to the current version"
    upgrade = True
