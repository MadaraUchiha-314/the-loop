"""``the-loop models list|check`` — what this machine's harnesses will actually run.

Issue-358. The operator declares models and effort levels; **this** is what makes the
declaration true. ``check`` asks each harness whether it can run each declared name, in
the cheapest way that still proves it, and caches the verdicts. ``list`` prints what is
already known without asking anything.

It exists because the declaration alone cannot answer the question. A model name is the
provider's identifier and the-loop neither normalises it nor parses it for a vendor, so
the only way to know whether *this* machine's Claude Code can run ``gpt-5.6-sol`` is to
ask it. That measurement is also what lets ``models`` be a plain list with no harness
attached: the model × harness relation is observed, not declared (decision-124).

Repo-scoped like ``critic`` and ``scenarios``: it reads the operator's CLI config and
this machine's binaries, and it is not part of the daemon.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List, Sequence

from .base import Command, register
from .sessions_cmd import _cli_config
from ..harness import build_adapters
from ..modelchoice import (
    EFFORT_LEVELS,
    candidate_harnesses,
    config_findings,
    declared_effort,
    declared_harnesses,
    declared_models,
)
from ..modelprobe import (
    REFUSED,
    UNKNOWN,
    VerdictCache,
    Verdict,
    digest,
    probe,
    resolved_args,
)
from ..state import layout_from_config

_HEADERS = ["Harness", "Kind", "Name", "Verdict", "Checked"]

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_MISCONFIGURED = 2


def _harnesses(config: dict) -> List[str]:
    """Declared harnesses, else the routing default — what every install has."""
    declared = declared_harnesses(config)
    if declared:
        return declared
    fallback = str(((config.get("routing") or {}).get("defaultHarness")) or "")
    return [fallback] if fallback else []


def _combinations(config: dict) -> List[tuple]:
    """Every ``(harness, kind, name)`` worth asking about.

    A bare model is a candidate for every declared harness; one that narrowed
    itself is asked only about the harnesses it named. Effort levels are asked
    about every harness, because the mapping is **the-loop's own assertion** about
    that harness's CLI — exactly the kind of claim that must be checked rather
    than trusted.
    """
    pairs = []
    for name in declared_models(config):
        for harness in candidate_harnesses(config, name) or _harnesses(config):
            pairs.append((harness, "model", name))
    for level in declared_effort(config):
        for harness in _harnesses(config):
            pairs.append((harness, "effort", level))
    return pairs


def _age(checked_at: float) -> str:
    if not checked_at:
        return "—"
    seconds = max(0, int(time.time() - checked_at))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    return f"{seconds // 3600}h ago"


def _render(rows: Sequence[Dict[str, Any]]) -> str:
    cells = [
        [
            str(row["harness"]),
            str(row["kind"]),
            str(row["name"]),
            str(row["verdict"]),
            str(row["checked"]),
        ]
        for row in rows
    ]
    widths = [len(h) for h in _HEADERS]
    for line in cells:
        for index, cell in enumerate(line):
            widths[index] = max(widths[index], len(cell))

    def fmt(values: Sequence[str]) -> str:
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values))

    return "\n".join([fmt(_HEADERS)] + [fmt(line) for line in cells])


@register
class ModelsCommand(Command):
    name = "models"
    help = "List the declared models and effort levels, and check what each harness accepts"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        lst = actions.add_parser(
            "list",
            help="Print the declared models and effort levels with their cached verdicts",
        )
        lst.add_argument(
            "--format",
            choices=("table", "json"),
            default="table",
            help="Output format (default: table).",
        )
        lst.set_defaults(_action=self._list)

        check = actions.add_parser(
            "check",
            help=(
                "Ask each harness whether it can run each declared model and effort "
                "level, and cache the answers"
            ),
            description=(
                "Runs each harness once per declared combination with a fixed "
                "the-loop prompt — never any text from a work item — and records "
                "ok / refused / unknown. A refused choice is then never offered on "
                "a phase-selection checklist, so nobody can pick a model that would "
                "leave a session dead in a pane nobody is watching."
            ),
        )
        check.add_argument(
            "--format",
            choices=("table", "json"),
            default="table",
            help="Output format (default: table).",
        )
        check.add_argument(
            "--refresh",
            action="store_true",
            help="Re-probe every combination, even ones with a standing verdict.",
        )
        check.set_defaults(_action=self._check)

    def run(self, args: argparse.Namespace) -> int:
        return args._action(args)

    # -- actions ----------------------------------------------------------------

    def _list(self, args: argparse.Namespace) -> int:
        config = _cli_config()
        cache = VerdictCache(layout_from_config(config).verdict_cache)
        rows = []
        for harness, kind, name in _combinations(config):
            verdict = cache.get(harness, kind, name)
            rows.append(
                {
                    "harness": harness,
                    "kind": kind,
                    "name": name,
                    "verdict": verdict.verdict if verdict else "unprobed",
                    "checked": _age(verdict.checked_at if verdict else 0.0),
                }
            )
        return self._emit(args, config, rows)

    def _check(self, args: argparse.Namespace) -> int:
        config = _cli_config()
        cache = VerdictCache(layout_from_config(config).verdict_cache)
        adapters = build_adapters(
            ((config.get("routing") or {}).get("harnessArgs")) or {}
        )
        rows: List[Dict[str, Any]] = []
        fresh: List[Verdict] = []
        for harness, kind, name in _combinations(config):
            adapter = adapters.get(harness)
            if adapter is None:
                rows.append(
                    {
                        "harness": harness,
                        "kind": kind,
                        "name": name,
                        "verdict": UNKNOWN,
                        "checked": "no adapter",
                    }
                )
                continue
            args_digest = digest(resolved_args(kind, name, adapter))
            standing = (
                None
                if args.refresh
                else cache.get(harness, kind, name, args_digest=args_digest)
            )
            verdict = standing or probe(kind, name, adapter)
            if standing is None:
                fresh.append(verdict)
            rows.append(
                {
                    "harness": harness,
                    "kind": kind,
                    "name": name,
                    "verdict": verdict.verdict,
                    "checked": _age(verdict.checked_at),
                }
            )
        if fresh:
            cache.put_all(fresh)
        return self._emit(args, config, rows)

    # -- output -----------------------------------------------------------------

    def _emit(self, args: argparse.Namespace, config: dict, rows: List[dict]) -> int:
        findings = config_findings(
            config,
            build_adapters(((config.get("routing") or {}).get("harnessArgs")) or {}),
        )
        if args.format == "json":
            print(
                json.dumps(
                    {
                        "effortLevels": list(EFFORT_LEVELS),
                        "verdicts": rows,
                        "findings": [
                            {"level": f.level, "where": f.where, "message": f.message}
                            for f in findings
                        ],
                    },
                    indent=2,
                )
            )
        else:
            if rows:
                print(_render(rows))
            else:
                print(
                    "nothing declared — set the top-level `models` and `effort` in "
                    "the CLI config to offer a work item a choice"
                )
            for finding in findings:
                print(f"{finding.level}: {finding.where}: {finding.message}")
        if any(f.level == "error" for f in findings):
            return _EXIT_MISCONFIGURED
        if any(row["verdict"] == REFUSED for row in rows):
            return _EXIT_REFUSED
        return _EXIT_OK
