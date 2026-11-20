"""Structured JSONL event log — end-to-end o11y of the-loop's CLI processes.

Every accept/reject/dispatch/spawn/retry/close decision the webhook receiver,
the poller and the session registry make is appended as one JSON object per
line to a single machine-queryable file (default
``.the-loop/logs/events.jsonl``, git-ignored). The file is the system's audit
trail: it answers "which events triggered this session?", "what was rejected,
and why?", and "what failed, and was it retried?" — for humans (``the-loop
events``, grep/jq) and for coding agents alike. JSONL over SQLite is
decision-025: append-only writes are atomic and multi-process-safe, the file
is directly greppable, and any dashboard/DB can be layered on top.

Every record shares one envelope::

    {"ts": "2026-07-22T06:31:20.123Z",  # UTC, ISO-8601, millisecond precision
     "source": "gh-webhook",            # emitting process: gh-webhook|poll|sessions
     "event": "dispatch.succeeded",     # dot-namespaced type (see EVENT_TYPES)
     "level": "info",                   # debug|info|warning|error
     "pid": 4242,                       # emitting process id
     ...}                               # event-specific fields, all optional

Common event-specific fields: ``work_item`` (``github:owner/repo#15``) /
``work_items``, ``delivery_id`` (GitHub ``X-GitHub-Delivery``), ``gh_event``
(+ ``action``), ``actor``, ``harness``, ``harness_session_id``, ``reason``
(why something was rejected/dropped), ``error`` and ``will_retry`` (failure
paths). The full catalog lives in :data:`EVENT_TYPES` (also ``the-loop events
--types``) and ``skills/the-loop/reference/observability.md``.

Emission is fire-and-forget: a broken log file must never break ingress, so
write failures are warned about once and swallowed. Library code calls the
module-level :func:`emit`, which is a no-op until a CLI entry point calls
:func:`configure` — pure unit tests and embedders pay zero I/O.

Spec: docs/specs/issue-50/design.md; decision-025.
"""

from __future__ import annotations

import fnmatch
import json
import logging
import os
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence, Tuple, Union

import yaml

from . import cli_config, strings

logger = logging.getLogger("the-loop.eventlog")

DEFAULT_PATH = ".the-loop/logs/events.jsonl"

LEVELS = ("debug", "info", "warning", "error")

# The catalog of event types the-loop emits — the single source of truth used
# by `the-loop events --types` and mirrored in the observability reference.
# Adding an instrumentation point means adding its type here and its description
# to strings/en.json under ``eventlog.event-type.<type>``.
_EVENT_TYPE_TEXT: Dict[str, str] = strings.section("eventlog.event-type")
_EVENT_NAMES: Tuple[str, ...] = (
    "session.identity_bound",
    "poll.item_filtered",
    "session.default_harness_bypassed",
    # -- lifecycle hooks (issue-344; source: whichever process ran the chain) ---
    "hooks.loaded",
    "hooks.load_failed",
    "hooks.decided",
    "hooks.failed",
    "hooks.refused",
    # -- webhook receiver (source: gh-webhook) --------------------------------
    "webhook.received",
    "webhook.rejected",
    # -- routing (source: gh-webhook or poll) ---------------------------------
    "routing.routed",
    "routing.dropped",
    "routing.collaborator",
    "routing.linkage_dropped",
    # -- dispatch (source: gh-webhook or poll) --------------------------------
    "dispatch.queued",
    "dispatch.quiz_gate",
    "dispatch.dropped",
    "ci.check_failed",
    "ci.autofix_exhausted",
    "dispatch.succeeded",
    "dispatch.attachments",
    "dispatch.failed",
    "dispatch.error",
    "dispatch.abandoned",
    "reaction.added",
    "reaction.failed",
    # -- execution control (source: any; issue-106) ---------------------------
    "control.command",
    "control.rejected",
    "control.ambiguous",
    # A control comment is CONSUMED, never delivered — so on the poll path its
    # delivery is settled rather than counted as an attempt (issue-270). That
    # applies to two outcomes above: applied (`control.command`) and refused
    # (`control.rejected`). An ambiguous one (`control.ambiguous`) is routed as
    # conversation instead (issue-498).
    "control.announced",
    "control.announce_failed",
    # -- session lifecycle (source: any) --------------------------------------
    "session.registered",
    "session.pr_linked",
    "session.pr_spawned",
    "session.pr_session_declined",
    "session.pr_closed",
    "session.link_failed",
    "graph.assignment_delivered",
    "graph.assignment_failed",
    "session.spawned",
    "session.spawn_failed",
    "session.choice_changed",
    "session.choice_refused",
    "session.spawn_deferred",
    "session.respawned",
    "session.respawn_averted",
    "session.resume_failed",
    "session.restarted",
    "session.credentials_inherited",
    "session.restart_failed",
    "session.announced",
    "session.work_item_missing",
    "session.announce_failed",
    "session.awaiting_input",
    "session.reply_sent",
    # -- turns, waits, stalls and ask deadlines (issue-551; source: the session's
    #    hooks and verbs, the dispatcher, and the control-plane service's watcher)
    "session.turn_started",
    "session.turn_ended",
    "session.wait_declared",
    "session.nudged",
    "session.stalled",
    "session.stall_ended",
    "session.ask_default_taken",
    "session.ask_reminded",
    "session.ask_answered",
    # -- channels (source: ask | channels | poll | gh-webhook) ----------------
    "channel.posted",
    "channel.post_failed",
    "channel.undelivered",
    "channel.posting_unavailable",
    "channel.delivered_late",
    "channel.undelivered_dropped",
    "channel.reply_received",
    "channel.dropped",
    "channel.caught_up",
    "channel.heartbeat",
    "channels.short_form_missing",
    "channel.split_suspected",
    "channel.split_cleared",
    "channel.command_received",
    "channel.command_completed",
    "channel.command_answer_failed",
    "channel.attachments",
    "channel.mirrored",
    "channel.mirror_skipped",
    "channel.mirror_failed",
    "channel.kickoff_asked",
    "channel.created",
    "channel.thread_opened",
    "channel.open_failed",
    "channel.reaction_added",
    "channel.reaction_failed",
    "channel.press_reported",
    "channel.gate_closed",
    "channel.press_report_failed",
    # -- mention-gated rooms, records and shortcuts (issue-389) ---------------
    "channel.context_recorded",
    "channel.decision_recorded",
    "channel.snapshot_empty",
    "channel.shortcut_received",
    "channel.shortcut_failed",
    "channel.view_submitted",
    # -- the bus (issue-309, decision-103) --------------------------------------
    "bus.published",
    "bus.recorded",
    "bus.record_failed",
    "standing.started",
    "standing.resumed",
    "standing.resume_failed",
    "standing.spawn_failed",
    "standing.created",
    "standing.create_failed",
    "standing.deleted",
    "standing.stopped",
    "standing.stop_failed",
    "standing.said",
    "standing.announced",
    "standing.announce_failed",
    "session.closed",
    "session.paused",
    "session.resumed",
    "session.retained",
    "session.autoclosed",
    "session.closing",
    "session.closing_cancelled",
    "session.pr_notice_delivered",
    "session.pr_notice_skipped",
    "session.pr_notice_failed",
    "graph.outer_reevaluated",
    "session.kept_open",
    "session.reset",
    "session.cleaned",
    "work_item.ended",
    "work_item.pull_request_ended",
    "work_item.reopened",
    # -- the harness's GitHub verbs (issue-447) --------------------------------
    "work_item.commented",
    "work_item.pr_opened",
    "work_item.pr_labelled",
    "work_item.pr_merged",
    "work_item.pr_ready",
    "work_item.ticket_closed",
    "work_item.thread_resolved",
    "work_item.merge_refused",
    "cleanup.deferred",
    "session.harness_terminated",
    # -- the handoff pick-up (issue-517; source: the dispatcher's arming path) ---
    "handoff.honoured",
    "handoff.ignored",
    "handoff.unreadable",
    "handoff.imported",
    "handoff.demoted",
    "arm.refused",
    "workspace.prepared",
    "workspace.cleaned",
    "workspace.trusted",
    "workspace.trust_failed",
    # -- poller (source: poll) ------------------------------------------------
    "poll.cycle",
    "poll.closure_detected",
    "poll.provider_error",
    "poll.item_error",
    "poll.scope_error",
    "poll.scope_degraded",
    "poll.scope_recovered",
    "poll.unauthorized",
    "poll.comment_forwarded",
    "poll.spawn_failed",
    "poll.rearmed",
    "poll.attempts_released",
    "poll.comment_settled",
    "poll.comment_failed",
    "poll.giveup_reported",
    "poll.giveup_report_failed",
    # -- process lifecycle (source: gh-webhook or poll) -----------------------
    "server.started",
    "server.stopped",
    "poller.started",
    "poller.stopped",
    "poller.blocked",
    "config.reloaded",
    # -- process graph (source: any; issue-109) -------------------------------
    "graph.started",
    "graph.advanced",
    "graph.blocked",
    "graph.parked",
    "graph.escalated",
    "graph.no_edge",
    "graph.hook_degraded",
    "graph.quiz_refused",
    "graph.completed",
    "graph.cleaned",
    "graph.spec_tree_excluded",
    "graph.skipped",
    "graph.link_failed",
    "graph.forced",
    "graph.repos_declared",
    # -- declared skips (issue-177) --------------------------------------------
    "graph.skips_declared",
    "graph.opt_ins_selected",
    "graph.skips_rejected",
    "graph.pull_request_linked",
    "graph.node_skipped",
    "graph.gate_session",
    # `the-loop graph pr-spec` recorded, or refused, a PR spec (issue-543)
    "graph.pr_spec_recorded",
    "graph.pr_spec_refused",
    # -- control-plane API service (source: service) — issue-161 --------------
    "api.request",
    "mcp.call",
    "config.updated",
    # -- the fleet a manager serves (source: service) — issue-374 --------------
    "instance.registered",
    "instance.unregistered",
    "instance.unreachable",
    "instance.recovered",
    "instance.mismatched",
    "instance.malformed",
    "aggregate.partial",
    # -- the server-push stream (source: service) — issue-239 ------------------
    "stream.subscribed",
    "stream.refused",
    "stream.desync",
    "stream.disconnected",
    "service.started",
    "service.stopped",
    "restart.scheduled",
    "restart.completed",
    "ingress.hosted",
    "ingress.hosted_failed",
    "ingress.hosted_stopped",
    "diagnosis.detected",
    "diagnosis.posted",
    "diagnosis.deferred",
    "diagnosis.failed",
    # -- the gateway (issue-496; source: gateway, or the instance's client) -------------
    "gateway.started",
    "gateway.stopped",
    "gateway.received",
    "gateway.dropped",
    "gateway.slack_call",
    "gateway.slack_download",
    "gateway.refused",
    "gateway.reloaded",
    "config.reload-failed",
    "gateway.claimed",
    "gateway.released",
    "gateway.bound",
    "gateway.rooms",
    "gateway.registered",
    "gateway.unreachable",
    "gateway.connected",
    "subject.appended",
    "subject.routed",
    "subject.committed",
    "subject.redelivered",
    "subject.dead-lettered",
    "subject.expired",
)

#: Each event type's description, in the catalog's order (issue-540: the prose is
#: in ``strings/en.json``; the names stay here).
EVENT_TYPES: Dict[str, str] = {name: _EVENT_TYPE_TEXT[name] for name in _EVENT_NAMES}


def _utcnow() -> str:
    return (
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[
            :-3
        ]  # microseconds -> milliseconds
        + "Z"
    )


class EventLog:
    """Append-only JSONL writer. Thread-safe; write failures never propagate.

    Each :meth:`emit` appends one ``\\n``-terminated JSON line via an
    ``O_APPEND`` write, so concurrently running processes (receiver + poller +
    sessions CLI) interleave whole lines, never corrupt each other.
    """

    def __init__(
        self, path: Union[str, Path] = DEFAULT_PATH, source: str = "", enabled=True
    ):
        self.path = Path(path)
        self.source = source
        self.enabled = enabled
        self._lock = threading.Lock()
        self._warned = False

    def emit(self, event: str, level: str = "info", **fields) -> bool:
        """Append one event record. Unknown ``event`` types are still logged
        (forward compatibility), but instrumentation should register them in
        :data:`EVENT_TYPES`.

        ``True`` when the record was appended; ``False`` when the log is
        disabled or the write failed. A caller whose next act must never
        happen without its record checks this before it acts."""
        if not self.enabled:
            return False
        record = {
            "ts": _utcnow(),
            "source": self.source,
            "event": event,
            "level": level if level in LEVELS else "info",
            "pid": os.getpid(),
        }
        extra = getattr(_context, "fields", None)
        if extra:
            record.update({k: v for k, v in extra.items() if v is not None})
        record.update({k: v for k, v in fields.items() if v is not None})
        delivery_id = record.get("delivery_id")
        if delivery_id is not None and _correlations:
            with _correlations_lock:
                tagged = _correlations.get(str(delivery_id))
            if tagged:
                for key, value in tagged.items():
                    record.setdefault(key, value)
        # A session credential value never reaches a log line (issue-533, R5.1): the
        # values this process has handed over or resolved, masked; free when none.
        from . import sessioncreds

        record = sessioncreds.scrub_tree(record)
        line = json.dumps(record, separators=(",", ":"), default=str) + "\n"
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line)
        except OSError as exc:
            if not self._warned:  # warn once — never break ingress over o11y
                self._warned = True
                logger.warning("cannot write event log %s: %s", self.path, exc)
            return False
        return True


# -- delivery correlation (issue-496, R10.2) -------------------------------------

#: ``delivery_id -> extra fields`` every record naming that delivery carries, whichever
#: thread emits it. The gateway client tags a delivery with its gateway event id before
#: handing it to the dispatcher, whose worker threads then record `dispatch.*` with
#: `gateway_event_id` beside the delivery id. Bounded: the oldest tag goes first.
_correlations: "OrderedDict[str, Dict]" = OrderedDict()
_correlations_lock = threading.Lock()
CORRELATION_CAP = 4096


def correlate(delivery_id: str, **fields) -> None:
    """Attach ``fields`` to every record that names ``delivery_id`` from now on."""
    if not delivery_id:
        return
    with _correlations_lock:
        _correlations[str(delivery_id)] = {
            k: v for k, v in fields.items() if v is not None
        }
        _correlations.move_to_end(str(delivery_id))
        while len(_correlations) > CORRELATION_CAP:
            _correlations.popitem(last=False)


def uncorrelate(delivery_id: str) -> None:
    with _correlations_lock:
        _correlations.pop(str(delivery_id), None)


# -- per-thread context fields (issue-496, R10.2) --------------------------------

_context = threading.local()


class context:
    """Fields every record emitted on this thread carries while the block is open.

    The gateway client wraps each delivery's dispatch in
    ``with eventlog.context(gateway_event_id=…):`` so the instance's ``dispatch.*``
    records name the gateway event beside the delivery id without every emit site
    learning a new argument. A field passed to :meth:`EventLog.emit` explicitly wins
    over the context's. Nested blocks merge, innermost winning.
    """

    def __init__(self, **fields) -> None:
        self._fields = fields
        self._previous: Optional[Dict] = None

    def __enter__(self) -> "context":
        self._previous = getattr(_context, "fields", None)
        merged = dict(self._previous or {})
        merged.update(self._fields)
        _context.fields = merged
        return self

    def __exit__(self, *exc) -> None:
        _context.fields = self._previous


# -- module-level emitter (a no-op until a CLI entry point configures it) -------

_log: Optional[EventLog] = None


def configure(
    source: str, path: Union[str, Path] = DEFAULT_PATH, enabled: bool = True
) -> EventLog:
    """Install the process-wide event log. Called once per CLI entry point."""
    global _log
    _log = EventLog(path=path, source=source, enabled=enabled)
    return _log


def configure_from_file(source: str) -> EventLog:
    """:func:`configure` from ``eventLog`` in the CLI config.

    An unset ``path`` resolves under ``state.root`` (issue-106) — the same
    ``<root>/logs/events.jsonl`` :data:`DEFAULT_PATH` names for the default root.
    """
    from .state import layout_from_config

    data = cli_config.load_cli_config(cli_config.default_cli_config_path())
    cfg = data.get("eventLog") or {}
    return configure(
        source,
        path=str(cfg.get("path") or layout_from_config(data).event_log),
        enabled=bool(cfg.get("enabled", True)),
    )


def load_config(config_path: Optional[Union[str, Path]] = None) -> dict:
    """Best-effort read of ``eventLog`` from the CLI config (``{}`` if unreadable).

    Defaults to the CLI config's resolved path (``cli_config.default_cli_config_path()``
    — ``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/cli-config.yaml``,
    then ``~/.the-loop/cli-config.yaml``, decision-032). ``eventLog`` is top-level in the
    CLI config; a project's log levels are its own logging configuration (issue-352
    removed the harness config's ``observability`` block).
    """
    path = (
        Path(config_path)
        if config_path is not None
        else cli_config.default_cli_config_path()
    )
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001 - a broken config must not break ingress
        return {}
    return data.get("eventLog") or {}


def current_path() -> Optional[Path]:
    """The file this process's records go to; ``None`` when no log is configured.

    For a reader that must see what this process just wrote (issue-551: the
    dispatcher asks whether the work item has an open ask)."""
    return _log.path if _log is not None and _log.enabled else None


def emit(event: str, level: str = "info", **fields) -> bool:
    """Emit through the configured log; silently a no-op when unconfigured.

    ``True`` only when the record was appended (:meth:`EventLog.emit`)."""
    if _log is None:
        return False
    return _log.emit(event, level=level, **fields)


def reset() -> None:
    """Deconfigure the module-level log and forget the delivery correlations (tests)."""
    global _log
    _log = None
    with _correlations_lock:
        _correlations.clear()


# -- reader ---------------------------------------------------------------------


def _matches_work_item(record: dict, ref: str) -> bool:
    if record.get("work_item") == ref:
        return True
    return ref in (record.get("work_items") or [])


def record_matches(
    record: dict,
    types: Sequence[str] = (),
    work_item: Optional[str] = None,
    delivery_id: Optional[str] = None,
    source: Optional[str] = None,
    min_level: Optional[str] = None,
    since: Optional[str] = None,
) -> bool:
    """Whether one parsed record passes the given filters.

    ``types`` are fnmatch patterns (``dispatch.*``); ``min_level`` is
    inclusive (``warning`` ⇒ warning + error); ``since`` is an ISO-8601 UTC
    timestamp compared lexicographically against ``ts``.
    """
    if types and not any(
        fnmatch.fnmatch(str(record.get("event", "")), t) for t in types
    ):
        return False
    if work_item and not _matches_work_item(record, work_item):
        return False
    if delivery_id and record.get("delivery_id") != delivery_id:
        return False
    if source and record.get("source") != source:
        return False
    if min_level in LEVELS:
        min_rank = LEVELS.index(str(min_level))
        level = record.get("level")
        if level not in LEVELS or LEVELS.index(str(level)) < min_rank:
            return False
    if since and str(record.get("ts", "")) < since:
        return False
    return True


def parse_lines(lines: Sequence[str], **filters) -> Iterator[dict]:
    """Parse JSONL lines into matching records, skipping corrupt/partial ones."""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record_matches(record, **filters):
            yield record


def read_events(path: Union[str, Path], **filters) -> Iterator[dict]:
    """Stream matching records from a JSONL event log, oldest first.

    Tolerates a missing file and corrupt/partial lines (skipped) so a log
    truncated mid-write or rotated externally still reads. Filters are those
    of :func:`record_matches`.
    """
    try:
        handle = open(path, "r", encoding="utf-8")
    except OSError:
        return
    with handle:
        yield from parse_lines(list(handle), **filters)
