"""``the-loop scenarios`` — list the Gherkin scenarios covered by integration tests.

Every integration test in the-loop carries a Gherkin-syntax docstring (Feature/Scenario/
Given-When-Then), optionally linked to a requirements.md. This command scans the
configured integration-test globs, extracts those scenarios and presents them as a table
(default), a Markdown table, or JSON — so a coding-agent harness can query "what
scenarios are tested?" without running anything.

Globs come from ``--glob`` (repeatable) or, failing that, ``testing.integrationTestGlobs``
in ``.the-loop/harness-config.yaml`` (when PyYAML is available; the pre-rename
``config.yaml`` is still honored — issue-82), else a built-in default set.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Sequence

from .base import Command, register
from ..scenarios import DEFAULT_GLOBS, Scenario, collect_scenarios

logger = logging.getLogger("the-loop.scenarios")


def _load_config_globs(root: Path) -> List[str]:
    """Best-effort read of testing.integrationTestGlobs from the harness config.

    Reads ``.the-loop/harness-config.yaml``, falling back to the pre-rename
    ``.the-loop/config.yaml`` (issue-82, decision-035) so repos that have not run
    /the-loop:upgrade-the-loop keep working. Returns ``[]`` if no file or PyYAML
    is unavailable — the CLI must work with zero runtime dependencies.
    """
    candidates = [
        root / ".the-loop" / "harness-config.yaml",
        root / ".the-loop" / "config.yaml",  # pre-rename fallback
    ]
    cfg_path = next((p for p in candidates if p.is_file()), None)
    if cfg_path is None:
        return []
    try:
        import yaml  # optional dependency
    except ImportError:
        logger.debug("pyyaml not installed; skipping config-file globs")
        return []
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:  # noqa: BLE001
        logger.warning("could not parse %s; using default globs", cfg_path)
        return []
    globs = ((data.get("testing") or {}).get("integrationTestGlobs")) or []
    return [str(g) for g in globs]


def render_json(scenarios: Sequence[Scenario]) -> str:
    return json.dumps([s.as_dict() for s in scenarios], indent=2)


def _rows(scenarios: Sequence[Scenario]) -> List[List[str]]:
    rows: List[List[str]] = []
    for i, s in enumerate(scenarios, start=1):
        location = f"{s.file}:{s.line}" if s.file else str(s.line)
        rows.append(
            [
                str(i),
                s.feature or "—",
                s.scenario or "—",
                s.requirement or "—",
                location,
            ]
        )
    return rows


_HEADERS = ["#", "Feature", "Scenario", "Requirement", "Location"]


def render_table(scenarios: Sequence[Scenario]) -> str:
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


def render_markdown(scenarios: Sequence[Scenario]) -> str:
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
        root = Path(args.root)
        globs = args.globs or _load_config_globs(root) or DEFAULT_GLOBS
        scenarios = collect_scenarios(root, globs)
        output = _RENDERERS[args.format](scenarios)
        print(output)
        if args.format != "json" and not scenarios:
            logger.warning("no scenarios found under %s for globs %s", root, globs)
        return 0
