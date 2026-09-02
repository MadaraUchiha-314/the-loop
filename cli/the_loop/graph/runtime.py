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
from .model import Graph, artifact_names, load_graph
from .refs import derive_ref
from .state import GraphState, StateLockBusy, state_lock, utc_now

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "CLEANUP_NODE",
    "NodeReport",
    "Runtime",
    "SkipResult",
    "StatusReport",
    "declare_skips",
    "force",
]

#: The node a work-item-level loop enters when the-loop releases its LOCAL
#: resources (issue-186). Named here rather than in the graph files' shape
#: because :meth:`Runtime.cleanup` is what enters it — the two work-item loops
#: declare it, ``pdlc-pr-loop`` deliberately does not, and a loop without it
#: simply has nothing to record.
CLEANUP_NODE = "cleanup"


def _exclude_spec_root(repo: Path, spec_root: str) -> str:
    """Keep the spec tree out of an **uninitialized** repository's history.

    A contribution can join a repository that never adopted the-loop (issue-185,
    PR #187 review). Its working checkout still needs the spec tree —
    ``graph-state.json``, ``execution-log.md``, ``contribution.md`` are how the
    runtime and its gates work at all — but none of that may reach the
    repository's history: the contribution PR carries only the intervention.
    Rather than trusting every session to remember not to ``git add`` it, the
    tree is excluded structurally, in ``info/exclude`` — git's checkout-local
    ignore file, itself never committed. Resolved via ``rev-parse --git-path``
    so a worktree checkout (the workspace default) lands on the shared file.

    Best-effort by contract: a non-git root or an unwritable exclude file
    degrades to a warning — the guarantee then rests on the session
    instructions, and starting the loop still must not fail.

    Returns ``"added"``, ``"present"`` or ``""`` (could not / nothing to do).
    """
    import subprocess

    entry = "/" + spec_root.strip("/") + "/"
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--git-path", "info/exclude"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("could not resolve %s's exclude file: %s", repo, exc)
        return ""
    if proc.returncode != 0:
        return ""  # not a git checkout — nothing to keep out of history
    path = Path(proc.stdout.strip())
    if not path.is_absolute():
        path = repo / path
    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        if entry in existing.splitlines():
            return "present"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            if existing and not existing.endswith("\n"):
                fh.write("\n")
            fh.write(entry + "\n")
    except OSError as exc:
        logger.warning("could not exclude %s from git: %s", spec_root, exc)
        return ""
    return "added"


#: The ``via`` marker of a skip nobody declared: an **opt-in** node that was
#: simply never selected (issue-188). Kept distinct from every human-declared
#: provenance because the two are different facts — one names a person who
#: removed a phase that would otherwise have run, the other names a phase that
#: was offered and not asked for.
NOT_SELECTED = "not-selected"


def _skip_provenance(decl: Mapping[str, Any]) -> str:
    """One line a reviewer can act on: who declared this skip, and how."""
    via = str(decl.get("via") or "unknown")
    if via == NOT_SELECTED:
        return (
            "not selected — an opt-in phase, off unless it is ticked at "
            "`phase-selection`"
        )
    token = str(decl.get("token") or "")
    by = str(decl.get("by") or "")
    reason = str(decl.get("reason") or "")
    parts = [f"skipped by declaration — via {via}"]
    if token:
        parts.append(f"token {token!r}")
    if by:
        parts.append(f"by {by}")
    if reason:
        parts.append(f"reason: {reason}")
    return ", ".join(parts)


def _degradations(outcome: ChainOutcome) -> List[Tuple[str, str]]:
    """``(hook, error)`` for every hook that **passed while recording a failure**.

    the-loop's outbound hooks are best-effort by contract: a GitHub outage must
    not wedge a work item, so `post-phase-selection`, `set-phase-label`,
    `request-review`, `publish-artifact`, `log-entry` and `notify` all catch,
    record ``data["error"]`` and return ``pass``. Nothing read that field
    (issue-194), so the only trace of a *deterministically* failing call — an
    unusable ref, a missing token — was a warning on a logger nothing
    configures, and the command printed a clean answer over a ticket that never
    received the question its gate was waiting on.

    Keyed on ``error`` rather than on ``posted=False``: an entry hook that finds
    its own marker and declines to post a second checklist returns
    ``posted=False, reason="already asked"``, and that is a correct no-op. Only
    a recorded error is a degradation.
    """
    return [
        (result.hook, str(result.data["error"]))
        for result in outcome.results
        if str(result.data.get("error") or "")
    ]


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
        state_subpath: str = "",
    ):
        self.repo = Path(repo)
        self.graph = graph or load_graph(repo=self.repo)
        self.spec_root = spec_root
        self.config = dict(config or {})
        # Where this runtime's graph-state lives, RELATIVE to the work item's
        # spec directory (issue-172). "" is the outer loop's state beside the
        # artifacts; an inner loop passes "pr-loops/pr-<n>" so each pull
        # request's pdlc-pr-loop keeps its own pointer while every artifact
        # gate still resolves against the work item's one spec chain.
        self.state_subpath = state_subpath

    # -- helpers --------------------------------------------------------------

    def spec_dir(self, work_item_id: str) -> Path:
        return self.repo / self.spec_root / work_item_id

    def state_dir(self, item: WorkItem) -> Path:
        """Where this runtime's graph state lives for ``item``.

        The artifacts and the state deliberately split here: hooks resolve
        against ``item.spec_dir`` (the shared spec chain), state against this.
        """
        if self.state_subpath:
            return item.spec_dir / self.state_subpath
        return item.spec_dir

    def work_item(self, work_item_id: str, ref: str = "") -> WorkItem:
        # Three tiers, in priority order (issue-194). An explicit `--ref` always
        # wins. Otherwise the ref is DERIVED from what this repository already
        # declares, because the bare id in the last tier is a value no
        # integration can use, and handing it to one is what made every outbound
        # hook a silent no-op. The bare id is kept as that last tier rather than
        # "": `WorkItem.ref` is also what the event log and the audit comments
        # call this work item, and they should print the id, not nothing.
        #
        # WHICH ref is derived depends on the loop. An **inner** loop (a
        # non-empty `state_subpath`) is about a PULL REQUEST, and its ref is
        # built by `build_runtime`, which is the only place that knows which one.
        # It deliberately does NOT fall through to the work item's ref: putting a
        # pull request's review comments on the ticket would be worse than the
        # silence this change removes.
        if ref:
            resolved = ref
        elif self.state_subpath:
            resolved = str(self.config.get("prRef") or "")
        else:
            resolved = derive_ref(
                work_item_id,
                str(self.config.get("originRepo") or ""),
                host=str(self.config.get("githubHost") or ""),
            )
        if not ref and resolved:
            logger.debug("derived ref %s for %s", resolved, work_item_id)
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
            ref=resolved or work_item_id,
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

    def _context(
        self,
        item: WorkItem,
        node,
        boundary: str,
        decisions: Optional[Mapping[str, Any]] = None,
        **extra,
    ) -> HookContext:
        return HookContext(
            work_item=item,
            node=node.as_mapping(),
            boundary=boundary,
            repo=self.repo,
            config=self.config,
            graph=self.graph,
            decisions=dict(decisions or {}),
            **extra,
        )

    def _note_degradations(
        self, report: NodeReport, item: WorkItem, node_id: str, outcome: ChainOutcome
    ) -> None:
        """Surface a best-effort hook that did not do its job (issue-194).

        Two readers, because the two callers of a graph verb see different
        things: the message lands on the report the CLI prints, and the event
        lands in the log the daemon's operator reads. Neither changes the
        chain's verdict — the status, the outcome and the edge are whatever they
        already were. Best-effort stays best-effort; it stops being silent.
        """
        for hook_name, error in _degradations(outcome):
            report.messages.append(f"warning: {hook_name} did not complete: {error}")
            eventlog.emit(
                "graph.hook_degraded",
                level="warning",
                work_item=item.ref,
                node=node_id,
                hook=hook_name,
                error=error,
            )

    def _surface(self, state: "GraphState") -> str:
        """This work item's collaboration surface, as frozen at selection.

        Read from the state rather than from any config (issue-183, owner's call
        on PR #184): where a work item is collaborated on is a property of that
        work item, chosen by its author at `phase-selection`, not a setting the
        repository or the operator's machine carries.
        """
        return str(getattr(state, "surface", "") or "")

    # -- declared skips (issue-177) --------------------------------------------

    def declared_skips(self, state: "GraphState") -> Dict[str, Dict[str, Any]]:
        """The declarations the runtime will honour — the ONE defensive read.

        ``state.skips`` is agent-writable, like everything in the state file,
        so every consumer goes through this filter: an entry is honoured only
        when the compiled graph marks that node skippable (and not required).
        A hand-written declaration on ``security-review`` is therefore inert
        everywhere at once, and :meth:`invalid_skips` surfaces it.

        **An unselected opt-in node is one of these too** (issue-188). Nobody
        declared it, so it carries ``via: not-selected`` rather than a person's
        name — but it is not walked, and expressing that here means routing,
        ``check``, ``--recompute`` and ``skipped_artifacts`` all learn it at
        once, through code that already exists. A work item whose state predates
        the node therefore skips it rather than blocking on a phase that did not
        exist when it started.
        """
        out: Dict[str, Dict[str, Any]] = {}
        for node_id, decl in (state.skips or {}).items():
            node = self.graph.nodes.get(node_id)
            if node is not None and node.skippable and not node.required:
                out[node_id] = dict(decl) if isinstance(decl, Mapping) else {}
        for node in self.graph.ordered():
            if node.opt_in and node.id not in out and not self.selected(state, node.id):
                out[node.id] = {"via": NOT_SELECTED}
        return out

    def selected(self, state: "GraphState", node_id: str) -> bool:
        """Did a human select this opt-in node (issue-188)?

        The mirror of :meth:`declared_skips`' filter, and defensive for the same
        reason: ``state.optIns`` is agent-writable, so an entry counts only when
        the compiled graph marks that node ``optIn``. A forged entry on any
        other node grants nothing — a node that is not opt-in was never skipped
        by default — which is why it needs no separate refusal report.
        """
        node = self.graph.nodes.get(node_id)
        if node is None or not node.opt_in:
            return False
        return isinstance((state.opt_ins or {}).get(node_id), Mapping)

    def invalid_skips(self, state: "GraphState") -> List[str]:
        """Declared node ids the graph refuses — surfaced, never honoured."""
        valid = self.declared_skips(state)
        return [n for n in (state.skips or {}) if n not in valid]

    def _skipped_artifact_names(self, skips: Mapping[str, Any]) -> frozenset:
        """Every artifact name authored by a declared-skipped node — what lets
        a later gate tell a planned absence from a missing deliverable."""
        names: set = set()
        for node_id in skips:
            node = self.graph.nodes.get(node_id)
            if node is None:
                continue
            for entry in node.produces:
                names.update(artifact_names(entry))
        return frozenset(names)

    def _record_selected_skips(
        self, state: "GraphState", item: WorkItem, outcome: ChainOutcome
    ) -> bool:
        """Record the skips a passing chain declared (issue-177).

        The `phase-selection` gate reads an authorized user's reply and returns
        the chosen skips as a **fact** in its result data; writing them is the
        runtime's job, because the runtime is the single writer holding the
        state. Applied only through :meth:`declared_skips`' vocabulary on every
        later read, so a hook cannot declare a skip the graph does not permit —
        and only for nodes still ahead of the pointer, so this can never excuse
        a node already walked.
        """
        # The decision itself is durable, separately from the skips it produced:
        # a selection that keeps every phase records nothing in `skips`, and
        # `the-loop check` (which passes no event) must still see the gate as
        # answered rather than re-asking forever.
        decided = False
        for result in outcome.results:
            marker = result.data.get("decision")
            if marker:
                record: Dict[str, Any] = {"at": utc_now()}
                frozen = result.data.get("frozenGraph")
                if frozen:
                    # The selection FREEZES the graph (issue-177, owner review):
                    # what the item will walk stops being a live comment anyone
                    # can keep editing and becomes a recorded fact — here, and
                    # in the portable session record through the sink below.
                    record["graph"] = frozen
                    record["via"] = str(result.data.get("selectionSource") or "")
                chosen = str(result.data.get("surface") or "")
                if chosen:
                    # Frozen by the same signed reply as the phase selection —
                    # one human act, one record (issue-183).
                    record["surface"] = chosen
                    state.surface = chosen
                per_pr = str(result.data.get("sessionPerPr") or "")
                if per_pr:
                    # How many sessions this work item's pull requests get
                    # (issue-260) — the third thing the one signed reply freezes.
                    # No `GraphState` field of its own, unlike `surface`: nothing
                    # here reads it back, and the reader that does is the daemon,
                    # through the frozen graph the sink below publishes.
                    record["sessionPerPr"] = per_pr
                goal = result.data.get("goal")
                if goal:
                    # The contribution loop's goal gate (issue-185): the goal
                    # and success criteria are frozen with provenance, exactly
                    # as a phase selection is — a recorded fact, not a live
                    # comment.
                    record["goal"] = dict(goal)
                brief = result.data.get("brief")
                if brief:
                    # The review loop's brief gate (issue-279): the reviewer's
                    # questions, angles and validations, frozen the same way —
                    # the contract every review round answers to.
                    record["brief"] = dict(brief)
                state.decisions.setdefault(str(marker), record)
                decided = True
                if frozen:
                    self._publish_frozen_graph(item, frozen)
        declared: Dict[str, Any] = {}
        chosen_in: Dict[str, Any] = {}
        for result in outcome.results:
            for node_id, decl in (result.data.get("declaredSkips") or {}).items():
                node = self.graph.nodes.get(str(node_id))
                rec = state.nodes.get(str(node_id))
                if node is None or not node.skippable or (rec and rec.entered_at):
                    continue
                declared[str(node_id)] = {**dict(decl), "at": utc_now()}
            # The same fact in the other direction (issue-188): an opt-in phase
            # somebody asked for. Same two guards — the compiled graph marks the
            # node, and the pointer has not already walked past it — because a
            # selection is as much a recorded human input as a skip is.
            for node_id, decl in (result.data.get("optIns") or {}).items():
                node = self.graph.nodes.get(str(node_id))
                rec = state.nodes.get(str(node_id))
                if node is None or not node.opt_in or (rec and rec.entered_at):
                    continue
                chosen_in[str(node_id)] = {**dict(decl), "at": utc_now()}
        if not declared and not chosen_in:
            return decided
        for node_id, decl in declared.items():
            state.skips.setdefault(node_id, decl)
        for node_id, decl in chosen_in.items():
            state.opt_ins.setdefault(node_id, decl)
        if declared:
            eventlog.emit(
                "graph.skips_declared",
                work_item=item.ref,
                via="selection",
                nodes=sorted(declared),
            )
            logger.info(
                "%s: phase selection declared skips %s", item.ref, sorted(declared)
            )
        if chosen_in:
            eventlog.emit(
                "graph.opt_ins_selected",
                work_item=item.ref,
                via="selection",
                nodes=sorted(chosen_in),
            )
            logger.info(
                "%s: phase selection selected opt-in phases %s",
                item.ref,
                sorted(chosen_in),
            )
        return True

    def _publish_frozen_graph(self, item: WorkItem, frozen: Mapping[str, Any]) -> None:
        """Push the frozen graph to the portable work-item record, if a sink exists.

        Same shape as the assignment channel (issue-172): the **daemon** injects
        a callable, because the registry is the daemon's and the runtime is
        repo-scoped. On the CLI path there is no sink and the frozen graph lives
        in `graph-state.json` alone, which is checked in and reviewable anyway.
        Best-effort: a failed publish never gates the selection.
        """
        sink = self.config.get("frozenGraphSink")
        if not callable(sink):
            return
        try:
            sink(dict(frozen))
        except Exception as exc:  # noqa: BLE001 — never gate on the sink
            logger.warning("could not publish the frozen graph: %s", exc)
            eventlog.emit(
                "graph.frozen_publish_failed",
                level="warning",
                work_item=item.ref,
                error=str(exc),
            )
            return
        eventlog.emit("graph.frozen", work_item=item.ref)

    def _route_skips(
        self,
        state: "GraphState",
        item: WorkItem,
        node_id: str,
        skips: Mapping[str, Any],
    ) -> str:
        """Walk declared-skipped nodes along their ``on: skipped`` edges.

        Each skipped node gets outcome ``skipped`` on its record — a
        declaration honoured, not a verdict forged — and NONE of its entry or
        exit hooks run: no phase label, no log checkpoint, no assignment
        (R3.1, R3.5). Returns the first non-skipped node. Compile-time
        validation guarantees every skippable node has its edge; the visited
        guard makes a cyclic authoring mistake land fail-closed on the node
        itself rather than loop.
        """
        visited: set = set()
        while node_id in skips and node_id not in visited:
            visited.add(node_id)
            target = self.graph.next_node(node_id, "skipped")
            if target is None:
                break  # fail closed: walk the node rather than guess an exit
            rec = state.record(node_id)
            rec.entered_at = rec.entered_at or utc_now()
            rec.outcome = "skipped"
            rec.exited_at = utc_now()
            eventlog.emit(
                "graph.node_skipped",
                work_item=item.ref,
                node=node_id,
                **{k: v for k, v in (skips.get(node_id) or {}).items() if v},
            )
            logger.info(
                "%s skipped %s (%s)",
                item.ref,
                node_id,
                _skip_provenance(skips.get(node_id) or {}),
            )
            node_id = target
        return node_id

    # -- evaluation (pure: no network, no subprocess, no mutation) -------------

    def evaluate(
        self,
        node_id: str,
        item: WorkItem,
        event: Optional[Mapping[str, Any]] = None,
        skips: Optional[Mapping[str, Any]] = None,
        decisions: Optional[Mapping[str, Any]] = None,
        surface: str = "",
    ) -> ChainOutcome:
        """Run one node's **exit** chain. This is what ``check`` calls.

        ``check`` passes no ``event`` — it reports what the artifacts alone say,
        which is what keeps it honest — so a gate awaiting human feedback reads
        as ``wait`` there and only resolves when a real event carries the reply.

        ``skips`` is the validated declared-skip set (issue-177): the chain
        needs it only to tell a *planned* absence (an artifact whose authoring
        node was declared-skipped) from a missing deliverable.
        """
        node = self.graph.node(node_id)
        return run_chain(
            node.exit,
            self._context(
                item,
                node,
                "exit",
                event=event,
                skipped_artifacts=self._skipped_artifact_names(skips or {}),
                decisions=decisions,
                surface=surface,
            ),
        )

    def status(self, work_item_id: str, recompute: bool = False) -> StatusReport:
        """Every node's verdict, in declaration order.

        ``recompute`` ignores graph state entirely and derives completion from
        the artifacts alone (R8.4) — this is what CI uses, and it is why a
        tampered or optimistic state file cannot survive review.
        """
        item = self.work_item(work_item_id)
        state = GraphState.load(self.state_dir(item), work_item_id)
        # Declared skips are honoured in BOTH modes (issue-177): a declaration
        # is a recorded human input with an off-repo audit trail, not the state
        # file scoring itself — while an invalid declaration is honoured in
        # NEITHER, and called out on the node it tried to touch.
        skips = self.declared_skips(state)
        refused = set(self.invalid_skips(state))
        reports: List[NodeReport] = []
        for node in self.graph.ordered():
            rec = state.nodes.get(node.id)
            if node.id in skips:
                reports.append(
                    NodeReport(
                        node=node.id,
                        status=SKIP,
                        outcome="skipped",
                        messages=[_skip_provenance(skips[node.id])],
                        attempts=rec.attempts if rec else 0,
                    )
                )
                continue
            outcome = self.evaluate(
                node.id,
                item,
                skips=skips,
                decisions=state.decisions,
                surface=self._surface(state),
            )
            messages = [m.render() for m in outcome.messages]
            if node.id in refused:
                messages.append(
                    "graph state declares a skip on this node, which is not "
                    "skippable — the declaration is refused and has no effect"
                )
            reports.append(
                NodeReport(
                    node=node.id,
                    status=outcome.status,
                    outcome=outcome.outcome,
                    messages=messages,
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

    def start(self, work_item_id: str, ref: str = "") -> Optional[NodeReport]:
        """Enter the start node for a work item that has not begun (issue-113).

        The counterpart ``advance`` never was: ``advance`` evaluates the *current*
        node's exit chain, so on a work item nobody entered it silently reads the
        start node as current and gates it. Nothing ever *entered* that node, which
        is why the entry chain — the phase label, the log checkpoint — never ran on
        the automated path.

        Deliberately a separate method rather than a branch inside ``advance``:
        "begin" and "evaluate a gate" are different questions, and folding them
        together would make a work item's first ``advance`` run an entry chain as a
        side effect — the kind of implicit step issue-109 exists to remove.

        Idempotent: a work item that already has a pointer returns ``None`` and is
        left untouched, so a redelivered spawn can never rewind it.
        """
        item = self.work_item(work_item_id, ref)
        state = GraphState.load(self.state_dir(item), work_item_id)
        if state.current_node:
            return None

        # A repository that never adopted the-loop must not have the spec tree
        # committed into it (issue-185, PR #187 review): exclude it from git
        # BEFORE the first state write creates it. `is False` on purpose — only
        # a bootstrap that positively established "uninitialized" triggers this;
        # a hand-built runtime config without the key changes nothing.
        if self.config.get("repoInitialized") is False:
            outcome = _exclude_spec_root(self.repo, self.spec_root)
            if outcome == "added":
                eventlog.emit(
                    "graph.spec_tree_excluded",
                    work_item=ref or work_item_id,
                    path=self.spec_root,
                )
                logger.info(
                    "%s: %s excluded from git — this repository has not adopted "
                    "the-loop, so its spec tree stays out of history",
                    ref or work_item_id,
                    self.spec_root,
                )

        node_id = self._route_skips(
            state, item, self.graph.start, self.declared_skips(state)
        )
        state.enter(node_id)
        # Which loop this state walks (issue-185): recorded once, at the only
        # moment the choice is made, so every later reader — the daemon, `the-loop
        # check`, the graph verbs — resolves the same graph without re-deriving
        # it from a control record that may live on another machine.
        state.loop = self.graph.name or state.loop
        state.save(
            self.state_dir(item)
        )  # persist BEFORE any dependent side effect (R8.2)
        node = self.graph.node(node_id)
        entered = run_chain(
            node.entry, self._context(item, node, "entry", surface=self._surface(state))
        )
        eventlog.emit("graph.started", work_item=item.ref, node=node_id)
        logger.info("%s entered the graph at %s", item.ref, node_id)
        report = NodeReport(
            node=node_id,
            status=PASS,
            outcome=PASS,
            attempts=state.record(node_id).attempts,
        )
        self._note_degradations(report, item, node_id, entered)
        return report

    def cleanup(
        self, work_item_id: str, ref: str = "", reason: str = ""
    ) -> Optional[NodeReport]:
        """Enter the ``cleanup`` node — the work item's local resources are going.

        A sibling of :meth:`start`, not of :func:`force`, and the distinction is
        the whole reason this exists. A force is an operator **bypassing a gate**:
        it warns, records the transition as forced, and posts an override
        announcement on the ticket. Cleanup bypasses nothing — the-loop is
        recording that it released the tmux sessions, the checkout and the local
        record — so it enters the node the same way ``start`` enters the first
        one: persist the pointer, then run the entry chain (issue-186, R5.2).

        Entering from **anywhere** is legitimate and honest. The ordinary path is
        from ``complete``; a work item closed as `wontfix` mid-flight is entered
        from wherever it stood, its earlier records untouched, so
        ``check --recompute`` still reports every gate that never ran.

        Returns ``None`` — a recorded no-op — in the three cases where there is
        nothing to record: the loop declares no ``cleanup`` node (``pdlc-pr-loop``),
        the work item never entered the graph, or the pointer is already there.
        """
        node = self.graph.nodes.get(CLEANUP_NODE)
        if node is None:
            logger.debug(
                "%s walks a loop with no %s node; nothing to record",
                work_item_id,
                CLEANUP_NODE,
            )
            return None
        item = self.work_item(work_item_id, ref)
        state = GraphState.load(self.state_dir(item), work_item_id)
        if not state.current_node:
            return None  # never entered the graph: there is no walk to end
        if state.current_node == CLEANUP_NODE:
            return None  # idempotent: a second cleanup re-runs no entry chain
        from_node = state.current_node
        state.enter(CLEANUP_NODE)
        state.save(self.state_dir(item))  # persist BEFORE any side effect (R8.2)
        entered = run_chain(
            node.entry,
            self._context(item, node, "entry", surface=self._surface(state)),
        )
        eventlog.emit(
            "graph.cleaned",
            work_item=item.ref,
            **{"from": from_node},
            reason=reason or None,
        )
        logger.info(
            "%s entered %s from %s — its local resources are being released",
            item.ref,
            CLEANUP_NODE,
            from_node,
        )
        report = NodeReport(
            node=CLEANUP_NODE,
            status=PASS,
            outcome=PASS,
            attempts=state.record(CLEANUP_NODE).attempts,
        )
        self._note_degradations(report, item, CLEANUP_NODE, entered)
        return report

    def complete(
        self,
        work_item_id: str,
        ref: str = "",
        node: str = "",
        actor: str = "",
    ) -> Dict[str, Any]:
        """A completion **claim**: the session says a node's work is done (issue-148).

        The claim carries no verdict and no event text — it is a prompt to run
        the current node's exit chain, nothing more (R1.2). The chain reads
        checked-in artifacts; a claim for work that is not actually done blocks
        on exactly what it would block on anyway.

        Claims name the node they are about (R1.4/R1.5): a replayed claim for a
        node the pointer has already left is a recorded no-op, and a claim for a
        node that is neither current nor past is refused naming the current one.
        The whole load→evaluate→save window runs under the graph-state lock —
        this verb is the second writer beside the daemon's GraphLink.
        """
        item = self.work_item(work_item_id, ref)
        try:
            with state_lock(self.state_dir(item)):
                return self._complete_locked(item, work_item_id, ref, node, actor)
        except StateLockBusy:
            return {
                "node": node or "",
                "status": "busy",
                "outcome": "",
                "moved": False,
                "currentNode": "",
                "messages": ["another the-loop process holds the graph-state lock"],
                "reason": "busy",
            }

    def _complete_locked(
        self, item: WorkItem, work_item_id: str, ref: str, node: str, actor: str
    ) -> Dict[str, Any]:
        state = GraphState.load(self.state_dir(item), work_item_id)
        if not state.current_node:
            return {
                "node": node or "",
                "status": "refused",
                "outcome": "",
                "moved": False,
                "currentNode": "",
                "messages": [
                    "this work item has not entered the graph; nothing to complete"
                ],
                "reason": "not-started",
            }
        current = state.current_node
        claimed = node or current
        order = [n.id for n in self.graph.ordered()]
        if claimed != current:
            past = (
                claimed in order
                and current in order
                and order.index(claimed) < order.index(current)
            )
            reason = "already-past" if past else "not-current"
            return {
                "node": claimed,
                "status": "noop" if past else "refused",
                "outcome": "",
                "moved": False,
                "currentNode": current,
                "messages": [
                    f"the current node is {current!r}"
                    + (" and the claimed node is behind it" if past else "")
                ],
                "reason": reason,
            }
        state.completions[claimed] = {"at": utc_now(), "by": actor or "cli"}
        state.save(self.state_dir(item))
        report = self.advance(work_item_id, ref=ref)
        after = GraphState.load(self.state_dir(item), work_item_id).current_node
        return {
            "node": claimed,
            "status": report.status,
            "outcome": report.outcome,
            "moved": after != current,
            "currentNode": after,
            "messages": report.messages,
            "reason": "",
        }

    def advance(
        self,
        work_item_id: str,
        ref: str = "",
        event: Optional[Mapping[str, Any]] = None,
    ) -> NodeReport:
        """Evaluate the current node's exit chain and take the matching edge.

        ``event`` is the inbound event that prompted this advance, passed to the
        chain as :attr:`HookContext.event` (issue-113). It is what lets a
        human-gate hook such as ``classify-feedback`` see the comments that just
        arrived; without it the gate has nothing to classify and waits forever.
        """
        item = self.work_item(work_item_id, ref)
        state = GraphState.load(self.state_dir(item), work_item_id)
        skips = self.declared_skips(state)
        if state.current_node:
            node_id = state.current_node
        else:
            # The CLI-only path never calls start(), so routing past already
            # declared skips lands here too — otherwise a fresh item would gate
            # the very node its author declared away (issue-177).
            node_id = self._route_skips(state, item, self.graph.start, skips)
        node = self.graph.node(node_id)

        outcome = self.evaluate(
            node_id,
            item,
            event=event,
            skips=skips,
            decisions=state.decisions,
            surface=self._surface(state),
        )
        report = NodeReport(
            node=node_id,
            status=outcome.status,
            outcome=outcome.outcome,
            messages=[m.render() for m in outcome.messages],
            attempts=state.record(node_id).attempts,
        )
        # An exit hook can degrade too — `classify-phase-selection` posts the
        # confirmation comment — and it does so on the wait and block paths as
        # much as on the passing one, so this is read before any of them return.
        self._note_degradations(report, item, node_id, outcome)

        if outcome.status == WAIT:
            state.park(node_id, outcome.render() or "awaiting a human")
            state.save(self.state_dir(item))
            eventlog.emit("graph.parked", work_item=item.ref, node=node_id)
            return report

        if outcome.status == BLOCK:
            rendered = outcome.render()
            repeated = state.note_block(node_id, rendered)
            rec = state.record(node_id)
            state.save(self.state_dir(item))
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

        # satisfied — record any skips this chain declared, then take the edge.
        # Order matters: the selection gate's own result decides which nodes the
        # very next hop routes around.
        if self._record_selected_skips(state, item, outcome):
            skips = self.declared_skips(state)
        state.exit(node_id, outcome.outcome)
        target = self.graph.next_node(node_id, outcome.outcome)
        if target is not None:
            # A declared-skipped successor is walked around, not entered
            # (issue-177) — its record says `skipped`, its hooks never run.
            target = self._route_skips(state, item, target, skips)
        if target is None:
            if node.terminal:
                state.current_node = node_id
                state.save(self.state_dir(item))
                eventlog.emit("graph.completed", work_item=item.ref, node=node_id)
                return report
            state.park(
                node_id, f"no declared edge from {node_id} on {outcome.outcome!r}"
            )
            state.save(self.state_dir(item))
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
        state.save(
            self.state_dir(item)
        )  # persist BEFORE any dependent side effect (R8.2)
        entry_node = self.graph.node(target)
        if entry_node.actor == "human":
            # `session: inherit` honoured for real (issue-148, R5): decide which
            # session this gate runs in, and record how it was arrived at. The
            # registry stays the dispatch authority — this is the graph's own
            # binding, consulted and logged, not a routing override.
            binding, how = self.resolve_session(entry_node, state)
            eventlog.emit(
                "graph.gate_session",
                work_item=item.ref,
                node=target,
                resolution=how,
                session=(binding or {}).get("id") or None,
            )
        entered = run_chain(
            entry_node.entry,
            self._context(item, entry_node, "entry", surface=self._surface(state)),
        )
        eventlog.emit(
            "graph.advanced",
            work_item=item.ref,
            node=node_id,
            to=target,
            outcome=outcome.outcome,
        )
        report.messages.append(f"advanced to {target}")
        # The entry chain of the node just ENTERED — attributed to that node,
        # not to the one this advance left. This is where the phase-selection
        # checklist and the phase label are posted, and where issue-194's silence
        # was loudest: the work item parked on a question nobody was asked.
        self._note_degradations(report, item, target, entered)
        return report


def _announce_force(runtime: "Runtime", item: WorkItem, record: Dict[str, Any]) -> str:
    """Post the force to the ticket — the audit record a human actually reads.

    Best-effort: an integration outage must not prevent the operator unblocking
    their work item. The other three records (graph state, execution log, event
    log) are already durable, so a failure here degrades the trail rather than
    losing it.

    Returns the error when the comment did not go up, ``""`` otherwise — the
    caller reports it as a warning (issue-194). "Best-effort" was never meant to
    mean "the operator is told the audit trail exists when it does not".
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
        return str(exc)
    return ""


# -- declared skips: the operator channel (issue-177) --------------------------


@dataclass
class SkipResult:
    work_item: str
    declared: List[str] = field(default_factory=list)
    rejected: List[Dict[str, str]] = field(default_factory=list)
    reason: str = ""
    #: Best-effort steps that did not happen — today, only the audit comment
    #: (issue-194). A declaration whose paper trail never reached the ticket is
    #: still a declaration, but the operator has to know to post it themselves.
    warnings: List[str] = field(default_factory=list)


def _announce_skips(
    runtime: "Runtime", item: WorkItem, declared: List[str], record: Dict[str, Any]
) -> str:
    """Post the declaration to the ticket — the audit record a human reads.

    Best-effort, like the force announcement: an integration outage must not
    prevent the operator declaring their skips; the state record and the event
    log are already durable. Returns the error when the comment did not go up,
    ``""`` otherwise (issue-194).
    """
    from ..authz import mark_self_authored
    from .integrations import IntegrationError, resolve

    body = mark_self_authored(
        "🤖 _the-loop_ — **declared skips**\n\n"
        f"{', '.join(f'`{n}`' for n in declared)} declared skipped by "
        f"{record['by']}\n\n"
        f"**Reason:** {record['reason']}\n\n"
        "These are declarations, not verdicts: `the-loop check` reports each "
        "node as *skipped by declaration*, the never-skippable gates still "
        "run, and the pointer routes around the named nodes when it reaches "
        "them."
    )
    try:
        resolve("github", runtime.config).call("add-comment", ref=item.ref, body=body)
    except (IntegrationError, Exception) as exc:  # noqa: BLE001
        logger.warning("could not post the skip audit comment: %s", exc)
        return str(exc)
    return ""


def declare_skips(
    runtime: Runtime,
    work_item_id: str,
    tokens: List[str],
    reason: str,
    actor: str = "",
    ref: str = "",
) -> SkipResult:
    """Declare skips for a work item — the operator channel (issue-177, R2.3).

    The sibling of :func:`force`, with the same posture: human-attributed, a
    reason required, an audit comment posted, and **never a forged verdict** —
    a declaration makes the runtime route around a node and report it as
    *skipped by declaration*, it does not mark any gate satisfied.

    Bounded twice: a token must resolve inside the graph's skip vocabulary
    (skippable nodes and shipped skip sets — protected gates are simply not in
    it), and it must land ahead of the pointer — a node already entered or
    passed is refused, because a skip is a plan, not an amnesty (R2.6).
    """
    if not reason or not reason.strip():
        raise ValueError(
            "--reason is required: an unexplained skip is refused. Record why "
            "this work item does not walk the phase."
        )
    if not tokens:
        raise ValueError("name at least one node or skip set to declare")

    item = runtime.work_item(work_item_id, ref)
    state = GraphState.load(runtime.state_dir(item), work_item_id)

    accepted, bad_tokens = runtime.graph.expand_skip_tokens(tokens)
    rejected: List[Dict[str, str]] = [
        {"token": token, "why": "not a skippable node or shipped skip set"}
        for token in bad_tokens
    ]

    order = [n.id for n in runtime.graph.ordered()]
    current = state.current_node
    declared: List[str] = []
    at = utc_now()
    by = actor or "(shell)"
    for node_id, token in accepted.items():
        rec = state.nodes.get(node_id)
        entered = bool(rec and rec.entered_at)
        behind = bool(
            current
            and node_id in order
            and current in order
            and order.index(node_id) < order.index(current)
        )
        if node_id == current or entered or behind:
            rejected.append(
                {
                    "token": node_id,
                    "why": "already entered or behind the pointer — a skip is "
                    "a plan, not an amnesty",
                }
            )
            continue
        state.skips.setdefault(
            node_id,
            {
                "via": "cli",
                "token": token,
                "by": by,
                "reason": reason.strip(),
                "at": at,
            },
        )
        declared.append(node_id)

    warnings: List[str] = []
    if declared:
        state.save(runtime.state_dir(item))
        eventlog.emit(
            "graph.skips_declared",
            work_item=item.ref,
            via="cli",
            actor=by,
            reason=reason.strip(),
            nodes=list(declared),
        )
        logger.info("%s: declared skips %s (%s)", item.ref, declared, reason.strip())
        failed = _announce_skips(
            runtime, item, declared, {"by": by, "reason": reason.strip()}
        )
        if failed:
            warnings.append(f"could not post the audit comment: {failed}")
    for entry in rejected:
        eventlog.emit(
            "graph.skips_rejected",
            level="warning",
            work_item=item.ref,
            token=entry["token"],
            via="cli",
            why=entry["why"],
        )
    return SkipResult(
        work_item=item.ref,
        declared=declared,
        rejected=rejected,
        reason=reason.strip(),
        warnings=warnings,
    )


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
    state = GraphState.load(runtime.state_dir(item), work_item_id)
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
    state.save(runtime.state_dir(item))

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
    failed = _announce_force(runtime, item, record)
    if failed:
        # Deliberately not in `record["warnings"]`: that list is the audit record
        # of what this force BYPASSED, written to graph state before the comment
        # was attempted. This is a warning about the reporting, and it belongs
        # only to the result the operator is reading right now.
        warnings = warnings + [f"could not post the audit comment: {failed}"]
    return ForceResult(
        work_item=item.ref,
        from_node=from_node,
        to_node=to_node,
        reason=record["reason"],
        warnings=warnings,
    )
