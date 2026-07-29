"""The runtime: enter a node, run its chain, take an edge. A state machine.

No workflow engine, no scheduler, no task queue, no database, no async (R6b.3).
One work item advances at a time, which costs nothing because the dispatcher
already serialises per session.

``the-loop run``, the daemon and ``the-loop check`` all call the **same**
chain-execution code — which is what keeps ``check`` honest: CI runs the
runtime, not a reimplementation of it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .. import eventlog
from .chain import ChainOutcome, run_chain
from .contract import BLOCK, PASS, SKIP, WAIT, HookContext, WorkItem
from .model import Graph, load_graph
from .state import GraphState, utc_now

logger = logging.getLogger("the-loop.graph")

__all__ = ["NodeReport", "Runtime", "StatusReport", "force"]


@dataclass
class NodeReport:
    """One node's verdict, as ``the-loop check`` reports it."""

    node: str
    status: str
    outcome: str
    messages: List[str] = field(default_factory=list)
    forced: bool = False
    attempts: int = 0

    @property
    def satisfied(self) -> bool:
        return self.status in (PASS, SKIP)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "node": self.node,
            "status": self.status,
            "outcome": self.outcome,
            "messages": self.messages,
            "forced": self.forced,
            "attempts": self.attempts,
        }


@dataclass
class StatusReport:
    work_item: str
    current_node: str
    nodes: List[NodeReport] = field(default_factory=list)
    parked: Optional[Dict[str, Any]] = None

    @property
    def ok(self) -> bool:
        """True when nothing up to and including the current node is unmet."""
        for report in self.nodes:
            if not report.satisfied:
                return False
            if report.node == self.current_node:
                break
        return True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "workItem": self.work_item,
            "currentNode": self.current_node,
            "ok": self.ok,
            "parked": self.parked,
            "nodes": [n.as_dict() for n in self.nodes],
        }


class Runtime:
    """Walks one repository's work items through the graph."""

    def __init__(
        self,
        repo: Path,
        graph: Optional[Graph] = None,
        spec_root: str = "docs/specs",
        config: Optional[Mapping[str, Any]] = None,
    ):
        self.repo = Path(repo)
        self.graph = graph or load_graph(repo=self.repo)
        self.spec_root = spec_root
        self.config = dict(config or {})

    # -- helpers --------------------------------------------------------------

    def spec_dir(self, work_item_id: str) -> Path:
        return self.repo / self.spec_root / work_item_id

    def work_item(self, work_item_id: str, ref: str = "") -> WorkItem:
        spec_dir = self.spec_dir(work_item_id)
        tags: List[str] = []
        tier = 3
        for name in ("requirements.md", "bugfix.md", "design.md"):
            candidate = spec_dir / name
            if candidate.is_file():
                from .frontmatter import read_front_matter

                front = read_front_matter(candidate)
                raw_tags = front.get("tags") or []
                if isinstance(raw_tags, list):
                    tags = [str(t) for t in raw_tags]
                try:
                    tier = int(front.get("riskTier", tier))
                except (TypeError, ValueError):
                    pass
                break
        return WorkItem(
            ref=ref or work_item_id,
            id=work_item_id,
            spec_dir=spec_dir,
            tags=tuple(tags),
            risk_tier=tier,
        )

    def resolve_session(
        self, node, state: "GraphState"
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        """The session a node runs in, and how it was arrived at (R7.3, R7.4).

        ``session: inherit`` reuses the session that produced the artifacts under
        review, so a reviewer's "this section is thin" reaches the agent that
        wrote it with its context intact. If that session has died the fallback
        is a **fresh** one seeded with the work item's artifacts — never a block:
        requirements.md, design.md and the execution log are enough to restart.
        """
        if node.session != "inherit":
            return None, "new"
        bound = state.session
        if bound and bound.get("alive", True):
            return dict(bound), "inherited"
        return (
            {
                "seed_artifacts": [
                    "requirements.md",
                    "design.md",
                    "execution-log.md",
                ]
            },
            "fresh-with-artifacts",
        )

    def _context(self, item: WorkItem, node, boundary: str, **extra) -> HookContext:
        return HookContext(
            work_item=item,
            node=node.as_mapping(),
            boundary=boundary,
            repo=self.repo,
            config=self.config,
            **extra,
        )

    # -- evaluation (pure: no network, no subprocess, no mutation) -------------

    def evaluate(self, node_id: str, item: WorkItem) -> ChainOutcome:
        """Run one node's **exit** chain. This is what ``check`` calls."""
        node = self.graph.node(node_id)
        return run_chain(node.exit, self._context(item, node, "exit"))

    def status(self, work_item_id: str, recompute: bool = False) -> StatusReport:
        """Every node's verdict, in declaration order.

        ``recompute`` ignores graph state entirely and derives completion from
        the artifacts alone (R8.4) — this is what CI uses, and it is why a
        tampered or optimistic state file cannot survive review.
        """
        item = self.work_item(work_item_id)
        state = GraphState.load(item.spec_dir, work_item_id)
        reports: List[NodeReport] = []
        for node in self.graph.ordered():
            outcome = self.evaluate(node.id, item)
            rec = state.nodes.get(node.id)
            reports.append(
                NodeReport(
                    node=node.id,
                    status=outcome.status,
                    outcome=outcome.outcome,
                    messages=[m.render() for m in outcome.messages],
                    forced=bool(rec and rec.forced) and not recompute,
                    attempts=rec.attempts if rec else 0,
                )
            )
        current = state.current_node or self.graph.start
        if recompute:
            current = self._first_unmet(reports) or current
        return StatusReport(
            work_item=work_item_id,
            current_node=current,
            nodes=reports,
            parked=None if recompute else state.parked,
        )

    @staticmethod
    def _first_unmet(reports: List[NodeReport]) -> str:
        for report in reports:
            if not report.satisfied:
                return report.node
        return reports[-1].node if reports else ""

    def reconstruct(self, work_item_id: str) -> str:
        """Derive the current node from the artifacts — the ground truth (R8.3)."""
        return self.status(work_item_id, recompute=True).current_node

    # -- advancement ----------------------------------------------------------

    def advance(self, work_item_id: str, ref: str = "") -> NodeReport:
        """Evaluate the current node's exit chain and take the matching edge."""
        item = self.work_item(work_item_id, ref)
        state = GraphState.load(item.spec_dir, work_item_id)
        node_id = state.current_node or self.graph.start
        node = self.graph.node(node_id)

        outcome = self.evaluate(node_id, item)
        report = NodeReport(
            node=node_id,
            status=outcome.status,
            outcome=outcome.outcome,
            messages=[m.render() for m in outcome.messages],
            attempts=state.record(node_id).attempts,
        )

        if outcome.status == WAIT:
            state.park(node_id, outcome.render() or "awaiting a human")
            state.save(item.spec_dir)
            eventlog.emit("graph.parked", work_item=item.ref, node=node_id)
            return report

        if outcome.status == BLOCK:
            rendered = outcome.render()
            repeated = state.note_block(node_id, rendered)
            rec = state.record(node_id)
            state.save(item.spec_dir)
            if repeated or rec.attempts >= node.max_attempts:
                eventlog.emit(
                    "graph.escalated",
                    level="warning",
                    work_item=item.ref,
                    node=node_id,
                    attempts=rec.attempts,
                    repeated=repeated,
                )
                report.status = "escalated"
            else:
                eventlog.emit(
                    "graph.blocked",
                    work_item=item.ref,
                    node=node_id,
                    hook=outcome.blocking.hook if outcome.blocking else "",
                )
            return report

        # satisfied — take the edge
        state.exit(node_id, outcome.outcome)
        target = self.graph.next_node(node_id, outcome.outcome)
        if target is None:
            if node.terminal:
                state.current_node = node_id
                state.save(item.spec_dir)
                eventlog.emit("graph.completed", work_item=item.ref, node=node_id)
                return report
            state.park(
                node_id, f"no declared edge from {node_id} on {outcome.outcome!r}"
            )
            state.save(item.spec_dir)
            eventlog.emit(
                "graph.no_edge",
                level="warning",
                work_item=item.ref,
                node=node_id,
                outcome=outcome.outcome,
            )
            report.status = "escalated"
            report.messages.append(
                f"no declared edge from {node_id} on outcome {outcome.outcome!r}"
            )
            return report

        state.enter(target)
        state.save(item.spec_dir)  # persist BEFORE any dependent side effect (R8.2)
        entry_node = self.graph.node(target)
        run_chain(entry_node.entry, self._context(item, entry_node, "entry"))
        eventlog.emit(
            "graph.advanced",
            work_item=item.ref,
            node=node_id,
            to=target,
            outcome=outcome.outcome,
        )
        report.messages.append(f"advanced to {target}")
        return report


def _announce_force(runtime: "Runtime", item: WorkItem, record: Dict[str, Any]) -> None:
    """Post the force to the ticket — the audit record a human actually reads.

    Best-effort: an integration outage must not prevent the operator unblocking
    their work item. The other three records (graph state, execution log, event
    log) are already durable, so a failure here degrades the trail rather than
    losing it.
    """
    from ..authz import mark_self_authored
    from .integrations import IntegrationError, resolve

    warnings = "".join(f"\n- ⚠️ {w}" for w in record.get("warnings") or [])
    body = mark_self_authored(
        "🤖 _the-loop_ — **forced transition**\n\n"
        f"`{record['from']}` → `{record['to']}` by {record['actor']}\n\n"
        f"**Reason:** {record['reason']}{warnings}\n\n"
        "This moved the pointer only. The bypassed gate keeps its real verdict, "
        "so `the-loop check --recompute` will still report it as unmet."
    )
    try:
        resolve("github", runtime.config).call("add-comment", ref=item.ref, body=body)
    except (IntegrationError, Exception) as exc:  # noqa: BLE001
        logger.warning("could not post the force audit comment: %s", exc)


# -- the escape hatch ---------------------------------------------------------


@dataclass
class ForceResult:
    work_item: str
    from_node: str
    to_node: str
    reason: str
    warnings: List[str] = field(default_factory=list)


def force(
    runtime: Runtime,
    work_item_id: str,
    to_node: str,
    reason: str,
    actor: str = "",
    ref: str = "",
) -> ForceResult:
    """Move a work item to ``to_node`` regardless of gates (issue-109, R10).

    **A force moves the pointer. It never forges a verdict.** The transition is
    recorded as ``forced`` and the bypassed node's gate keeps whatever it
    actually evaluated to — so ``check --recompute`` still reports it unmet, and
    CI, the diff and any reviewer see a forced transition for exactly what it
    is. The operator gets unblocked; nobody gets misled.

    An override that also marked the gate satisfied would be a verdict-forging
    tool, and every guarantee in the design would then be worth only as much as
    the operator's discipline.
    """
    if not reason or not reason.strip():
        raise ValueError(
            "--reason is required: an unexplained override is refused. Record why "
            "you are bypassing the gate."
        )
    target = runtime.graph.node(to_node)  # raises GraphConfigError, listing valid ids

    item = runtime.work_item(work_item_id, ref)
    state = GraphState.load(item.spec_dir, work_item_id)
    from_node = state.current_node or runtime.graph.start

    warnings: List[str] = []
    if runtime.graph.next_node(from_node, PASS) != to_node and not any(
        e.target == to_node for e in runtime.graph.edges_from(from_node)
    ):
        warnings.append(
            f"{from_node} → {to_node} is not a declared edge; you are deliberately "
            "outside the model"
        )
    if target.required or runtime.graph.node(from_node).required:
        bypassed = from_node if runtime.graph.node(from_node).required else to_node
        warnings.append(
            f"node {bypassed!r} is marked required — this force bypasses a "
            "guarantee the process treats as mandatory"
        )

    record = {
        "from": from_node,
        "to": to_node,
        "reason": reason.strip(),
        "actor": actor or "(shell)",
        "at": utc_now(),
        "warnings": list(warnings),
    }
    state.forced.append(record)
    # Mark the destination forced — NOT the bypassed gate satisfied.
    state.enter(to_node)
    state.record(to_node).forced = True
    state.save(item.spec_dir)

    eventlog.emit(
        "graph.forced",
        level="warning",
        work_item=item.ref,
        **{"from": from_node},
        to=to_node,
        actor=record["actor"],
        reason=record["reason"],
    )
    logger.warning(
        "FORCED %s: %s → %s (%s)%s",
        item.ref,
        from_node,
        to_node,
        record["reason"],
        "".join(f"\n  warning: {w}" for w in warnings),
    )
    _announce_force(runtime, item, record)
    return ForceResult(
        work_item=item.ref,
        from_node=from_node,
        to_node=to_node,
        reason=record["reason"],
        warnings=warnings,
    )
