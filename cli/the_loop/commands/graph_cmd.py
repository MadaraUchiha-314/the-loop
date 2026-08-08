"""``the-loop check`` and ``the-loop graph`` — the runtime's CLI surface.

The **core** check operation is pure: no network, no subprocess, no mutation
(R8.8) — which is what lets the same code run on every harness turn *and* in
CI. Since issue-161 the purity lives in :mod:`the_loop.core.graphs`; this
command routes through the control-plane service (the CLI's only execution
path for core capabilities, decision-058), and the one hop to loopback is
transport, not evaluation.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from .base import Command, register
from ..client.routing import routed, service_error
from ..core import graphs as core_graphs

logger = logging.getLogger("the-loop.graph")


def _report(exc: Exception) -> int:
    """A client-side failure as the CLI's ``(message, exit code)``.

    Graph commands print bare ``error: …`` on stdout (they predate the split),
    so the mapping is shared but the stream is theirs.
    """
    mapped = service_error(exc)
    if mapped is None:
        mapped = (f"error: {exc}", 2)
    print(mapped[0])
    return mapped[1]


def _is_bad_request(exc: Exception) -> bool:
    """Whether ``exc`` is core saying "you asked for something invalid".

    A refused ``force`` looks the same either way: ``ValueError`` in-process,
    HTTP 400 over the service, because that is exactly how the API maps it.
    """
    from ..client import ApiError

    return isinstance(exc, ValueError) or (
        isinstance(exc, ApiError) and exc.status == 400
    )


def _detail(exc: Exception) -> str:
    from ..client import ApiError

    return exc.detail if isinstance(exc, ApiError) and exc.detail else str(exc)


def _show(root: Path, pr: "int | None" = None) -> Dict[str, Any]:
    """The repo's graph, its start node and its spec root — one round trip."""
    params: Dict[str, Any] = {"repo": str(root)}
    if pr is not None:
        params["pr"] = pr
    return routed(
        lambda connection: connection.get("/graph", params=params),
        lambda: core_graphs.show(str(root), pr=pr),
    )


def _check(
    root: Path, work_item: str, recompute: bool = False, pr: "int | None" = None
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/check",
            {
                "repo": str(root),
                "workItem": work_item,
                "recompute": bool(recompute),
                "pr": pr,
            },
        ),
        lambda: core_graphs.check(str(root), work_item, recompute=recompute, pr=pr),
    )


def _advance(
    root: Path, work_item: str, ref: str = "", pr: "int | None" = None
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/advance",
            {"repo": str(root), "workItem": work_item, "ref": ref, "pr": pr},
        ),
        lambda: core_graphs.advance(str(root), work_item, ref=ref, pr=pr),
    )


def _complete(
    root: Path,
    work_item: str,
    node: str = "",
    actor: str = "",
    ref: str = "",
    pr: "int | None" = None,
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/complete",
            {
                "repo": str(root),
                "workItem": work_item,
                "node": node,
                "actor": actor,
                "ref": ref,
                "pr": pr,
            },
        ),
        lambda: core_graphs.complete(
            str(root), work_item, node=node, actor=actor, ref=ref, pr=pr
        ),
    )


def _force(
    root: Path,
    work_item: str,
    to_node: str,
    reason: str,
    actor: str,
    ref: str,
    pr: "int | None" = None,
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/force",
            {
                "repo": str(root),
                "workItem": work_item,
                "toNode": to_node,
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
            },
        ),
        lambda: core_graphs.force(
            str(root), work_item, to_node, reason, actor=actor, ref=ref, pr=pr
        ),
    )


def _skip(
    root: Path,
    work_item: str,
    nodes: List[str],
    reason: str,
    actor: str,
    ref: str,
    pr: "int | None" = None,
) -> Dict[str, Any]:
    return routed(
        lambda connection: connection.post(
            "/graph/skip",
            {
                "repo": str(root),
                "workItem": work_item,
                "nodes": list(nodes),
                "reason": reason,
                "actor": actor,
                "ref": ref,
                "pr": pr,
            },
        ),
        lambda: core_graphs.skip(
            str(root), work_item, nodes, reason, actor=actor, ref=ref, pr=pr
        ),
    )


def _discover_work_items(root: Path, spec_root: str) -> List[str]:
    base = root / spec_root
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


def _split_at_pointer(nodes: List[Dict[str, Any]], current: str):
    """Split node reports into those up to the pointer and those beyond it.

    A node the work item has not reached yet is *expected* to be unmet — that is
    what "not done yet" looks like. Reporting it in the same voice as a genuine
    blocker is how a status view starts contradicting itself ("ok" printed above
    a wall of BLOCK lines), so the two are kept visually distinct.
    """
    for index, report in enumerate(nodes):
        if report["node"] == current:
            return nodes[: index + 1], nodes[index + 1 :]
    return list(nodes), []


def _fails(report: Dict[str, Any], fail_on: str) -> bool:
    """Whether this report should make the process exit non-zero.

    ``unmet`` — anything not satisfied, a human-wait included. What you want
    when you are *asking* where a work item stands.

    ``block`` — only a node an agent can actually fix. What an automated gate
    wants: a work item parked at a human-approval node is the normal state of an
    open PR, so failing CI for it would make the gate red by construction, and a
    gate that is always red is one people learn to merge past.
    """
    if fail_on == "unmet":
        return not report["ok"]
    current = report.get("currentNode")
    for node in report.get("nodes") or []:
        if node.get("node") == current:
            return node.get("status") == "block"
        if node.get("status") == "block":
            return True  # an earlier node is broken; the pointer moved past it
    return False


def _render_table(reports, ahead=()) -> str:
    lines = []
    for report in reports:
        status = report["status"]
        mark = {"pass": "ok", "skip": "--", "wait": "wait", "block": "BLOCK"}.get(
            status, status.upper()
        )
        flag = " (forced)" if report.get("forced") else ""
        lines.append(f"  {mark:<6} {report['node']}{flag}")
        for message in report.get("messages") or []:
            lines.append(f"         · {message}")
    pending = [r for r in ahead if r["status"] not in ("pass", "skip")]
    if pending:
        lines.append(
            f"  ····   {len(pending)} node(s) not reached yet: "
            + ", ".join(r["node"] for r in pending)
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
        parser.add_argument(
            "--fail-on",
            choices=["unmet", "block"],
            default="unmet",
            help=(
                "what makes this command exit non-zero. 'unmet' (default) is any "
                "node that is not satisfied, including one waiting on a human — "
                "what you want when asking where something stands. 'block' is only "
                "a node an agent can actually fix, which is what an automated gate "
                "wants: a PR waiting on its reviewer is the normal state of an open "
                "PR, and failing CI for it would make the gate red by construction."
            ),
        )

    def run(self, args: argparse.Namespace) -> int:
        root = Path(args.repo).resolve()
        try:
            return self._report_on(root, args)
        except Exception as exc:  # noqa: BLE001 — every failure is a message
            return _report(exc)

    def _report_on(self, root: Path, args: argparse.Namespace) -> int:
        if args.all:
            items = _discover_work_items(root, _show(root)["specRoot"])
        elif args.work_item:
            items = [args.work_item]
        else:
            print("error: give a work item id, or --all")
            return 2

        payload = []
        failing = 0
        for item in items:
            data = _check(root, item, recompute=args.recompute)
            payload.append(data)
            if _fails(data, args.fail_on):
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
        show.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

        status = sub.add_parser("status", help="where a work item is")
        status.add_argument("work_item")
        status.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

        advance = sub.add_parser("advance", help="evaluate and take the matching edge")
        advance.add_argument("work_item")
        advance.add_argument("--ref", default="", help="work item ref for integrations")
        advance.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

        complete = sub.add_parser(
            "complete",
            help=(
                "claim the current node's work is done: evaluate its exit chain "
                "and advance if it passes (issue-148). The claim is a prompt to "
                "evaluate, never a verdict — output is one JSON envelope."
            ),
        )
        complete.add_argument("work_item")
        complete.add_argument(
            "--node",
            default="",
            help="the node being claimed (default: the current node)",
        )
        complete.add_argument(
            "--ref", default="", help="work item ref for integrations"
        )
        complete.add_argument("--actor", default="", help="who is claiming completion")
        complete.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

        forced = sub.add_parser(
            "force",
            help="move a work item to a node regardless of gates (escape hatch)",
        )
        forced.add_argument("work_item")
        forced.add_argument("--to", required=True, help="target node id")
        forced.add_argument("--reason", required=True, help="why (required)")
        forced.add_argument("--actor", default="", help="who is forcing this")
        forced.add_argument("--ref", default="")
        forced.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

        skip = sub.add_parser(
            "skip",
            help=(
                "declare phases skipped for a work item (issue-177). Tokens are "
                "skippable node ids or shipped skip-set names (e.g. spec-chain); "
                "protected gates are not in the vocabulary, and a node the "
                "pointer already reached is refused. A declaration routes the "
                "pointer around the node and is reported as 'skipped by "
                "declaration' — never as a pass."
            ),
        )
        skip.add_argument("work_item")
        skip.add_argument(
            "--node",
            action="append",
            required=True,
            dest="nodes",
            help="a skippable node id or skip-set name (repeatable)",
        )
        skip.add_argument("--reason", required=True, help="why (required)")
        skip.add_argument("--actor", default="", help="who is declaring this")
        skip.add_argument("--ref", default="", help="work item ref for integrations")
        skip.add_argument(
            "--pr",
            type=int,
            default=None,
            help="walk this pull request's inner loop (pdlc-pr-loop, state under pr-loops/pr-<n>/) instead of the work item's outer loop",
        )

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
            return self._dispatch(root, args)
        except Exception as exc:  # noqa: BLE001 — every failure is a message
            return _report(exc)

    def _dispatch(self, root: Path, args: argparse.Namespace) -> int:
        if args.action == "show":
            graph = _show(root, pr=args.pr)
            if args.format == "json":
                # ``specRoot`` is a layout fact the runtime carries, not part of
                # the graph an operator asked to see, so it stays out of here.
                print(
                    json.dumps(
                        {k: v for k, v in graph.items() if k != "specRoot"}, indent=2
                    )
                )
                return 0
            print(f"graph v{graph['version']}, start: {graph['start']}")
            edges = graph["edges"]
            for node in graph["nodes"]:
                flags = []
                if node.get("required"):
                    flags.append("required")
                if node.get("skippable"):
                    flags.append("skippable")
                if node.get("actor") == "human":
                    flags.append("human")
                if node.get("terminal"):
                    flags.append("terminal")
                suffix = f"  [{', '.join(flags)}]" if flags else ""
                print(f"  {node['id']}{suffix}")
                for edge in edges:
                    if edge["from"] == node["id"]:
                        print(f"      --{edge['on']}--> {edge['to']}")
            return 0

        if args.action == "status":
            report = _check(root, args.work_item, pr=args.pr)
            reached, ahead = _split_at_pointer(report["nodes"], report["currentNode"])
            print(f"{report['workItem']}: at {report['currentNode']}")
            print(_render_table(reached, ahead))
            return 0 if report["ok"] else 1

        if args.action == "advance":
            result = _advance(root, args.work_item, ref=args.ref, pr=args.pr)
            print(f"{args.work_item}: {result['node']} → {result['status']}")
            for message in result["messages"]:
                print(f"  · {message}")
            return 0 if result["status"] in ("pass", "wait") else 1

        if args.action == "complete":
            # One JSON envelope on stdout, machine-readable (R1.3). A refusal
            # or a block is a *result* the agent acts on, not a CLI error —
            # exit 0 either way; non-zero is reserved for not being able to
            # answer at all.
            result = _complete(
                root,
                args.work_item,
                node=args.node,
                actor=args.actor,
                ref=args.ref,
                pr=args.pr,
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.action == "skip":
            try:
                result = _skip(
                    root,
                    args.work_item,
                    args.nodes,
                    args.reason,
                    args.actor,
                    args.ref,
                    pr=args.pr,
                )
            except Exception as exc:  # noqa: BLE001
                # A refused declaration is the runtime's verdict, not a broken
                # CLI — same contract as a refused force.
                if not _is_bad_request(exc) and service_error(exc) is not None:
                    raise
                print(f"refused: {_detail(exc)}")
                return 2
            for node in result["declared"]:
                print(f"declared: {node} will be skipped")
            for entry in result["rejected"]:
                print(f"rejected: {entry['token']} — {entry['why']}")
            if result["declared"]:
                print(
                    "  note: these are declarations, not verdicts — `the-loop "
                    "check` reports each node as 'skipped by declaration', and "
                    "the never-skippable gates still run."
                )
            return 0 if result["declared"] else 1

        if args.action == "run":
            return self._run_loop(root, args)

        if args.action == "force":
            try:
                result = _force(
                    root,
                    args.work_item,
                    args.to,
                    args.reason,
                    args.actor,
                    args.ref,
                    pr=args.pr,
                )
            except Exception as exc:  # noqa: BLE001
                # A refused force is the runtime's verdict, not a broken CLI —
                # it keeps its own word. Only a transport failure (unreachable
                # service) falls through to the shared "error:" mapping.
                if not _is_bad_request(exc) and service_error(exc) is not None:
                    raise
                print(f"refused: {_detail(exc)}")
                return 2
            print(
                f"forced {result['workItem']}: {result['fromNode']} → {result['toNode']}"
            )
            print(f"  reason: {result['reason']}")
            for warning in result["warnings"]:
                print(f"  WARNING: {warning}")
            print(
                "  note: this moved the pointer only — the bypassed gate keeps its "
                "real verdict, so `the-loop check --recompute` will still report it."
            )
            return 0

        return 2

    @staticmethod
    def _run_loop(root: Path, args) -> int:
        """Advance until the work item waits, escalates or reaches a terminal node.

        Bounded by ``--max-nodes`` — a runaway loop is the one failure mode a
        deterministic driver can still have, so it gets an explicit ceiling
        rather than trust.
        """
        if args.dry_run:
            report = _check(root, args.work_item)
            reached, ahead = _split_at_pointer(report["nodes"], report["currentNode"])
            print(
                f"{args.work_item}: at {report['currentNode']} (dry run — nothing written)"
            )
            print(_render_table(reached, ahead))
            return 0 if report["ok"] else 1

        terminal = {n["id"] for n in _show(root)["nodes"] if n.get("terminal")}
        seen: List[str] = []
        for _ in range(max(1, args.max_nodes)):
            result = _advance(root, args.work_item, ref=args.ref)
            print(f"  {result['node']}: {result['status']}")
            for message in result["messages"]:
                print(f"      · {message}")
            if result["status"] in ("wait", "block", "escalated"):
                print(
                    f"{args.work_item}: stopped at {result['node']} ({result['status']})"
                )
                return 0 if result["status"] == "wait" else 1
            if result["node"] in terminal:
                print(f"{args.work_item}: complete")
                return 0
            seen.append(result["node"])
            if seen.count(result["node"]) > 2:
                print(f"{args.work_item}: looping on {result['node']}; stopping")
                return 1
        print(f"{args.work_item}: hit --max-nodes ({args.max_nodes}); stopping")
        return 1
