"""``the-loop scenarios`` — list the Gherkin scenarios covered by integration tests.

Every integration test in the-loop carries a Gherkin-syntax docstring (Feature/Scenario/
Given-When-Then), optionally linked to a requirements.md. This command scans the
configured integration-test globs, extracts those scenarios and presents them as a table
(default), a Markdown table, or JSON — so a coding-agent harness can query "what
scenarios are tested?" without running anything.

Globs come from ``--glob`` (repeatable) or, failing that, ``testing.integrationTestGlobs``
in the repository's harness config (read through :mod:`the_loop.harness_config`, which
also honours the pre-rename name — issue-82), else a built-in default set.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, List, Mapping, Sequence

from .base import Command, register
from ..client.routing import routed, service_error
from ..core import repo as core_repo

logger = logging.getLogger("the-loop.scenarios")


def render_json(scenarios: Sequence[Mapping[str, Any]]) -> str:
    return json.dumps(list(scenarios), indent=2)


def _rows(scenarios: Sequence[Mapping[str, Any]]) -> List[List[str]]:
    rows: List[List[str]] = []
    for i, s in enumerate(scenarios, start=1):
        location = f"{s['file']}:{s['line']}" if s.get("file") else str(s.get("line"))
        rows.append(
            [
                str(i),
                s.get("feature") or "—",
                s.get("scenario") or "—",
                s.get("requirement") or "—",
                location,
            ]
        )
    return rows


_HEADERS = ["#", "Feature", "Scenario", "Requirement", "Location"]


def render_table(scenarios: Sequence[Mapping[str, Any]]) -> str:
    """A plain, aligned ASCII table (no third-party dependency)."""
    rows = _rows(scenarios)
    widths = [len(h) for h in _HEADERS]
    for row in rows:
        for c, cell in enumerate(row):
            widths[c] = max(widths[c], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells))

    lines = [fmt(_HEADERS), "  ".join("-" * w for w in widths)]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def render_markdown(scenarios: Sequence[Mapping[str, Any]]) -> str:
    """A GitHub-flavoured Markdown table (pipes escaped)."""

    def esc(text: str) -> str:
        return text.replace("|", "\\|")

    lines = [
        "| " + " | ".join(_HEADERS) + " |",
        "|" + "|".join("---" for _ in _HEADERS) + "|",
    ]
    for row in _rows(scenarios):
        lines.append("| " + " | ".join(esc(cell) for cell in row) + " |")
    return "\n".join(lines)


_RENDERERS = {
    "table": render_table,
    "markdown": render_markdown,
    "json": render_json,
}


@register
class ScenariosCommand(Command):
    name = "scenarios"
    help = "List Gherkin scenarios covered by integration tests (table/markdown/json)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--root",
            default=".",
            help="Project root to scan (default: current directory).",
        )
        parser.add_argument(
            "--glob",
            action="append",
            dest="globs",
            metavar="PATTERN",
            help="Glob for integration-test files (repeatable). Overrides config/defaults.",
        )
        parser.add_argument(
            "--format",
            choices=sorted(_RENDERERS),
            default="table",
            help="Output format (default: table).",
        )

    def run(self, args: argparse.Namespace) -> int:
        root = str(Path(args.root))
        globs = list(args.globs or [])
        try:
            report = routed(
                lambda connection: connection.get(
                    "/repo/scenarios", params={"repo": root, "glob": globs}
                ),
                lambda: core_repo.scenarios(root, globs=globs),
            )
        except Exception as exc:  # noqa: BLE001 — mapped, or re-raised below
            mapped = service_error(exc)
            if mapped is None:
                mapped = (f"error: {exc}", 2)
            print(mapped[0], file=sys.stderr)
            return mapped[1]
        scenarios = report["scenarios"]
        print(_RENDERERS[args.format](scenarios))
        if args.format != "json" and not scenarios:
            logger.warning(
                "no scenarios found under %s for globs %s",
                report["repo"],
                report["globs"],
            )
        return 0
