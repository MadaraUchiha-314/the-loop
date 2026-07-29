"""``the-loop check`` and ``the-loop graph`` — the runtime's CLI surface.

``check`` is **pure**: no network, no subprocess, no mutation (R8.8). That is
what lets it run on every harness turn *and* in CI, and it is why CI runs the
same code the runtime does rather than a reimplementation of it.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .base import Command, register

logger = logging.getLogger("the-loop.graph")


def _load_harness_config(root: Path) -> Dict[str, Any]:
    """Best-effort read of the per-repo harness config (never fatal)."""
    import yaml

    for name in ("harness-config.yaml", "config.yaml"):
        path = root / ".the-loop" / name
        if path.is_file():
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                return {}
            return data if isinstance(data, dict) else {}
    return {}


def _runtime(root: Path):
    from ..graph.runtime import Runtime

    harness = _load_harness_config(root)
    workflow = harness.get("workflow") or {}
    config: Dict[str, Any] = {
        "phaseLabelPrefix": workflow.get("phaseLabelPrefix", "loop:"),
        "notifications": harness.get("notifications") or {},
    }
    try:
        from .. import cli_config

        cli_cfg = cli_config.load_cli_config(cli_config.default_cli_config_path()) or {}
    except Exception:  # noqa: BLE001 — the CLI config is optional for `check`
        cli_cfg = {}
    if isinstance(cli_cfg, dict):
        config["integrations"] = cli_cfg.get("integrations") or {}
        routing = ((cli_cfg.get("webhooks") or {}).get("ghWebhook") or {}).get(
            "routing"
        ) or {}
        config["authorizedUsers"] = routing.get("authorizedUsers") or []
    return Runtime(
        root,
        spec_root=str(workflow.get("specDir", "docs/specs")),
        config=config,
    )


def _discover_work_items(root: Path, spec_root: str) -> List[str]:
    base = root / spec_root
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def _split_at_pointer(nodes, current: str):
    """Split node reports into those up to the pointer and those beyond it.

    A node the work item has not reached yet is *expected* to be unmet — that is
    what "not done yet" looks like. Reporting it in the same voice as a genuine
    blocker is how a status view starts contradicting itself ("ok" printed above
    a wall of BLOCK lines), so the two are kept visually distinct.
    """
    for index, report in enumerate(nodes):
        if report.node == current:
            return nodes[: index + 1], nodes[index + 1 :]
    return list(nodes), []


def _render_table(reports, ahead=()) -> str:
    lines = []
    for report in reports:
        mark = {"pass": "ok", "skip": "--", "wait": "wait", "block": "BLOCK"}.get(
            report.status, report.status.upper()
        )
        flag = " (forced)" if report.forced else ""
        lines.append(f"  {mark:<6} {report.node}{flag}")
        for message in report.messages:
            lines.append(f"         · {message}")
    pending = [r for r in ahead if r.status not in ("pass", "skip")]
    if pending:
        lines.append(
            f"  ····   {len(pending)} node(s) not reached yet: "
            + ", ".join(r.node for r in pending)
        )
    return "\n".join(lines)


@register
class CheckCommand(Command):
    name = "check"
    help = "Evaluate a work item's nodes against its checked-in artifacts (read-only)."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("work_item", nargs="?", help="work item id, e.g. issue-109")
        parser.add_argument("--repo", default=".", help="repository root (default: .)")
        parser.add_argument("--format", choices=["table", "json"], default="table")
        parser.add_argument(
            "--all",
            action="store_true",
            help="evaluate every work item and report drift",
        )
        parser.add_argument(
            "--recompute",
            action="store_true",
            help="ignore graph state; derive completion from the artifacts alone",
        )

    def run(self, args: argparse.Namespace) -> int:
        root = Path(args.repo).resolve()
        try:
            runtime = _runtime(root)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}")
            return 2

        if args.all:
            items = _discover_work_items(root, runtime.spec_root)
        elif args.work_item:
            items = [args.work_item]
        else:
            print("error: give a work item id, or --all")
            return 2

        payload = []
        failing = 0
        for item in items:
            report = runtime.status(item, recompute=args.recompute)
            payload.append(report.as_dict())
            if not report.ok:
                failing += 1

        if args.format == "json":
            print(json.dumps(payload if args.all else payload[0], indent=2))
        else:
            for report in payload:
                state = "ok" if report["ok"] else "UNMET"
                print(f"{report['workItem']}: {state} (at {report['currentNode']})")
                # Only nodes at or before the pointer are findings; anything
                # beyond it is simply not done yet, and saying "BLOCK" about it
                # would make an ok work item read as a broken one.
                reached = []
                for entry in report["nodes"]:
                    reached.append(entry)
                    if entry["node"] == report["currentNode"]:
                        break
                unmet = [r for r in reached if r["status"] not in ("pass", "skip")]
                if unmet and (not args.all or not report["ok"]):
                    for entry in unmet[:1] if args.all else unmet:
                        print(f"  {entry['status'].upper():<6} {entry['node']}")
                        for message in entry["messages"]:
                            print(f"         · {message}")
                ahead = [
                    r
                    for r in report["nodes"][len(reached) :]
                    if r["status"] not in ("pass", "skip")
                ]
                if ahead and not args.all:
                    print(f"  ····   {len(ahead)} node(s) not reached yet")
            if args.all:
                print(f"\n{len(payload) - failing}/{len(payload)} work items satisfied")
        return 1 if failing else 0


@register
class GraphCommand(Command):
    name = "graph"
    help = "Inspect and drive the-loop's process graph."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--repo", default=".", help="repository root (default: .)")
        sub = parser.add_subparsers(dest="action", required=True)

        show = sub.add_parser("show", help="print the shipped graph")
        show.add_argument("--format", choices=["text", "json"], default="text")

        status = sub.add_parser("status", help="where a work item is")
        status.add_argument("work_item")

        advance = sub.add_parser("advance", help="evaluate and take the matching edge")
        advance.add_argument("work_item")
        advance.add_argument("--ref", default="", help="work item ref for integrations")

        forced = sub.add_parser(
            "force",
            help="move a work item to a node regardless of gates (escape hatch)",
        )
        forced.add_argument("work_item")
        forced.add_argument("--to", required=True, help="target node id")
        forced.add_argument("--reason", required=True, help="why (required)")
        forced.add_argument("--actor", default="", help="who is forcing this")
        forced.add_argument("--ref", default="")

        run = sub.add_parser(
            "run", help="drive a work item until it waits, escalates or completes"
        )
        run.add_argument("work_item")
        run.add_argument("--ref", default="")
        run.add_argument(
            "--max-nodes", type=int, default=20, help="safety bound on advances"
        )
        run.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would happen without writing state",
        )

    def run(self, args: argparse.Namespace) -> int:
        root = Path(args.repo).resolve()
        try:
            runtime = _runtime(root)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {exc}")
            return 2

        if args.action == "show":
            graph = runtime.graph
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "version": graph.version,
                            "start": graph.start,
                            "nodes": [n.as_mapping() for n in graph.ordered()],
                            "edges": [
                                {"from": e.source, "to": e.target, "on": e.on}
                                for e in graph.edges
                            ],
                        },
                        indent=2,
                    )
                )
            else:
                print(f"graph v{graph.version}, start: {graph.start}")
                for node in graph.ordered():
                    flags = []
                    if node.required:
                        flags.append("required")
                    if node.actor == "human":
                        flags.append("human")
                    if node.terminal:
                        flags.append("terminal")
                    suffix = f"  [{', '.join(flags)}]" if flags else ""
                    print(f"  {node.id}{suffix}")
                    for edge in graph.edges_from(node.id):
                        print(f"      --{edge.on}--> {edge.target}")
            return 0

        if args.action == "status":
            report = runtime.status(args.work_item)
            reached, ahead = _split_at_pointer(report.nodes, report.current_node)
            print(f"{report.work_item}: at {report.current_node}")
            print(_render_table(reached, ahead))
            return 0 if report.ok else 1

        if args.action == "advance":
            result = runtime.advance(args.work_item, ref=args.ref)
            print(f"{args.work_item}: {result.node} → {result.status}")
            for message in result.messages:
                print(f"  · {message}")
            return 0 if result.status in ("pass", "wait") else 1

        if args.action == "run":
            return self._run_loop(runtime, args)

        if args.action == "force":
            from ..graph.runtime import force

            try:
                result = force(
                    runtime,
                    args.work_item,
                    args.to,
                    args.reason,
                    actor=args.actor,
                    ref=args.ref,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"refused: {exc}")
                return 2
            print(f"forced {result.work_item}: {result.from_node} → {result.to_node}")
            print(f"  reason: {result.reason}")
            for warning in result.warnings:
                print(f"  WARNING: {warning}")
            print(
                "  note: this moved the pointer only — the bypassed gate keeps its "
                "real verdict, so `the-loop check --recompute` will still report it."
            )
            return 0

        return 2

    @staticmethod
    def _run_loop(runtime, args) -> int:
        """Advance until the work item waits, escalates or reaches a terminal node.

        Bounded by ``--max-nodes`` — a runaway loop is the one failure mode a
        deterministic driver can still have, so it gets an explicit ceiling
        rather than trust.
        """
        if args.dry_run:
            report = runtime.status(args.work_item)
            reached, ahead = _split_at_pointer(report.nodes, report.current_node)
            print(
                f"{args.work_item}: at {report.current_node} (dry run — nothing written)"
            )
            print(_render_table(reached, ahead))
            return 0 if report.ok else 1

        seen: List[str] = []
        for _ in range(max(1, args.max_nodes)):
            result = runtime.advance(args.work_item, ref=args.ref)
            print(f"  {result.node}: {result.status}")
            for message in result.messages:
                print(f"      · {message}")
            if result.status in ("wait", "block", "escalated"):
                print(f"{args.work_item}: stopped at {result.node} ({result.status})")
                return 0 if result.status == "wait" else 1
            node = runtime.graph.node(result.node)
            if node.terminal:
                print(f"{args.work_item}: complete")
                return 0
            seen.append(result.node)
            if seen.count(result.node) > 2:
                print(f"{args.work_item}: looping on {result.node}; stopping")
                return 1
        print(f"{args.work_item}: hit --max-nodes ({args.max_nodes}); stopping")
        return 1
