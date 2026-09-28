"""``the-loop hooks [list|points]`` — what the operator's lifecycle hooks declare, and the
points they can attach to (issue-344, R5).

Deliberately inert, like ``graph hooks`` and ``critic list``: the declaration is read
**strictly** and reported, and no module is imported and no URL contacted. The whole point
is that an operator reads what would run — and where — before a work item does. A daemon
loads the declaration at start (and refuses to start on one it cannot load); this command
finds the mistake first.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Sequence

from .base import Command, register
from .. import cli_config
from ..lifecycle import CONFIG_KEY, HooksConfigError, read_declaration
from ..lifecycle.contract import describe

_EXIT_OK = 0
_EXIT_ERROR = 1


def _strict_config() -> Dict[str, Any]:
    path = cli_config.default_cli_config_path()
    if not path.is_file():
        return {}
    loaded = cli_config.load_cli_config(path, strict=True) or {}
    return loaded if isinstance(loaded, dict) else {}


def declared() -> Dict[str, Any]:
    """The declaration as a report — or ``{"error": …}`` when it cannot be read."""
    path = cli_config.default_cli_config_path()
    try:
        declaration = read_declaration(_strict_config())
    except HooksConfigError as exc:
        return {"config": str(path), "hooks": [], "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — the report IS the error
        return {
            "config": str(path),
            "hooks": [],
            "error": f"could not read {path}: {exc.__class__.__name__}: {exc}",
        }
    return {
        "config": str(path),
        "hooks": [entry.as_dict() for entry in declaration.entries],
    }


def _on(entry: Dict[str, Any]) -> str:
    if entry["on"]:
        return ", ".join(entry["on"])
    if entry["kind"] == "url":
        return "every point"
    return "the points the class overrides"


def render_list(report: Dict[str, Any]) -> List[str]:
    if report.get("error"):
        return [f"error: {report['error']}"]
    hooks = report["hooks"]
    if not hooks:
        return [
            f"no lifecycle hooks declared (top-level `{CONFIG_KEY}` in {report['config']})",
            "`the-loop hooks points` lists the points a hook can attach to.",
        ]
    lines = [
        f"lifecycle hooks ({len(hooks)} declared in {report['config']}) — nothing here "
        "has been imported or contacted:"
    ]
    width = max(len(h["name"]) for h in hooks)
    for h in hooks:
        parts = [f"{h['kind']} {h['target']}", f"on: {_on(h)}"]
        if h["kind"] == "url":
            parts.append(f"timeout {h['timeoutSeconds']:g}s")
            if h.get("tokenEnv"):
                parts.append(f"token ${h['tokenEnv']}")
        else:
            if h.get("executor"):
                parts.append(f"executor {h['executor']}")
            if h.get("with"):
                parts.append(f"with: {h['with']}")
        if h["required"]:
            parts.append("required")
        if not h["enabled"]:
            parts.append("DISABLED")
        lines.append(f"  {h['name'].ljust(width)}  " + "   ".join(parts))
    lines.append(
        "\na daemon loads the declaration at start and refuses to start on one it "
        "cannot load; a one-shot command loads it on first use and runs hookless, "
        "recording `hooks.load_failed`, when it cannot."
    )
    return lines


def render_points(rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = [f"lifecycle points ({len(rows)}):"]
    for row in rows:
        lines.append(f"\n  {row['point']}  ({row['context']})")
        lines.append(f"    fires:     {row['fires']}")
        lines.append(f"    facts:     {', '.join(row['facts'])}")
        lines.append(f"    decisions: {', '.join(row['decisions']) or '(none)'}")
    return lines


@register
class HooksCommand(Command):
    name = "hooks"
    help = (
        "Report the lifecycle hooks the CLI config declares (importing nothing), or "
        "the points they can attach to"
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "action",
            nargs="?",
            choices=("list", "points"),
            default="list",
            help="list (default): the declaration; points: the catalog of hook points",
        )
        parser.add_argument(
            "--format", choices=("text", "json"), default="text", help="output format"
        )

    def run(self, args: argparse.Namespace) -> int:
        if args.action == "points":
            rows = describe()
            if args.format == "json":
                print(json.dumps({"points": rows}, indent=2))
            else:
                print("\n".join(render_points(rows)))
            return _EXIT_OK
        report = declared()
        if args.format == "json":
            print(json.dumps(report, indent=2))
        else:
            print("\n".join(render_list(report)))
        return _EXIT_ERROR if report.get("error") else _EXIT_OK
