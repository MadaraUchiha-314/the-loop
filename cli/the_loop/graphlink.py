"""The seam between the ingress and the process graph (issue-113).

Before this module, the two halves of the-loop's automation never met. The
ingress (webhook receiver, poller) discovered work items and spawned harness
sessions; the process graph (issue-109) modelled the PDLC and knew how to walk
it — and ``graph/runtime.py`` had exactly one importer in the tree, the CLI
command. So on the automated path **no node was ever entered**: no entry chain
ran, the ``loop:<phase>`` labels stayed unpopulated, and ``HookContext.event``
— read by ``classify-feedback``, written by nobody — left every human gate
waiting for feedback it could not be given.

This module is the missing call. Two entry points, both invoked by the
**dispatcher** (which both ingresses share, so wiring it here means a webhook
deployment and a polling one behave identically):

* :meth:`GraphLink.on_spawn` — a session just started for a work item, so the
  work item enters the graph (and, when the node it enters is a human gate, that
  gate is evaluated once against the spawning event — issue-199);
* :meth:`GraphLink.on_event` — an event reached an existing session, so the
  graph takes at most one node boundary, with the event's comments attached.

**Everything here is best-effort.** Both entry points return ``None`` and never
raise: hooks run lint, subprocesses and outbound HTTP, and none of those failing
is a reason to drop a webhook delivery. The blanket ``except`` is paired with a
narrow scope and an event-log record, so a swallowed failure is still visible in
``the-loop events``.

Every skip path leaves the graph exactly where it was. There is no input to this
code that moves a work item **forward** — inputs can only cause a move not to
happen. That asymmetry is what makes it safe to let untrusted comment text reach
a hook chain at all.

Spec: docs/specs/issue-113/design.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import eventlog, harness_config
from .control import ControlConfig, ControlStore
from .sessions import WorkItemRef

logger = logging.getLogger("the-loop.graph")

__all__ = [
    "GraphContext",
    "GraphLink",
    "GraphLinkConfig",
    "comments_from",
    "render_graph_context",
    "spec_id_for",
]

# Events that carry human-authored prose a gate may route on. `pull_request_review`
# holds its text under `review`; the two comment events under `comment`.
_COMMENT_EVENTS = {
    "issue_comment": "comment",
    "pull_request_review_comment": "comment",
    "pull_request_review": "review",
}

#: The actions whose adoption safety net runs (issue-193, narrowed by issue-201) — the
#: two that *drive* the graph. ``context`` is excluded because it is documented as
#: mutating nothing, and ``clean`` because it runs while the checkout is being released.
#: The primary adoption is :meth:`GraphLink.adopt`, called before anything is spawned.
_ADOPTING_ACTIONS = frozenset({"start", "advance"})

#: The actions that do NOT require ``<specDir>/<id>/`` to already exist (issue-273).
#:
#: ``docs/specs/<id>/`` is created by the work the graph exists to gate, so keying
#: every action on it is a chicken-and-egg for a work item that begins life as a plain
#: ticket: the one ``required: true`` node of ``pdlc-work-item-loop`` —
#: ``phase-selection``, "where every work item starts" (issue-177, decision-067/068) —
#: is the node that runs *before* any spec exists, and gating it on the spec folder is
#: what routed it around every ticket not minted by ``/create-ticket``.
#:
#: * ``start`` places the work item on that node. It produces no artifact, and
#:   :func:`the_loop.graph.state.state_lock` / :meth:`GraphState.save` create the
#:   directory they write into, so nothing here has to pre-create it.
#: * ``context`` is a pure read that renders the spawn prompt's process-state block.
#:   Without the exemption the block is empty for exactly the items that need it, and
#:   the spawned session walks into ``requirements-definition`` unguarded.
#:
#: ``advance`` and ``clean`` keep the predicate. Neither can be the *first* thing that
#: happens to a work item, so for them a missing directory still means "this graph was
#: never placed here" — and keeping it there preserves the module's asymmetry: no input
#: moves an unplaced work item forward.
_SPEC_DIR_OPTIONAL_ACTIONS = frozenset({"start", "context"})


@dataclass
class GraphLinkConfig:
    """Mirror of ``routing.graph``.

    ``enabled`` defaults to true: a graph nothing drives is the bug this work
    item fixes. It stays configurable because an operator who does not keep
    specs in the repo gets nothing from the coupling — though for them it is
    already inert, since a work item with no spec directory is skipped.

    ``spec_dir`` defaults to **unset**, and that is the whole of issue-123. It
    used to default to ``docs/specs``, which was never merely a default: it is
    passed to ``build_runtime`` as an explicit ``spec_root``, and an explicit
    ``spec_root`` overrides the repository's own ``workflow.specDir``. Always
    being set therefore meant *never* honouring a watched repository's value —
    a repo that kept its specs elsewhere had its graph silently skipped, on one
    flat value the operator could not vary per repository (decision-032: the
    daemon watches several). Empty means "the repository decides"; a non-empty
    value is a deliberate override for a checkout that carries no harness
    config at all.
    """

    enabled: bool = True
    spec_dir: str = ""

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "GraphLinkConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            # `or ""` rather than a default, so an explicit `specDir: null` reads
            # as unset instead of as the string "None".
            spec_dir=str(data.get("specDir") or ""),
        )


def spec_id_for(ref: WorkItemRef) -> Optional[str]:
    """``github:owner/repo#113`` → ``"issue-113"``; ``None`` if not GitHub.

    The ingress and the graph name the same work item differently — a
    provider-qualified ref versus a spec-directory id — and this is the whole of
    the translation between them.

    ``ref.number`` is an ``int`` parsed by :meth:`WorkItemRef.parse`, so the
    result cannot contain a path separator however the ref arrived on the wire
    (issue-113 A5). Other providers return ``None`` rather than a guess: the
    ``issue-<n>`` convention is GitHub's, and a wrong directory name would
    silently start the wrong work item's graph.
    """
    if ref.provider != "github":
        return None
    return f"issue-{int(ref.number)}"


def _pr_repo(work_item: WorkItemRef, pr: WorkItemRef) -> str:
    """The repository qualifier for ``pr``'s inner loop — ``""`` in the origin repo.

    A work item may be delivered by pull requests in several repositories
    (issue-183), and a PR number is unique only within one. Derived from the two
    refs the caller already holds, so nothing new has to reach the dispatcher:
    same repository as the ticket ⇒ the shipped ``pr-loops/pr-<n>/`` path;
    another repository ⇒ ``pr-loops/<owner>__<repo>/pr-<n>/``, still under the
    ONE spec directory in the origin repository's checkout.
    """
    return "" if pr.path == work_item.path else pr.path


def _repo_slug(remote_url: str) -> str:
    """``owner/repo`` (lowercased) from any git remote URL form.

    Handles the shapes a real checkout carries — `https://host/o/r.git`,
    `git@host:o/r.git`, `ssh://git@host/o/r`, and a proxied `http://host/git/o/r`
    — by taking the last two path components, because that is the part every
    form agrees on. Anything shorter yields ``""``, which never matches.
    """
    trimmed = remote_url.strip().rstrip("/")
    if trimmed.endswith(".git"):
        trimmed = trimmed[: -len(".git")]
    parts = [p for p in trimmed.replace(":", "/").split("/") if p]
    if len(parts) < 2:
        return ""
    return "/".join(parts[-2:]).lower()


def _is_contained(root: Path, spec_dir: str) -> bool:
    """Whether ``root / spec_dir`` stays inside ``root`` (issue-123 R4.3).

    ``spec_dir`` now comes from a repository rather than from the operator, so
    an absolute or ``../``-escaping value would let a checkout name a write
    target elsewhere on the operator's machine. Only whoever can commit to the
    work item's own repository can set it — the ownership proof runs first — but
    "already trusted" is not a reason to hand out the whole filesystem.

    Enforced on the daemon path only. ``the-loop check`` and ``the-loop graph``
    resolve the same key from the same file and are unchanged: they run inside
    the repository at the user's own invocation, where the value is the user's.

    Fails closed on an ``OSError``: a path that cannot be resolved is not a
    path that has been shown to be contained.
    """
    candidate = Path(spec_dir)
    if candidate.is_absolute():
        return False
    try:
        resolved = (root / candidate).resolve()
        base = root.resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


def comments_from(routed, authorized: Sequence[str] = ()) -> List[Dict[str, str]]:
    """The human-authored comments an event carries, each with its author.

    Author and body travel **together, always**: ``classify-feedback`` decides
    authorization by author, so a body with no author is text the gate cannot
    authorize. Such an entry is dropped here rather than passed with an empty
    author, which would arrive at the hook looking like an anonymous review.

    Note what this deliberately does *not* do: it does not filter by
    ``authorizedUsers`` and does not drop self-authored bodies. That decision
    already lives in ``classify-feedback``, and an authorization check
    implemented in two places is one that will eventually disagree with itself.

    One thing it does do, since issue-309 (decision-103 D4): a comment carrying a
    ledger **envelope** — the bus's record of a gate answer given on a channel —
    is attributed to the person the envelope names, so ``approvedBy`` records a
    person rather than the credential that relayed them. **Only** when the
    comment's real poster is in ``authorized`` and the named GitHub login is too:
    an envelope is comment text, so it may narrow from one authorized identity
    to another and never widen. A work-item collaborator's forged envelope
    (A3) rewrites nothing.
    """
    key = _COMMENT_EVENTS.get(getattr(routed, "event", ""))
    if not key:
        return []
    raw = (getattr(routed, "payload", None) or {}).get(key) or {}
    body = str(raw.get("body") or "").strip()
    author = str((raw.get("user") or {}).get("login") or "").strip()
    if not body or not author:
        return []
    return [{"author": _attributed(author, body, authorized), "body": body}]


def _attributed(author: str, body: str, authorized: Sequence[str]) -> str:
    """The envelope's GitHub login when both the poster and it are authorized."""
    if not authorized or author not in set(authorized):
        return author
    from .channels.envelope import parse as parse_envelope

    envelope = parse_envelope(body)
    if envelope is None:
        return author
    named = str(envelope.actor.get("github") or "").strip()
    if named and named in set(authorized):
        return named
    return author


@dataclass(frozen=True)
class GraphContext:
    """A work item's graph state, as the dispatcher reads it (issue-148, D2).

    Pure data, resolved read-only **before** anything is delivered — this is
    what lets a prompt say which node the item stands on, and what lets the
    dispatcher notice an item parked at a human gate. Everything here derives
    from the-loop's own state and graph definition: no comment body, no payload
    text, so nothing in it widens what untrusted input can reach a prompt.
    """

    current_node: str
    phase: str
    #: pending | in-progress | waiting | blocked | parked | complete | escalated.
    #: ``pending`` (issue-273) is the one status that describes a node the work item
    #: has **not** entered: the graph knows where it is about to be placed, and the
    #: spawn prompt is rendered before the placement happens (issue-148, D5 — the
    #: write only follows a successful spawn). It is deliberately not part of
    #: :attr:`at_human_gate`: nothing has been entered, so there is no gate to hand
    #: an event to.
    status: str
    reason: str
    messages: Tuple[str, ...]
    next_command: str
    actor: str  # agent | human — who the current node waits on
    #: Where the OUTER loop's artifacts are iterated for THIS work item
    #: (issue-183): ``pull-request``, or empty for the default — the work item
    #: itself. Chosen by its author at `phase-selection` and frozen into
    #: `graph-state.json`, never a repository or machine setting. The INNER
    #: loop ignores it: a pull request's loop runs on that pull request.
    surface: str = ""
    #: Which loop this state walks, as recorded at its first entry (issue-185).
    #: Read here for one reason (issue-199): a contribution has no outer loop,
    #: so the prompt must not tell its session where to put one.
    loop: str = ""

    @property
    def at_human_gate(self) -> bool:
        """Parked/waiting on a human node — the consult-first case (D4)."""
        return self.actor == "human" and self.status in ("waiting", "parked")


def _is_contribution(loop: str) -> bool:
    """Whether ``loop`` is the shipped contribution loop (issue-199).

    One import, one comparison — but kept a named predicate because two very
    different readers ask it: the prompt block here, and the phase-selection
    gate's surface question. Both mean "this work item has no outer loop".
    """
    from .graph.model import PDLC_CONTRIBUTION_LOOP

    return loop == PDLC_CONTRIBUTION_LOOP


def _is_adhoc(loop: str) -> bool:
    """Whether ``loop`` is the shipped ad-hoc loop (issue-225).

    Its sibling above means "no outer loop"; this one means something stronger
    — **no process at all**, so no spec chain to place anywhere and no artifact
    to iterate. Separate predicates because the sentence each produces differs,
    and collapsing them would tell an ad-hoc session it is a guest.
    """
    from .graph.model import PDLC_ADHOC_LOOP

    return loop == PDLC_ADHOC_LOOP


def _is_review(loop: str) -> bool:
    """Whether ``loop`` is the shipped review loop (issue-279).

    The third sentence of the family: not "no outer loop", not "no process",
    but **no authorship at all** — the session is the reviewer of somebody
    else's change, so the prompt must say the one thing the other loops never
    need to: change no code.
    """
    from .graph.model import PDLC_REVIEW_LOOP

    return loop == PDLC_REVIEW_LOOP


def _surface_line(surface: str) -> str:
    """One sentence naming where the OUTER loop's artifacts are iterated.

    Composed from the-loop's own vocabulary and a value that is one of two
    literals — no payload text enters it (R3.6). The value is this **work
    item's** own, chosen by its author at `phase-selection` (issue-183); an
    unset one is the default, the work item itself.
    """
    if surface == "pull-request":
        return (
            "a pull request in the repository the ticket was created in — the "
            "surface chosen for this work item at phase-selection"
        )
    return (
        "this work item (the default) — comment on the ticket, and do not open "
        "a pull request just to carry the spec chain"
    )


def render_graph_context(
    ctx: Optional["GraphContext"],
    item_id: str,
    verdict: str = "",
    pr_number: Optional[int] = None,
    pr_repo: str = "",
) -> str:
    """The ``$graph_context`` prompt block (issue-148, D3).

    Empty when there is no context — the templates carry the variable
    unconditionally, and an out-of-graph repository renders byte-identical
    prompts modulo this empty substitution (R3.4). ``verdict`` carries a
    gate-first outcome (D4) so the session knows what the gate just decided
    about the event it is receiving.

    ``pr_number`` marks an **inner-loop** prompt (issue-172): the block then
    names the PR's own loop and its claim command carries ``--pr <n>`` — the
    report-back channel must address the loop the session is actually walking,
    or a PR session's claim would evaluate the work item's outer gates instead.
    ``pr_repo`` adds ``--pr-repo <owner>/<repo>`` for a pull request in a
    contributing repository (issue-183), for the same reason: without it the
    claim would address a *different* loop in the origin repository.
    """
    if ctx is None or not ctx.current_node:
        return ""
    scope = (
        f"pull request #{pr_number}'s pdlc-pr-loop on {item_id}"
        if pr_number is not None
        else item_id
    )
    lines = [
        f"the-loop process state for {scope}:",
        f"  node: {ctx.current_node}"
        + (f" (phase: {ctx.phase})" if ctx.phase else "")
        + f" — status: {ctx.status}",
    ]
    if ctx.status == "pending":
        # issue-273: the work item has not entered this node yet, and this block is
        # the only thing standing between the auto-execute prompt and a session that
        # starts a phase nobody selected. Everything below — the reason, the gate
        # messages, the resume command, the claim command — describes a node that was
        # entered; none of it is true yet, so none of it is rendered.
        #
        # Worded for BOTH prompts. At a spawn the entry follows within moments, which
        # is the case this exists for. But an *event* prompt can carry a pending
        # context too — a session that predates the coupling, or one whose entry
        # faulted — and there the assignment never comes. So the last line makes the
        # stall speak instead of waiting: an agent that is never placed says so on the
        # work item rather than deciding for itself that it may begin.
        lines.append(
            "  NOT ENTERED YET — the-loop has not placed this work item on any node. Do "
            "not start a phase, write a spec artifact, set a phase label or open a pull "
            "request: the loop delivers this node's assignment into this conversation "
            "when it enters it"
        )
        if ctx.actor == "human":
            lines.append(
                "  this node is a HUMAN gate — the loop waits for an authorized person "
                "on the work item. Do not claim it, do not answer it on their behalf, "
                "and do not start the work it gates"
            )
        lines.append(
            "  if no assignment arrives, say so on the work item — never start the "
            "phase yourself"
        )
        lines.append(
            "  (this block is the-loop's own state, not part of the event payload)"
        )
        return "\n".join(lines)
    if ctx.reason:
        lines.append(f"  reason: {ctx.reason}")
    for message in ctx.messages:
        lines.append(f"  gate: {message}")
    if verdict:
        lines.append(f"  this event was classified by the gate first: {verdict}")
    if ctx.next_command:
        lines.append(f"  resume with: `/the-loop:{ctx.next_command} {item_id}`")
    claim_suffix = f" --pr {pr_number}" if pr_number is not None else ""
    if pr_number is not None and pr_repo:
        claim_suffix += f" --pr-repo {pr_repo}"
    if pr_number is not None:
        lines.append(
            "  iterate on: this pull request (the inner loop always runs on its "
            "PR — no setting moves it)"
        )
    elif _is_contribution(ctx.loop):
        # A contribution has no outer loop to place (issue-199), so it is not
        # told where to put one: its single artifact and its results belong on
        # the thread it was invited into.
        lines.append(
            "  iterate on: this work item (a contribution has no outer loop — "
            "post the plan and its results here, and open no pull request but "
            "the one carrying the code)"
        )
    elif _is_adhoc(ctx.loop):
        # An ad-hoc task has no spec chain at all (issue-225), so there is
        # nothing to place and nothing to iterate: the thread is the whole
        # surface, and a pull request is opened only if the change needs one.
        lines.append(
            "  iterate on: this work item (an ad-hoc task has no spec chain — "
            "do the work, report back here, ask follow-ups here, and open a "
            "pull request only if the change needs one)"
        )
    elif _is_review(ctx.loop):
        # A review authors nothing (issue-279): its whole product is judgement
        # on the thread, so the session is told the one rule the other loops
        # never need — hands off the code.
        lines.append(
            "  iterate on: this thread (this is a REVIEW — post the brief's "
            "answers, findings and follow-ups here; change no code, commit "
            "nothing, and open no pull request)"
        )
    else:
        lines.append(
            f"  iterate the outer loop's artifacts on: {_surface_line(ctx.surface)}"
        )
    lines.append(
        "  when this node's work is done, run: "
        f"`the-loop graph complete {item_id}{claim_suffix}`"
    )
    lines.append(
        "  (this block is the-loop's own state, not part of the event payload)"
    )
    return "\n".join(lines)


class GraphLink:
    """Drives the process graph from ingress events. Never raises."""

    def __init__(
        self,
        config: GraphLinkConfig,
        control: Optional[ControlConfig] = None,
        control_store: Optional[ControlStore] = None,
        authorized_users: Optional[Sequence[str]] = None,
        assignment_sink: Optional[Any] = None,
        frozen_graph_sink: Optional[Any] = None,
    ):
        self.config = config
        self.control = control or ControlConfig()
        self.control_store = control_store
        self.authorized_users = list(authorized_users or [])
        # The graph-assigns channel (issue-172): a callable
        # ``(work_item, pr_number, text) -> bool`` the dispatcher provides so
        # the `deliver-assignment` entry hook can push an entered node's
        # assignment into the loop's bound session. None on the CLI path — the
        # hook then skips, because a claiming session already reads the same
        # facts from its command's envelope.
        self.assignment_sink = assignment_sink
        # The frozen-graph channel (issue-177): a callable
        # ``(work_item, frozen) -> None`` the dispatcher provides so the
        # phase-selection gate's frozen graph reaches the portable session
        # record. None on the CLI path — `graph-state.json` is the
        # authoritative copy and is checked in anyway.
        self.frozen_graph_sink = frozen_graph_sink

    # -- entry points -----------------------------------------------------------

    def on_spawn(
        self,
        work_item: WorkItemRef,
        cwd: str,
        session_id: str = "",
        runner: str = "",
        routed: Optional[Any] = None,
    ) -> None:
        """A session was spawned — enter the graph's start node.

        Idempotent by way of :meth:`Runtime.start`, which returns ``None`` for a
        work item that already has a pointer: a redelivered spawn, or a session
        respawned after a crash, never rewinds it. Either way the **session
        binding** is (re)recorded (issue-148, D6): `session: inherit` gates read
        it, and a respawned session is the new inheritance target.

        **A start node that is a human gate is then evaluated once** (issue-199),
        with the spawning event's comments attached. The comment that spawns a
        session is very often the one that answers the gate it lands on — the
        arming ``the-loop contribute`` carries the goal, by design (issue-185) —
        and it is the one comment a gate can never be handed later, because the
        control path consumes it rather than forwarding it. Without this the
        work item sits at its first node until some *unrelated* event happens to
        arrive, which is the second half of issue-199: a contribution that
        stated its goal up front still needed a second command to move.

        Deliberately narrow. Only a **fresh** entry evaluates (a respawn's
        ``start`` returns ``None``), and only a **human** node: an agent node's
        exit chain gates checked-in artifacts the session has not been given a
        chance to write, so running it here would count a failed attempt against
        work that has not begun. Waiting is the ordinary outcome and costs
        nothing but a parked pointer with a reason on it — which is more than the
        gate said before.
        """

        def call(rt, item):
            report = rt.start(item, work_item.ref)
            self._bind_session(rt, item, session_id, runner)
            if report is None or not self._entered_a_human_gate(rt, report):
                return
            rt.advance(
                item,
                ref=work_item.ref,
                event={"comments": comments_from(routed, self.authorized_users)},
            )

        self._guarded("start", work_item, cwd, call)

    def on_event(self, work_item: WorkItemRef, cwd: str, routed) -> Optional[Any]:
        """An event reached a session — advance at most one node boundary.

        The event's comments ride along as ``HookContext.event["comments"]``, so
        a human-approval node's ``classify-feedback`` finally has the input it
        was written to read. ``block``/``wait`` need no handling here: the
        runtime records them and leaves the pointer where it is.

        Returns the runtime's :class:`NodeReport` when the graph ran, ``None``
        on any skip or fault (issue-148, D4) — the consult-first path renders
        the gate's verdict into the prompt it delivers.
        """
        event = {"comments": comments_from(routed, self.authorized_users)}
        return self._guarded(
            "advance",
            work_item,
            cwd,
            lambda rt, item: rt.advance(item, ref=work_item.ref, event=event),
        )

    def on_close(self, work_item: WorkItemRef, cwd: str) -> None:
        """The item's session ended — mark the graph's binding dead (issue-148, D6).

        Best-effort like everything here: a failure leaves a stale binding,
        which :meth:`Runtime.resolve_session` treats as inheritable until the
        next spawn re-records it — the registry, not the binding, decides what
        is actually dispatched to.
        """

        def call(rt, item):
            from .graph.state import GraphState

            wi = rt.work_item(item)
            state_dir = rt.state_dir(wi) if hasattr(rt, "state_dir") else wi.spec_dir
            state = GraphState.load(state_dir, item)
            if state.session:
                state.session = {**state.session, "alive": False}
                state.save(state_dir)

        self._guarded("close", work_item, cwd, call)

    def on_cleanup(self, work_item: WorkItemRef, cwd: str, reason: str = "") -> None:
        """The item's LOCAL resources are about to go — record it (issue-186).

        Called **before** anything is torn down, because the node's entry chain
        writes into the very checkout the cleanup then removes: the phase label
        reaches the ticket and the execution-log checkpoint reaches the working
        tree while that tree still exists.

        One deliberate difference from every other entry point here: the
        ``_awaiting_start`` gate is not applied. That gate exists to stop work
        *starting* on an item nobody armed — but cleanup runs at the end of the
        life cycle, and a work item is disarmed by the very command that asks for
        it, so applying the gate would make the graph silently skip the one
        transition it is meant to record.

        Best-effort like everything here: a loop with no ``cleanup`` node, a
        checkout that is gone, or a work item with no spec directory all leave
        the teardown itself untouched.
        """
        self._guarded(
            "clean",
            work_item,
            cwd,
            lambda rt, item: rt.cleanup(item, ref=work_item.ref, reason=reason),
            require_started=False,
        )

    def context(self, work_item: WorkItemRef, cwd: str) -> Optional[GraphContext]:
        """Resolve the item's graph state, read-only (issue-148, D2).

        Runs behind the same gate order as the driving entry points — the
        ownership proof still precedes any checkout read — but runs **no**
        chain and mutates nothing. ``None`` means "unknown or not applicable",
        and every caller treats that as "deliver without context" (R3.3).
        """
        return self._guarded(
            "context", work_item, cwd, lambda rt, item: self._context_from(rt, item)
        )

    # -- the inner loop (issue-172): one pdlc-pr-loop per pull request ----------

    def on_pr_spawn(
        self,
        work_item: WorkItemRef,
        pr: WorkItemRef,
        cwd: str,
        session_id: str = "",
        runner: str = "",
    ) -> None:
        """A pull request's endpoint was spawned — enter its inner loop.

        The inner loop starts at ``implementation``: everything before it —
        requirements, design, the task DAG — is the work item's, decided once
        at the outer level. Idempotent exactly as :meth:`on_spawn` is.
        """

        def call(rt, item):
            rt.start(item, pr.ref)
            self._bind_session(rt, item, session_id, runner)

        self._guarded(
            "start",
            work_item,
            cwd,
            call,
            pr_number=pr.number,
            pr_repo=_pr_repo(work_item, pr),
        )

    def on_pr_event(
        self, work_item: WorkItemRef, pr: WorkItemRef, cwd: str, routed
    ) -> Optional[Any]:
        """An event reached a PR's endpoint — advance ITS loop, never the outer.

        The outer loop hears about the inner ones exactly once, at the
        ``await-inner-loops`` seam, by reading their checked-in state — not by
        being advanced from a PR's events. That one-way flow is what keeps a PR
        from walking the work item past gates the work item has not earned.
        """
        event = {"comments": comments_from(routed, self.authorized_users)}
        return self._guarded(
            "advance",
            work_item,
            cwd,
            lambda rt, item: rt.advance(item, ref=pr.ref, event=event),
            pr_number=pr.number,
            pr_repo=_pr_repo(work_item, pr),
        )

    def pr_context(
        self, work_item: WorkItemRef, pr: WorkItemRef, cwd: str
    ) -> Optional[GraphContext]:
        """The inner loop's state, read-only — the PR session's prompt context."""
        return self._guarded(
            "context",
            work_item,
            cwd,
            lambda rt, item: self._context_from(rt, item),
            pr_number=pr.number,
            pr_repo=_pr_repo(work_item, pr),
        )

    def on_pr_close(
        self, work_item: WorkItemRef, pr: WorkItemRef, cwd: str, merged: bool
    ) -> None:
        """The PR closed. Merged → its loop is driven to ``complete``, audited.

        A merge is the PR's approval, delivered as a GitHub state change rather
        than a reviewable comment — so the pointer is moved with the runtime's
        ``force``, which records the transition as forced and leaves every
        bypassed gate's verdict intact (issue-109 R10: a force moves the
        pointer, never forges a verdict). ``await-inner-loops`` reads only the
        pointer, so the outer loop unblocks; ``check --recompute`` still shows
        exactly which inner gates never ran. A PR closed WITHOUT merging keeps
        its pointer where it was: the work was abandoned, not finished, and the
        outer gate holding on it is the process noticing.
        """
        if not merged:
            return

        def call(rt, item):
            from .graph.runtime import force
            from .graph.state import GraphState

            state = GraphState.load(rt.state_dir(rt.work_item(item)), item)
            if not state.current_node:
                return  # never started: nothing to finish, nothing to await
            if state.current_node == "complete":
                return
            force(
                rt,
                item,
                "complete",
                reason=f"pull request {pr.ref} merged",
                actor="the-loop",
                ref=pr.ref,
            )

        self._guarded(
            "advance",
            work_item,
            cwd,
            call,
            pr_number=pr.number,
            pr_repo=_pr_repo(work_item, pr),
        )

    # -- internals --------------------------------------------------------------

    def _guarded(
        self,
        action: str,
        work_item: WorkItemRef,
        cwd: str,
        call,
        pr_number: Optional[int] = None,
        pr_repo: str = "",
        require_started: bool = True,
    ) -> Optional[Any]:
        """Run ``call`` behind every skip path, swallowing any failure.

        ``require_started`` is the one gate a caller may switch off, and exactly
        one does: :meth:`on_cleanup` (issue-186). Every other action here would
        be *starting work*, which is what the start requirement exists to hold
        back; releasing a finished item's resources is the opposite end of the
        life cycle, and the item is disarmed by the command that asks for it.

        The gate order is load-bearing: ``_checkout_belongs_to`` runs **before**
        anything reads the checkout, because resolving the spec directory reads
        that checkout's harness config and the daemon may only do so once it has
        proved the directory is the work item's own repository (decision-044,
        issue-113 A6). The set of skipped work items is unchanged by the order —
        both are pure predicates over disjoint inputs — only which reason is
        reported when both would fire, and a foreign checkout is the more
        important of the two.
        """
        if not self.config.enabled:
            return None
        item_id = spec_id_for(work_item)
        if item_id is None:
            logger.debug(
                "no spec-id convention for %s; not %sing its graph",
                work_item.ref,
                action,
            )
            return None
        if require_started and self._awaiting_start(work_item):
            logger.debug(
                "%s has not been started; not %sing its graph", work_item.ref, action
            )
            return None
        root = Path(cwd or ".")
        if not self._checkout_belongs_to(root, work_item):
            logger.warning(
                "%s is not a checkout of %s/%s, so a work item directory there "
                "belongs to a different project; not %sing a graph in it",
                root,
                work_item.owner,
                work_item.repo,
                action,
            )
            return None
        spec_dir = self._spec_dir(root)
        if not _is_contained(root, spec_dir):
            logger.warning(
                "%s resolves its spec directory to %r, which is outside the "
                "checkout; not %sing a graph there",
                root,
                spec_dir,
                action,
            )
            self._skipped(action, work_item, "spec-dir-outside-checkout", spec_dir)
            return None
        # Resolved here rather than beside the runtime build (where it used to
        # live) because adoption asks the same question: the CONTRIBUTION loop is
        # the one walk that must not adopt its repository.
        loop = (
            self._outer_loop_name(root, spec_dir, item_id, work_item)
            if pr_number is None
            else ""
        )
        self._adopt(action, root, work_item, loop)
        if (
            action not in _SPEC_DIR_OPTIONAL_ACTIONS
            and not (root / spec_dir / item_id).is_dir()
        ):
            logger.debug(
                "no %s/%s under %s; not %sing its graph",
                spec_dir,
                item_id,
                root,
                action,
            )
            self._skipped(action, work_item, "no-spec-dir", spec_dir)
            return None
        try:
            # The outer loop's call keeps its pre-issue-172 shape so an injected
            # runtime factory (tests, embedders) built for two arguments still
            # serves every outer-path caller. A contribution item (issue-185)
            # is the one exception: its resolved loop name rides along.
            if pr_number is None:
                runtime = (
                    self._build_runtime(str(root), spec_dir, loop=loop)
                    if loop
                    else self._build_runtime(str(root), spec_dir)
                )
            else:
                runtime = self._build_runtime(
                    str(root), spec_dir, pr_number=pr_number, pr_repo=pr_repo
                )
            if action == "context":
                return call(runtime, item_id)
            if self.assignment_sink is not None:
                # Bind the graph-assigns channel to THIS loop, so an entered
                # node's `deliver-assignment` hook reaches the session walking
                # it — the record's own for the outer loop, the PR's endpoint
                # for an inner one.
                sink, wi, prn = self.assignment_sink, work_item, pr_number
                runtime.config = {
                    **runtime.config,
                    "assignmentDeliver": lambda text: sink(wi, prn, text),
                    "assignmentPr": pr_number,
                    "assignmentPrRepo": pr_repo,
                }
            if self.frozen_graph_sink is not None:
                # The frozen graph is the WORK ITEM's, whichever loop froze it.
                frozen_sink, item_ref = self.frozen_graph_sink, work_item
                runtime.config = {
                    **runtime.config,
                    "frozenGraphSink": lambda frozen: frozen_sink(item_ref, frozen),
                }
            # Write actions hold the graph-state lock (issue-148): the session's
            # `graph complete` is a second writer beside this daemon, and the
            # load→mutate→save windows must not interleave. `context` stays
            # outside the lock — it is a pure read, and a stale read costs a
            # slightly stale prompt, never a wrong pointer. flock is not
            # reentrant across file handles, so everything `call` reaches must
            # not re-acquire it.
            from .graph.state import state_lock

            # The lock lives beside the state it serialises: the outer loop's
            # writers contend on the spec dir, an inner loop's on its own
            # pr-loops/pr-<n>/ — so two PRs' loops never block each other.
            lock_dir = root / spec_dir / item_id
            if pr_number is not None:
                from .graph.hooks.loops import inner_loop_state_dir

                lock_dir = inner_loop_state_dir(lock_dir, pr_number, pr_repo)
            with state_lock(lock_dir):
                return call(runtime, item_id)
        except Exception as exc:  # noqa: BLE001 — a graph fault must not cost a delivery
            logger.error(
                "graph %s for %s failed: %s", action, work_item.ref, exc, exc_info=True
            )
            eventlog.emit(
                "graph.link_failed",
                level="error",
                work_item=work_item.ref,
                action=action,
                error=str(exc),
            )
            return None

    @staticmethod
    def _entered_a_human_gate(rt: Any, report: Any) -> bool:
        """Whether the node just entered waits on a human (issue-199).

        Read from the compiled graph the runtime is walking, so the contribution
        loop's ``goal-definition``, the outer loop's ``phase-selection`` and any
        graph a repository supplies all answer for themselves. Anything
        unreadable answers *no*: not evaluating a gate leaves the work item
        exactly where the pre-issue-199 code left it, which is the safe side.
        """
        try:
            return rt.graph.node(str(getattr(report, "node", ""))).actor == "human"
        except Exception as exc:  # noqa: BLE001 — a fake runtime, or a node that went
            logger.debug("could not resolve the entered node's actor: %s", exc)
            return False

    @staticmethod
    def _bind_session(rt: Any, item_id: str, session_id: str, runner: str) -> None:
        """Record which session works this item (issue-148, D6).

        Runs inside :meth:`_guarded`'s state lock — it must not re-acquire it.
        The binding follows the runtime's OWN state location (issue-172): an
        inner loop's session binds inside its pr-loops/pr-<n>/ state, never the
        outer one — a PR's conversation must not become the inheritance target
        for the work item's human gates.
        """
        from .graph.state import GraphState

        item = rt.work_item(item_id)
        state_dir = rt.state_dir(item) if hasattr(rt, "state_dir") else item.spec_dir
        state = GraphState.load(state_dir, item_id)
        state.session = {"id": session_id, "runner": runner, "alive": True}
        state.save(state_dir)

    @staticmethod
    def _pending_context(rt: Any, state: Any) -> Optional[GraphContext]:
        """Where a work item that has not entered the graph is about to stand (issue-273).

        The dispatcher resolves the context **before** it spawns and enters the graph
        **after** (issue-148, D5: a failed spawn must not leave a labelled ticket
        pointing at a node nobody stands on). So at the one moment the auto-execute
        prompt is written, a fresh work item has no pointer — and returning ``None``
        there rendered an empty process-state block, which is how a spawned session
        came to walk into ``requirements-definition`` with the outer loop's one
        ``required: true`` node, ``phase-selection``, never having run.

        The graph's own ``start`` is that answer, and reading it costs nothing and
        writes nothing. Declared skips are deliberately **not** applied: they are made
        *at* ``phase-selection``, which is not skippable, so the start node is the start
        node — and re-deriving a route here would be this module guessing at a walk it
        is documented never to move.

        ``None`` when the graph cannot be read at all (a fake runtime, a graph that
        failed to compile): the block is then empty, exactly as before.
        """
        try:
            node = rt.graph.node(rt.graph.start)
        except Exception as exc:  # noqa: BLE001 — an unreadable graph renders nothing
            logger.debug("could not resolve the graph's start node: %s", exc)
            return None
        return GraphContext(
            current_node=node.id,
            phase=node.phase,
            status="pending",
            reason="",
            messages=(),
            # Not rendered for a pending node (see `render_graph_context`): a command
            # that has not been assigned is not a command to run.
            next_command=node.command,
            actor=node.actor,
            surface=str(getattr(state, "surface", "") or ""),
            loop=str(getattr(state, "loop", "") or ""),
        )

    @staticmethod
    def _context_from(rt: Any, item_id: str) -> Optional[GraphContext]:
        """Derive a :class:`GraphContext` from state + graph, mutating nothing.

        Reads the runtime's OWN state location (issue-172): an inner-loop
        runtime's context comes from its ``pr-loops/pr-<n>/`` state, so a PR
        session's prompt describes the loop that session is walking — never the
        outer pointer.
        """
        from .graph.state import GraphState

        item = rt.work_item(item_id)
        state_dir = rt.state_dir(item) if hasattr(rt, "state_dir") else item.spec_dir
        state = GraphState.load(state_dir, item_id)
        if not state.current_node:
            return GraphLink._pending_context(rt, state)
        node = rt.graph.node(state.current_node)
        rec = state.nodes.get(node.id)
        reason, messages = "", ()
        if node.terminal and rec is not None and rec.outcome:
            status = "complete"
        elif state.parked:
            status = "waiting" if node.actor == "human" else "parked"
            reason = str(state.parked.get("reason") or "")
        elif rec is not None and rec.last_block:
            status = "escalated" if rec.attempts >= node.max_attempts else "blocked"
            messages = (rec.last_block,)
        else:
            status = "in-progress"
        return GraphContext(
            current_node=node.id,
            phase=node.phase,
            status=status,
            reason=reason,
            messages=messages,
            next_command=node.command,
            actor=node.actor,
            # The work item's own frozen choice (issue-183) — read from the
            # same state this context comes from, because the prompt is
            # rendered far from the runtime and there is no config to ask.
            surface=str(getattr(state, "surface", "") or ""),
            # And which loop it is walking (issue-185), for the one prompt line
            # that differs between owning a work item and contributing to one.
            loop=str(getattr(state, "loop", "") or ""),
        )

    @staticmethod
    def _skipped(
        action: str, work_item: WorkItemRef, reason: str, spec_dir: str
    ) -> None:
        """Record a skip that would otherwise be invisible (issue-123).

        A work item that is labelled, armed and spawned but whose graph never
        moves is worth one line in ``the-loop events``: at ``logger.debug`` the
        operator saw a successful delivery and an inert graph with nothing
        joining the two.

        Only the two spec-directory refusals record. The others already have a
        voice: ``enabled: false`` is the operator's own switch, a non-GitHub ref
        is not a work item the graph can name, ``_awaiting_start`` is already
        logged by the dispatcher as ``dispatch.dropped`` with
        ``reason: awaiting-start``, and a foreign checkout is a ``warning``.
        """
        eventlog.emit(
            "graph.skipped",
            work_item=work_item.ref,
            action=action,
            reason=reason,
            spec_dir=spec_dir,
        )

    def _outer_loop_name(
        self, root: Path, spec_dir: str, item_id: str, work_item: WorkItemRef
    ) -> str:
        """Which outer-path loop this work item walks — ``""`` for the default.

        State-first, control-record-second (issue-185): once a loop has
        started, `graph-state.json`'s recorded ``loop`` is the fact and a later
        control command cannot re-shape a walk in progress; before the first
        start, the arming command recorded in the portable control record is
        the declared intent (``contribute`` → the contribution loop, ``do`` →
        the ad-hoc loop, issue-225). Only a shipped **outer-path** loop is ever
        returned — the state file is agent-writable, so an invented name reads
        as the default rather than choosing a graph (fail closed).
        """
        from .graph.model import LOOP_FOR_CONTROL_COMMAND, resolve_outer_loop
        from .graph.state import GraphState

        try:
            state = GraphState.load(root / spec_dir / item_id, item_id)
            recorded = str(getattr(state, "loop", "") or "")
        except Exception as exc:  # noqa: BLE001 — an unreadable state is the default
            logger.debug("could not read %s's recorded loop: %s", item_id, exc)
            recorded = ""
        if recorded:
            return resolve_outer_loop(recorded)
        if self.control_store is not None:
            try:
                record = self.control_store.get(work_item)
                if record is not None:
                    return LOOP_FOR_CONTROL_COMMAND.get(record.command, "")
            except Exception as exc:  # noqa: BLE001
                logger.debug("could not read %s's control record: %s", item_id, exc)
        return ""

    def adopt(self, work_item: WorkItemRef, cwd: str) -> None:
        """Adopt an unconfigured checkout **before anything is spawned** (issue-201).

        This is the entry point the dispatcher calls between preparing the
        workspace and rendering the prompt, and its whole reason for existing is
        *ordering*. issue-193 wrote the default from :meth:`on_spawn`, which the
        dispatcher calls **after** ``tmux.spawn`` — so a session could begin, its
        SessionStart hook included, in a checkout whose ``.the-loop/`` did not
        exist yet. The window was short and the write is fast, but a harness whose
        point is predictability cannot leave "did the agent read a config?" to a
        race.

        It cannot simply call :func:`harness_config.scaffold`, because at this
        point ``cwd`` is not yet known to be the work item's own repository:
        under the legacy ``spawnWorkdir`` setup it is a static directory that may
        be the operator's own checkout. So the same gates run here as anywhere
        else the coupling touches a checkout — the coupling is enabled, the work
        item is nameable, an authorized human armed it, and ``origin`` proves the
        directory (issue-113 A6, decision-044) — plus the contribution carve-out.

        :meth:`_adopt` stays behind it, on the driving actions, as an idempotent
        safety net: a session spawned before this existed, or any path that does
        not come through the dispatcher, is still adopted at its next advance.

        Best-effort and silent about it, like everything here.
        """
        if not self.config.enabled:
            return
        item_id = spec_id_for(work_item)
        if item_id is None:
            return
        if self._awaiting_start(work_item):
            return
        root = Path(cwd or ".")
        if not self._checkout_belongs_to(root, work_item):
            logger.warning(
                "%s is not a checkout of %s/%s; not adopting it",
                root,
                work_item.owner,
                work_item.repo,
            )
            return
        loop = self._outer_loop_name(root, self._spec_dir(root), item_id, work_item)
        self._write_default(root, work_item, loop)

    def _adopt(
        self, action: str, root: Path, work_item: WorkItemRef, loop: str
    ) -> None:
        """The driving actions' adoption — the safety net behind :meth:`adopt`.

        The primary moment is pre-spawn (issue-201); this one catches a work item
        whose session started before that existed, or that reaches the graph by a
        route the dispatcher does not own. It is idempotent, so the common case
        here is :func:`harness_config.scaffold` reporting ``"present"``.

        **Only on the actions that drive the graph** (:data:`_ADOPTING_ACTIONS`).
        ``context`` resolves a prompt's block and is documented as mutating
        nothing — an exception for "only a config file" is how that property
        stops being true — and ``clean`` runs as the work item's local resources
        are released, where a newly written file would be leaving litter in a
        checkout about to be removed.
        """
        if action not in _ADOPTING_ACTIONS:
            return
        self._write_default(root, work_item, loop)

    def _write_default(self, root: Path, work_item: WorkItemRef, loop: str) -> None:
        """Write the built-in default into ``root``, unless it is a guest's (issue-193).

        the-loop is routinely pointed at a repository that never ran
        ``/the-loop:init``: the daemon clones it, spawns a session in it, and the
        session finds no ``.the-loop/`` at all — no workflow, no tooling, no
        phases.

        **Never for a guest loop.** ``pdlc-contribution-loop`` joins somebody
        else's in-progress work item, and PR #187 decided the-loop's machinery
        stays out of that repository's history; ``pdlc-review-loop``
        (issue-279) reviews somebody else's change under the same rule. A
        committed file declaring the-loop's process in a repository that never
        asked for it would be the loudest possible breach of that; a guest
        does not install itself.

        Both callers have already proved the checkout is the work item's own.
        Best-effort: :func:`harness_config.scaffold` never raises, and a
        repository that could not be adopted is worked exactly as it was before.
        """
        from .graph.model import GUEST_LOOPS

        if loop in GUEST_LOOPS:
            return
        if harness_config.scaffold(root, work_item.owner, work_item.repo) != "written":
            return
        written = harness_config.config_path(root)
        eventlog.emit(
            "harness.config_scaffolded",
            work_item=work_item.ref,
            path=str(written) if written else "",
            repo=f"{work_item.owner}/{work_item.repo}",
        )

    def _spec_dir(self, root: Path) -> str:
        """Where this work item's specs live, as declared.

        The repository's own ``workflow.specDir`` is the answer — that is the ⟶
        direction decision-044 allows, and where a project keeps its specs is a
        fact about that project's layout. ``config.spec_dir`` overrides it only
        when the operator set it deliberately.

        Returns the declared value **whether or not it is usable**; containment
        is the caller's gate (:func:`_is_contained`), so a refused value can
        still be named in the log and the ``graph.skipped`` record. A refusal the
        operator cannot see the value of is a refusal they cannot fix.

        Resolved **once** per call and threaded into both the ``is_dir()`` gate
        and the runtime, so the directory the skip decision is made on and the
        directory ``graph-state.json`` is written into cannot drift apart.

        Reading the checkout is safe here and only here: the caller has already
        proved via the ``origin`` remote that this directory is the work item's
        own repository. ``harness_config.load`` degrades a missing, unparseable
        or non-mapping file to ``{}``, so a repository mid-edit falls back to the
        default rather than costing a delivery.
        """
        return self.config.spec_dir or harness_config.spec_dir(
            harness_config.load(root)
        )

    def _awaiting_start(self, work_item: WorkItemRef) -> bool:
        """Whether an authorized user has yet to start this item (issue-106).

        The same gate the spawn path applies. Without it, every labelled item in
        the operator's repos would enter node one and fire its entry hooks —
        labels written, reviewers notified — for work nobody asked to run.
        """
        if not (self.control.enabled and self.control.require_start_command):
            return False
        if self.control_store is None:
            return True  # fail closed: the policy is on and its record is missing
        return not self.control_store.start_requested(work_item)

    def _checkout_belongs_to(self, root: Path, work_item: WorkItemRef) -> bool:
        """Whether ``root`` is a checkout of the work item's own repository.

        The spec id is derived from the issue **number** alone — `issue-15` names
        a directory, not a project — so without this check an event about *any*
        repository's issue #15 would drive `docs/specs/issue-15` in whatever
        checkout the daemon is pointed at. Under the default
        ``spawnWorkdir: "."`` that checkout is the operator's own repo, which
        means unrelated inbound events would write graph state and execution-log
        entries into their work items (issue-113, A6).

        Read from the checkout's ``origin`` remote via git itself rather than by
        parsing ``.git/config``, because the config a worktree uses is not the
        file next to its ``.git``. **Fails closed:** a directory that is not a
        checkout, has no origin, or cannot be interrogated is not a match — it
        is exactly the case where we cannot tell whose work item this is.
        """
        url = self._origin_url(root)
        if not url:
            return False
        return _repo_slug(url) == f"{work_item.owner}/{work_item.repo}".lower()

    @staticmethod
    def _origin_url(root: Path) -> str:
        import subprocess

        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("could not read the origin remote of %s: %s", root, exc)
            return ""
        return proc.stdout.strip() if proc.returncode == 0 else ""

    def _build_runtime(
        self,
        cwd: str,
        spec_dir: str,
        pr_number: Optional[int] = None,
        pr_repo: str = "",
        loop: str = "",
    ) -> Any:
        """The graph runtime rooted at the session's checkout.

        Not the daemon's cwd: with ``routing.workspace`` enabled each work item
        has its own git worktree, and ``graph-state.json`` belongs in the tree
        the agent is working in — that is what gets committed and reviewed in
        the PR diff.

        Imported lazily so the ingress does not pay for the graph package (and
        its yaml parse of ``pdlc.yaml``) on a path where the coupling is off.

        ``spec_dir`` is the value :meth:`_spec_dir` already resolved, not the raw
        CLI key. Passing the resolved value is what makes the gate and the
        runtime agree on one directory (issue-123 R2.1); passing the raw key is
        what made them disagree.

        ``authorized_users`` is threaded through deliberately: it is what
        ``classify-feedback`` filters comments on, and a runtime built without
        it fails closed on every human gate — the coupling would deliver the
        comments and the gate would still never resolve.
        """
        from .graph.bootstrap import build_runtime

        return build_runtime(
            Path(cwd),
            spec_root=spec_dir,
            authorized_users=self.authorized_users,
            pr_number=pr_number,
            pr_repo=pr_repo,
            loop=loop,
        )
