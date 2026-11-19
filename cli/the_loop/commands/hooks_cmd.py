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
from .. import cli_config, strings
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
            "error": strings.t(
                "cli.hooks.read-report.could-not-read",
                path=path,
                exc_type=exc.__class__.__name__,
                exc=exc,
            ),
        }
    return {
        "config": str(path),
        "hooks": [entry.as_dict() for entry in declaration.entries],
    }


def _on(entry: Dict[str, Any]) -> str:
    if entry["on"]:
        return ", ".join(entry["on"])
    if entry["kind"] == "url":
        return strings.t("cli.hooks.on.every-point")
    return strings.t("cli.hooks.on.class-points")


def render_list(report: Dict[str, Any]) -> List[str]:
    if report.get("error"):
        return [strings.t("cli.hooks.render-list.error", error=report["error"])]
    hooks = report["hooks"]
    if not hooks:
        return [
            strings.t(
                "cli.hooks.render-list.none-declared",
                config_key=CONFIG_KEY,
                config=report["config"],
            ),
            strings.t("cli.hooks.render-list.points-hint"),
        ]
    lines = [
        strings.t(
            "cli.hooks.render-list.heading", n_hooks=len(hooks), config=report["config"]
        )
    ]
    width = max(len(h["name"]) for h in hooks)
    for h in hooks:
        parts = [
            f"{h['kind']} {h['target']}",
            strings.t("cli.hooks.render-list.on", on=_on(h)),
        ]
        if h["kind"] == "url":
            parts.append(
                strings.t(
                    "cli.hooks.render-list.timeout", timeout_seconds=h["timeoutSeconds"]
                )
            )
            if h.get("tokenEnv"):
                parts.append(
                    strings.t("cli.hooks.render-list.token", token_env=h["tokenEnv"])
                )
        else:
            if h.get("executor"):
                parts.append(
                    strings.t("cli.hooks.render-list.executor", executor=h["executor"])
                )
            if h.get("with"):
                parts.append(strings.t("cli.hooks.render-list.with", with_=h["with"]))
        if h["required"]:
            parts.append(strings.t("cli.hooks.render-list.required"))
        if not h["enabled"]:
            parts.append(strings.t("cli.hooks.render-list.disabled"))
        lines.append(f"  {h['name'].ljust(width)}  " + "   ".join(parts))
    lines.append(strings.t("cli.hooks.render-list.load-note"))
    return lines


def render_points(rows: Sequence[Dict[str, Any]]) -> List[str]:
    lines = [strings.t("cli.hooks.render-points.heading", n_rows=len(rows))]
    for row in rows:
        lines.append(f"\n  {row['point']}  ({row['context']})")
        lines.append(strings.t("cli.hooks.render-points.fires", fires=row["fires"]))
        lines.append(
            strings.t("cli.hooks.render-points.facts", facts=", ".join(row["facts"]))
        )
        lines.append(
            strings.t(
                "cli.hooks.render-points.decisions",
                decisions=", ".join(row["decisions"])
                or strings.t("cli.hooks.render-points.none"),
            )
        )
    return lines


@register
class HooksCommand(Command):
    name = "hooks"
    help = strings.t("cli.hooks.help")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "action",
            nargs="?",
            choices=("list", "points"),
            default="list",
            help=strings.t("cli.hooks.action.help"),
        )
        parser.add_argument(
            "--format",
            choices=("text", "json"),
            default="text",
            help=strings.t("cli.hooks.format.help"),
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
