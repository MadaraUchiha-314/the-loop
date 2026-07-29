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
  work item enters the graph;
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
from typing import Any, Dict, List, Optional, Sequence

from . import eventlog
from .control import ControlConfig, ControlStore
from .sessions import WorkItemRef

logger = logging.getLogger("the-loop.graph")

__all__ = ["GraphLink", "GraphLinkConfig", "comments_from", "spec_id_for"]

# Events that carry human-authored prose a gate may route on. `pull_request_review`
# holds its text under `review`; the two comment events under `comment`.
_COMMENT_EVENTS = {
    "issue_comment": "comment",
    "pull_request_review_comment": "comment",
    "pull_request_review": "review",
}


@dataclass
class GraphLinkConfig:
    """Mirror of ``webhooks.ghWebhook.routing.graph``.

    ``enabled`` defaults to true: a graph nothing drives is the bug this work
    item fixes. It stays configurable because an operator who does not keep
    specs in the repo gets nothing from the coupling — though for them it is
    already inert, since a work item with no spec directory is skipped.
    """

    enabled: bool = True
    spec_dir: str = "docs/specs"

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "GraphLinkConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            spec_dir=str(data.get("specDir", "docs/specs")),
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


def comments_from(routed) -> List[Dict[str, str]]:
    """The human-authored comments an event carries, each with its author.

    Author and body travel **together, always**: ``classify-feedback`` decides
    authorization by author, so a body with no author is text the gate cannot
    authorize. Such an entry is dropped here rather than passed with an empty
    author, which would arrive at the hook looking like an anonymous review.

    Note what this deliberately does *not* do: it does not filter by
    ``authorizedUsers`` and does not drop self-authored bodies. That decision
    already lives in ``classify-feedback``, and an authorization check
    implemented in two places is one that will eventually disagree with itself.
    """
    key = _COMMENT_EVENTS.get(getattr(routed, "event", ""))
    if not key:
        return []
    raw = (getattr(routed, "payload", None) or {}).get(key) or {}
    body = str(raw.get("body") or "").strip()
    author = str((raw.get("user") or {}).get("login") or "").strip()
    if not body or not author:
        return []
    return [{"author": author, "body": body}]


class GraphLink:
    """Drives the process graph from ingress events. Never raises."""

    def __init__(
        self,
        config: GraphLinkConfig,
        control: Optional[ControlConfig] = None,
        control_store: Optional[ControlStore] = None,
        authorized_users: Optional[Sequence[str]] = None,
    ):
        self.config = config
        self.control = control or ControlConfig()
        self.control_store = control_store
        self.authorized_users = list(authorized_users or [])

    # -- entry points -----------------------------------------------------------

    def on_spawn(self, work_item: WorkItemRef, cwd: str) -> None:
        """A session was spawned — enter the graph's start node.

        Idempotent by way of :meth:`Runtime.start`, which returns ``None`` for a
        work item that already has a pointer: a redelivered spawn, or a session
        respawned after a crash, never rewinds it.
        """
        self._guarded(
            "start", work_item, cwd, lambda rt, item: rt.start(item, work_item.ref)
        )

    def on_event(self, work_item: WorkItemRef, cwd: str, routed) -> None:
        """An event reached a session — advance at most one node boundary.

        The event's comments ride along as ``HookContext.event["comments"]``, so
        a human-approval node's ``classify-feedback`` finally has the input it
        was written to read. ``block``/``wait`` need no handling here: the
        runtime records them and leaves the pointer where it is.
        """
        event = {"comments": comments_from(routed)}
        self._guarded(
            "advance",
            work_item,
            cwd,
            lambda rt, item: rt.advance(item, ref=work_item.ref, event=event),
        )

    # -- internals --------------------------------------------------------------

    def _guarded(self, action: str, work_item: WorkItemRef, cwd: str, call) -> None:
        """Run ``call`` behind every skip path, swallowing any failure."""
        if not self.config.enabled:
            return
        item_id = spec_id_for(work_item)
        if item_id is None:
            logger.debug(
                "no spec-id convention for %s; not %sing its graph",
                work_item.ref,
                action,
            )
            return
        if self._awaiting_start(work_item):
            logger.debug(
                "%s has not been started; not %sing its graph", work_item.ref, action
            )
            return
        root = Path(cwd or ".")
        if not (root / self.config.spec_dir / item_id).is_dir():
            logger.debug(
                "no %s/%s under %s; not %sing its graph",
                self.config.spec_dir,
                item_id,
                root,
                action,
            )
            return
        try:
            call(self._build_runtime(str(root)), item_id)
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

    def _build_runtime(self, cwd: str) -> Any:
        """The graph runtime rooted at the session's checkout.

        Not the daemon's cwd: with ``routing.workspace`` enabled each work item
        has its own git worktree, and ``graph-state.json`` belongs in the tree
        the agent is working in — that is what gets committed and reviewed in
        the PR diff.

        Imported lazily so the ingress does not pay for the graph package (and
        its yaml parse of ``pdlc.yaml``) on a path where the coupling is off.

        ``authorized_users`` is threaded through deliberately: it is what
        ``classify-feedback`` filters comments on, and a runtime built without
        it fails closed on every human gate — the coupling would deliver the
        comments and the gate would still never resolve.
        """
        from .graph.bootstrap import build_runtime

        return build_runtime(
            Path(cwd),
            spec_root=self.config.spec_dir,
            authorized_users=self.authorized_users,
        )
