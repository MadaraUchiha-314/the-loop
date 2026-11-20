"""Core capability: may this session's turn end? (issue-551, Requirement 3).

The harness's Stop hook stays a clock. It asks here, because the answer needs
what only the service's side holds together: the graph's recomputed verdicts,
the node owners from the graph definition, and the event log's asks and waits.

:func:`decide` is the whole rule and is pure: it reads no file, no clock and no
registry. :func:`stop_check` gathers its four inputs for one work item, records
``session.turn_ended`` on every allow and records nothing on a refusal.

Every operation here answers only for a work item that has a live session in
the session registry (design § Security design). The service authenticates no
caller (decision-059), so that is what "bound" can mean on this side; the CLI
verbs add the caller's own ``THE_LOOP_WORK_ITEM`` before they call.

Spec: docs/specs/issue-551/design.md § "The stop check".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

from .. import cli_config, eventlog, prompts, strings
from ..graph.model import slash_command
from ..sessions.registry import Session, SessionRegistry
from ..state import layout_from_config
from ..watchconfig import AsksConfig, WatchdogConfig
from ..workitem import WorkItemRef
from . import graphs as core_graphs
from . import sessions as core_sessions
from . import sessionstate
from .sessionstate import SessionState

logger = logging.getLogger("the-loop.core.stopcheck")

__all__ = [
    "ALLOW",
    "MAX_CONDITION_LENGTH",
    "REFUSE",
    "Decision",
    "check_condition",
    "decide",
    "declare_wait",
    "stop_check",
    "turn_start",
]

ALLOW = "allow"
REFUSE = "refuse"

#: What a refusal's `reason` says. An allow's reason is one of the closed list a
#: turn's end records (design § Events).
WORK_OWED = "work-owed"

#: The longest condition a declared wait may state. It is shown on the status
#: surfaces and in channels (design § Security design).
MAX_CONDITION_LENGTH = 200


@dataclass(frozen=True)
class Decision:
    verdict: str
    reason: str
    #: On an allow, the pointer's node. On a refusal, the node that owes work,
    #: which is a node before the pointer when one of those blocks.
    node: str = ""
    node_status: str = ""
    #: A refusal's unmet checks, as the report words them.
    messages: Tuple[str, ...] = ()


def decide(
    report: Optional[Mapping[str, Any]],
    nodes: Mapping[str, Mapping[str, Any]],
    session: SessionState,
    background_work: bool,
) -> Decision:
    """The stop check's rule, in the design's order.

    ``report`` is the recomputed check report (``the-loop check --recompute``).
    ``nodes`` maps each node id to its ``actor`` and ``terminal`` from the graph
    definition. ``background_work`` is what the harness's own payload reports.
    """
    reported: Dict[str, Mapping[str, Any]] = {
        str(entry.get("node") or ""): entry
        for entry in ((report or {}).get("nodes") or [])
        if isinstance(entry, Mapping)
    }
    at = str((report or {}).get("pointer") or "")
    # 1. A check that cannot say where the item is must not invent a debt (R3.7).
    if not at or at not in reported or at not in nodes:
        return Decision(ALLOW, "inconclusive")
    status = str(reported[at].get("status") or "")
    # 2. Nobody owes agent work here.
    if nodes[at].get("actor") == "human":
        return Decision(ALLOW, "human-gate", at, status)
    if nodes[at].get("terminal") or nodes[at].get("actor") != "agent":
        return Decision(ALLOW, "complete", at, status)
    # 3. A pointer moved forward hides nothing behind it (issue-429). A human
    # gate behind it was answered, or the pointer would not be past it, and an
    # answered gate recomputes as `wait`: it counts as passed (R3.3).
    for node_id, entry in reported.items():
        if node_id == at:
            break
        owner = (nodes.get(node_id) or {}).get("actor")
        if owner == "agent" and entry.get("status") == "block":
            return _refusal(node_id, entry)
    # 4, 5. The node is done, or the graph itself says it waits.
    if status in ("pass", "skip"):
        return Decision(ALLOW, "exit-met", at, status)
    if status == "wait":
        return Decision(ALLOW, "graph-wait", at, status)
    if status != "block":
        return Decision(ALLOW, "inconclusive", at, status)
    # 6. Work is owed. Only something the session really waits on excuses it.
    if session.open_ask is not None:
        return Decision(ALLOW, "open-ask", at, status)
    if session.declared_wait is not None and session.declared_wait.covers_stop:
        return Decision(ALLOW, "declared-wait", at, status)
    if background_work:
        return Decision(ALLOW, "background-work", at, status)
    return _refusal(at, reported[at])


def _refusal(node_id: str, entry: Mapping[str, Any]) -> Decision:
    return Decision(
        REFUSE,
        WORK_OWED,
        node_id,
        str(entry.get("status") or ""),
        tuple(str(message) for message in entry.get("messages") or []),
    )


# -- gathering ------------------------------------------------------------------


def _bound(
    ref: str, config: Optional[dict], registry_dir: str = ""
) -> Tuple[WorkItemRef, Session]:
    """The work item and its live session, or ``LookupError``.

    The one check every operation here makes before it reads or records
    anything. ``ValueError`` for a malformed ref.
    """
    work_item = WorkItemRef.parse(ref)
    registry = SessionRegistry(core_sessions._registry_dir(config, registry_dir))
    session = registry.session_for(work_item)
    if session is None:
        raise LookupError(strings.t("core.stopcheck.not-bound", ref=work_item.ref))
    return work_item, session


def _standing(
    session: Session, work_item: WorkItemRef
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    """The recomputed report and the node facts, from the session's checkout.

    ``(None, {})`` when they cannot be read: the gate's fail-open case is kept
    on purpose (R3.7), and is recorded as `inconclusive`.
    """
    try:
        return core_graphs.stop_report(session.cwd, work_item.ref)
    except Exception as exc:  # noqa: BLE001 — a gate that cannot tell allows
        logger.debug("cannot read where %s stands: %s", work_item.ref, exc)
        return None, {}


def _pointer(session: Session, work_item: WorkItemRef) -> Dict[str, Any]:
    """The node the work item's pointer is on, with its owner; ``{}`` when it
    cannot be read."""
    try:
        return core_graphs.pointer(session.cwd, work_item.ref)
    except Exception as exc:  # noqa: BLE001 — a position that cannot be read is none
        logger.debug("cannot read the pointer of %s: %s", work_item.ref, exc)
        return {}


def _session_state(
    work_item: WorkItemRef, config: Optional[dict], now: Optional[datetime] = None
) -> SessionState:
    data = config or cli_config.load_cli_config(cli_config.default_cli_config_path())
    # The file `eventlog.configure_from_file` writes to, so the wait a session
    # declared a moment ago is the wait this reads.
    log_path = (data.get("eventLog") or {}).get("path") or layout_from_config(
        data
    ).event_log
    routing = core_sessions._routing(config)
    return sessionstate.derive(
        sessionstate.load(log_path).get(work_item.ref, []),
        now=now or datetime.now(timezone.utc),
        watchdog=WatchdogConfig.from_mapping(routing.get("watchdog") or {}),
        asks=AsksConfig.from_mapping(routing.get("asks") or {}),
        work_item=work_item.ref,
    )


def _resume_command(node: Mapping[str, Any], work_item: WorkItemRef) -> str:
    """How a session resumes ``node``, as the assignment words it; ``""`` for a
    node that names no command."""
    if not node.get("command"):
        return ""
    item_id = core_graphs.work_item_id(work_item.ref)
    return f"{slash_command(str(node['command']))} {item_id}"


def _refusal_text(decision: Decision, command: str, work_item: WorkItemRef) -> str:
    """What the harness hands back to the session (R3.5): fixed prompt files, with
    the node, its unmet checks, the command and the work item's own ref."""
    lines = [prompts.render("stopcheck/refusal", inline=True, node=decision.node)]
    lines += [
        prompts.render("stopcheck/check", inline=True, message=message)
        for message in decision.messages
    ]
    if command:
        lines.append(prompts.render("stopcheck/resume", inline=True, command=command))
    lines.append(prompts.render("stopcheck/ways-out", inline=True, ref=work_item.ref))
    return "\n".join(lines)


# -- the operation ----------------------------------------------------------------


def stop_check(
    ref: str,
    config: Optional[dict] = None,
    background_work: bool = False,
    gave_up: bool = False,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Decide whether ``ref``'s session may end its turn, and record an allow.

    ``gave_up`` records a stop the hook already allowed after its own attempts
    ran out (R3.6): nothing is judged. ``LookupError`` when no live session is
    registered for ``ref``; then nothing is read and nothing is recorded.
    """
    work_item, session = _bound(ref, config, registry_dir)
    report, nodes = _standing(session, work_item)
    decision = decide(
        report, nodes, _session_state(work_item, config), bool(background_work)
    )
    if gave_up:
        at = (report or {}).get("pointer")
        entry = next(
            (n for n in (report or {}).get("nodes") or [] if n.get("node") == at), None
        )
        decision = (
            Decision(ALLOW, "gate-gave-up", str(at), str(entry.get("status") or ""))
            if at and entry is not None
            else Decision(ALLOW, "gate-gave-up")
        )
    answer: Dict[str, Any] = {
        "workItem": work_item.ref,
        "verdict": decision.verdict,
        "reason": decision.reason,
        "node": decision.node,
        "nodeStatus": decision.node_status,
    }
    if decision.verdict == ALLOW:
        eventlog.emit(
            "session.turn_ended",
            work_item=work_item.ref,
            node=decision.node or None,
            node_status=decision.node_status or None,
            reason=decision.reason,
        )
        return answer
    command = _resume_command(nodes.get(decision.node) or {}, work_item)
    answer.update(
        messages=list(decision.messages),
        command=command,
        text=_refusal_text(decision, command, work_item),
    )
    return answer


def turn_start(
    ref: str, config: Optional[dict] = None, registry_dir: str = ""
) -> Dict[str, Any]:
    """Record that ``ref``'s session started a turn (R4.5, R4.6).

    While this is the session's last turn record it is `working`, and it is the
    one record that ends a stall. ``LookupError`` when no live session is
    registered for ``ref``; then nothing is recorded.
    """
    work_item, session = _bound(ref, config, registry_dir)
    node = str(_pointer(session, work_item).get("node") or "")
    eventlog.emit("session.turn_started", work_item=work_item.ref, node=node or None)
    return {"workItem": work_item.ref, "node": node}


def check_condition(condition: str) -> str:
    """A declared wait's condition, stripped; ``ValueError`` when it is empty or
    longer than :data:`MAX_CONDITION_LENGTH`."""
    text = condition.strip() if isinstance(condition, str) else ""
    if not text:
        raise ValueError(strings.t("core.stopcheck.wait.empty-condition"))
    if len(text) > MAX_CONDITION_LENGTH:
        raise ValueError(
            strings.t(
                "core.stopcheck.wait.condition-too-long",
                length=len(text),
                limit=MAX_CONDITION_LENGTH,
            )
        )
    return text


def declare_wait(
    ref: str,
    condition: str,
    seconds: int,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Record what ``ref``'s session waits for, and for how long (R4.7).

    The wait covers one stop, the one that ends the turn it is made in; the
    derivation enforces that, not this record. ``ValueError`` for an empty or
    over-long condition, a time over ``routing.watchdog.maxWaitSeconds``, and a
    pointer on a human-owned node: a person's answer is asked for with
    `the-loop ask`, and no session puts a clock on it. ``LookupError`` when no
    live session is registered for ``ref``. A refusal records nothing.
    """
    work_item, session = _bound(ref, config, registry_dir)
    condition = check_condition(condition)
    routing = core_sessions._routing(config)
    limit = WatchdogConfig.from_mapping(routing.get("watchdog") or {}).max_wait_seconds
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 1:
        raise ValueError(strings.t("core.stopcheck.wait.not-positive"))
    if seconds > limit:
        raise ValueError(
            strings.t("core.stopcheck.wait.over-limit", seconds=seconds, limit=limit)
        )
    at = _pointer(session, work_item)
    if at.get("actor") == "human":
        raise ValueError(strings.t("core.stopcheck.wait.human-node", node=at["node"]))
    # The event log's own timestamp form, which the derivation parses back.
    until = sessionstate._stamp(datetime.now(timezone.utc) + timedelta(seconds=seconds))
    eventlog.emit(
        "session.wait_declared",
        work_item=work_item.ref,
        condition=condition,
        until=until,
    )
    return {
        "workItem": work_item.ref,
        "condition": condition,
        "until": until,
        "exitCode": 0,
        "messages": [
            {
                "stream": "out",
                "text": strings.t(
                    "core.stopcheck.wait.declared", condition=condition, until=until
                ),
            },
            {"stream": "out", "text": strings.t("core.stopcheck.wait.covers-one-stop")},
        ],
    }
