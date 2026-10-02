"""A work item's terminal record — what outlives its checkout (issue-452).

The closure (issue-329) stamps a work item's portable record with an ``ended``
section, and cleanup keeps that record on purpose. Until issue-452 the stamp
said only *that* the item ended. Everything about *how* — the node its graph
reached, the phases it froze, the pull requests that delivered it — lived in
``work-item-state.json`` inside the checkout, and the very same closure removed
the checkout before anything read it. A later ``the-loop check <ref>`` from any
other directory then found no state, fell back to the graph's start node and
evaluated the caller's directory: a delivered item read as never started.

This module is the two halves of the fix, kept free of I/O policy so both are
testable on their own:

- **write**: :func:`terminal_record` copies the ending out of a runtime's state
  file while the checkout still exists; :func:`closure_outcome` classifies it.
  The dispatcher stores both in the ``ended`` stamp.
- **read**: :func:`ended_for` finds that stamp from the CLI config alone, and
  :func:`archived_report` turns it into the answer ``check`` gives instead of a
  start-node guess.

## What the record is not

It is a **copy of an agent-writable file**, so it is a report and never an
authority (issue-109's rule, restated). Nothing reads it back into routing, a
gate, a spawn or a cleanup. Every field is filtered on the way in exactly as the
runtime filters it on read — the node must exist in the compiled graph, skips go
through ``declared_skips``, opt-ins through ``selected``, a pull request's URL is
re-derived from its parsed ref — and evidence names are restricted to plain
path characters, because ``check`` prints them to a terminal.

Spec: docs/specs/issue-452/design.md.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

logger = logging.getLogger("the-loop.archive")

__all__ = [
    "CANCELLED",
    "CLOSED_EXTERNALLY",
    "COMPLETED",
    "MAX_EVIDENCE",
    "OUTCOMES",
    "RECORDED",
    "UNAVAILABLE",
    "UNKNOWN",
    "archived_report",
    "cancelled",
    "closure_outcome",
    "ended_for",
    "terminal_record",
]

#: How a work item ended. ``completed`` is only ever a **recorded** claim on the
#: loop's completion node — never inferred from a closed or merged ticket.
COMPLETED = "completed"
CANCELLED = "cancelled"
CLOSED_EXTERNALLY = "closed-externally"
UNKNOWN = "unknown"
OUTCOMES = (COMPLETED, CANCELLED, CLOSED_EXTERNALLY, UNKNOWN)

#: Whether an archived report carries the terminal record (``recorded``) or only
#: the closure's own facts (``unavailable`` — a stamp from before issue-452, or a
#: checkout that could not be read when the item closed).
RECORDED = "recorded"
UNAVAILABLE = "unavailable"

#: The most evidence names a record keeps — a listing, not an inventory.
MAX_EVIDENCE = 50

#: A plain relative path: what an evidence name must look like to be recorded.
#: Anything else (spaces, control characters, an escape sequence) is dropped
#: rather than escaped, because the operator's terminal is where it lands.
_PLAIN_PATH = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")

#: A scalar choice (harness, model, effort, …): short and printable, or nothing.
_PLAIN_VALUE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}")


def _utcnow() -> str:
    from .graph.state import utc_now

    return utc_now()


def _plain(value: Any) -> str:
    text = str(value or "")
    return text if _PLAIN_VALUE.fullmatch(text) else ""


def _completion_node(graph: Any) -> Optional[Any]:
    """The loop's completion node: terminal, and named or staged ``complete``.

    ``cleanup`` and ``escalated`` are terminal too, and neither is completion —
    which is why "the pointer reached a terminal node" is not the test.
    """
    for node in graph.ordered():
        if node.terminal and (node.stage == "complete" or node.id == "complete"):
            return node
    return None


def _evidence(spec_dir: Path) -> List[str]:
    """The plain-named files under ``<spec_dir>/evidence``, sorted, capped."""
    root = spec_dir / "evidence"
    if not root.is_dir():
        return []
    names = []
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            name = path.relative_to(root).as_posix()
            if ".." in name.split("/") or not _PLAIN_PATH.fullmatch(name):
                continue
            names.append(name)
            if len(names) >= MAX_EVIDENCE:
                break
    except OSError as exc:  # a listing that fails is an empty listing
        logger.debug("could not list %s: %s", root, exc)
    return names


def _pull_requests(state: Any) -> List[Dict[str, str]]:
    """Each delivering pull request whose ref parses, its URL derived from it."""
    from .sessions import WorkItemRef

    rows = []
    for pr in getattr(state, "pull_requests", None) or []:
        try:
            ref = WorkItemRef.parse(str(pr.ref))
        except ValueError:
            continue
        state_text = str(pr.state or "")
        rows.append(
            {
                "ref": ref.ref,
                "url": ref.url,
                "state": state_text
                if state_text in ("open", "merged", "closed")
                else "",
            }
        )
    return rows


def terminal_record(rt: Any, item_id: str) -> Optional[Dict[str, Any]]:
    """What ``rt``'s state file says about how ``item_id`` ended, or ``None``.

    ``None`` when there is no state file — a ticket that closed before it was
    ever armed has no walk to record. A read only: nothing is written, and the
    caller decides where the copy goes.
    """
    from .graph.runtime import NOT_SELECTED
    from .graph.state import WorkItemState

    item = rt.work_item(item_id)
    state_dir = rt.state_dir(item)
    if WorkItemState.existing_path(state_dir) is None:
        return None
    state = WorkItemState.load(state_dir, item_id)
    graph = rt.graph
    node = state.current_node if state.current_node in graph.nodes else ""
    completion = _completion_node(graph)
    claimed = state.nodes.get(completion.id) if completion is not None else None
    completed = bool(claimed is not None and claimed.outcome)
    skips = rt.declared_skips(state)
    return {
        "workItem": item_id,
        "loop": graph.name,
        "node": node,
        "phase": _plain(state.phase),
        "completed": completed,
        "completedAt": str(claimed.exited_at or "") if claimed and completed else "",
        "selections": {
            "skipped": [
                n
                for n in (n.id for n in graph.ordered())
                if n in skips and skips[n].get("via") != NOT_SELECTED
            ],
            "optedIn": [n.id for n in graph.ordered() if rt.selected(state, n.id)],
            "surface": _plain(state.surface),
            "harness": _plain(state.harness),
            "model": _plain(state.model),
            "effort": _plain(state.effort),
            "sessionPerPr": _plain(state.session_per_pr),
            "repos": [r for r in (_plain(r) for r in state.repos) if r],
        },
        "pullRequests": _pull_requests(state),
        "specDir": f"{rt.spec_root}/{item_id}",
        "evidence": _evidence(item.spec_dir),
        "recordedAt": _utcnow(),
    }


def cancelled(event: str, payload: Mapping[str, Any], reason: str) -> bool:
    """Whether a closure is an explicit cancellation.

    An issue closed **as not planned** (the provider's ``state_reason``), or a
    pull request — a work item in its own right for `the-loop review` and
    `the-loop contribute` — closed without merging. Anything else, an issue
    closed as completed included, is not a cancellation; whether it is a
    *completion* is the terminal record's to say, not the closure's.
    """
    if event == "issues":
        issue = payload.get("issue") if isinstance(payload, Mapping) else None
        return isinstance(issue, Mapping) and issue.get("state_reason") == "not_planned"
    return reason == "pr-closed"


def closure_outcome(terminal: Optional[Mapping[str, Any]], is_cancelled: bool) -> str:
    """``completed`` | ``cancelled`` | ``closed-externally`` | ``unknown``.

    Completion comes first and only from the record: a work item whose session
    claimed its completion node completed, however the ticket was then closed.
    Without a record nothing can be said about completion, so the answer is
    ``unknown`` unless the closure itself was a cancellation.
    """
    if isinstance(terminal, Mapping) and terminal.get("completed") is True:
        return COMPLETED
    if is_cancelled:
        return CANCELLED
    return CLOSED_EXTERNALLY if isinstance(terminal, Mapping) else UNKNOWN


def ended_for(ref: str, config: Optional[Mapping[str, Any]] = None) -> Optional[Dict]:
    """The ``ended`` stamp the portable record holds for ``ref``, or ``None``.

    The portable directory comes from the CLI config (``state.root``), the same
    one the daemon writes — read best-effort, so a machine with no config, no
    directory or no record simply has no archive. Only a mapping counts, as in
    :meth:`the_loop.control.ControlStore.ended`.
    """
    from .graph.bootstrap import load_cli_config_best_effort
    from .state import layout_from_config
    from .workitem import ENDED, WorkItemStore

    try:
        loaded = dict(config) if config is not None else load_cli_config_best_effort()
        portable = Path(layout_from_config(loaded).portable_dir)
        if not portable.is_dir():
            return None
        section = WorkItemStore(portable).section(ref, ENDED)
    except Exception as exc:  # noqa: BLE001 — a record we cannot read is "no archive"
        logger.debug("could not read the portable record for %s: %s", ref, exc)
        return None
    return dict(section) if isinstance(section, Mapping) else None


def archived_report(
    work_item: str, ref: str, stamp: Mapping[str, Any], state_path: str
) -> Dict[str, Any]:
    """The ``check`` answer for an archived work item.

    The keys of a live report, so every reader keeps working, plus ``archived``.
    **No node findings**: there is nothing to evaluate them against — the caller's
    directory is not the work item's checkout, and saying "BLOCK requirements.md"
    about a phase the item never selected was the bug. ``ok`` is true only for a
    completed item.
    """
    terminal = stamp.get("terminal")
    terminal = dict(terminal) if isinstance(terminal, Mapping) else None
    outcome = str(stamp.get("outcome") or "")
    if outcome not in OUTCOMES:
        outcome = closure_outcome(terminal, False) if terminal is not None else UNKNOWN
    node = str(terminal.get("node") or "") if terminal is not None else ""
    archived: Dict[str, Any] = {
        "ref": ref,
        "outcome": outcome,
        "detail": RECORDED if terminal is not None else UNAVAILABLE,
        "state": str(stamp.get("state") or ""),
        "reason": str(stamp.get("reason") or ""),
        "at": str(stamp.get("at") or ""),
        "actor": str(stamp.get("actor") or ""),
    }
    if terminal is not None:
        archived["terminal"] = terminal
    return {
        "workItem": work_item,
        "currentNode": node,
        "ok": outcome == COMPLETED,
        "parked": None,
        "nodes": [],
        "statePath": state_path,
        "stateFound": False,
        "pointer": node,
        "archived": archived,
    }
