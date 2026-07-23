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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, Optional, Sequence, Union

from . import cli_config

logger = logging.getLogger("the-loop.eventlog")

DEFAULT_PATH = ".the-loop/logs/events.jsonl"

LEVELS = ("debug", "info", "warning", "error")

# The catalog of event types the-loop emits — the single source of truth used
# by `the-loop events --types` and mirrored in the observability reference.
# Adding an instrumentation point means adding its type (and description) here.
EVENT_TYPES: Dict[str, str] = {
    # -- webhook receiver (source: gh-webhook) --------------------------------
    "webhook.received": (
        "An inbound webhook POST was accepted for routing "
        "(gh_event, delivery_id, verified: HMAC signature checked)."
    ),
    "webhook.rejected": (
        "An inbound webhook POST was refused before routing "
        "(reason: invalid-signature | invalid-payload)."
    ),
    # -- routing (source: gh-webhook or poll) ---------------------------------
    "routing.routed": (
        "A verified event mapped to work item(s) and passed all guards "
        "(gh_event, work_items, labeled)."
    ),
    "routing.dropped": (
        "A verified event was not routed (reason: disabled-event | "
        "duplicate-delivery | no-work-item | unauthorized-actor; actor)."
    ),
    # -- dispatch (source: gh-webhook or poll) --------------------------------
    "dispatch.queued": (
        "A routed event was enqueued on a session's FIFO queue "
        "(work_item, spawn: whether it will spawn a new session)."
    ),
    "dispatch.dropped": (
        "A routed event was discarded at dispatch (reason: duplicate-delivery "
        "| already-processed | spawn-policy | session-vanished | no-adapter)."
    ),
    "dispatch.succeeded": (
        "An event was delivered to its harness session (work_item, harness, "
        "via: resume | tmux)."
    ),
    "dispatch.failed": (
        "Delivering an event to its session failed (work_item, harness, "
        "error; will_retry: the delivery id was released so a redelivery / "
        "next poll cycle can retry)."
    ),
    "dispatch.error": (
        "A dispatch worker crashed on an event (work_item, error; will_retry)."
    ),
    # -- session lifecycle (source: any) --------------------------------------
    "session.registered": (
        "A work item ↔ harness session link was recorded in the registry "
        "(work_item, harness, harness_session_id, runner, cwd)."
    ),
    "session.spawned": (
        "A new harness session was spawned for a work item — this is the "
        "'what triggered this session' record (work_item, harness, "
        "harness_session_id, runner, gh_event, delivery_id)."
    ),
    "session.spawn_failed": (
        "Spawning a session failed (work_item, harness, error; will_retry)."
    ),
    "session.closed": "A session was closed in the registry (work_item).",
    "session.autoclosed": (
        "A session was auto-closed because its PR was merged/closed "
        "(work_item, merged)."
    ),
    "workspace.prepared": (
        "A repo was cloned (if needed) and a per-work-item git worktree made "
        "ready for a spawned session (work_item, repo_dir, worktree, branch)."
    ),
    "workspace.cleaned": (
        "A work item's git worktree was removed after its PR merged/closed (work_item)."
    ),
    # -- poller (source: poll) ------------------------------------------------
    "poll.cycle": (
        "One poll cycle finished (items_seen, spawns, comments_forwarded, errors)."
    ),
    "poll.provider_error": (
        "Asking a provider for its work items failed; retried next cycle "
        "(provider, error, will_retry)."
    ),
    "poll.item_error": (
        "Processing one polled work item failed; retried next cycle "
        "(work_item, error, will_retry)."
    ),
    "poll.unauthorized": (
        "A polled item was ignored because its author is not an authorized "
        "user (work_item, actor)."
    ),
    "poll.comment_forwarded": (
        "A new authorized comment was forwarded to the item's session "
        "(work_item, comment_id, actor)."
    ),
    # -- process lifecycle (source: gh-webhook or poll) -----------------------
    "server.started": "The webhook receiver started (host, port, path, routing).",
    "server.stopped": "The webhook receiver shut down.",
    "poller.started": "The poller started (interval_seconds, sources).",
    "poller.stopped": "The poller shut down.",
    "config.reloaded": (
        "A config edit was hot-reloaded into a running process (detail)."
    ),
}


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

    def emit(self, event: str, level: str = "info", **fields) -> None:
        """Append one event record. Unknown ``event`` types are still logged
        (forward compatibility), but instrumentation should register them in
        :data:`EVENT_TYPES`."""
        if not self.enabled:
            return
        record = {
            "ts": _utcnow(),
            "source": self.source,
            "event": event,
            "level": level if level in LEVELS else "info",
            "pid": os.getpid(),
        }
        record.update({k: v for k, v in fields.items() if v is not None})
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
    """:func:`configure` from ``eventLog`` in the CLI config."""
    cfg = load_config()
    return configure(
        source,
        path=str(cfg.get("path", DEFAULT_PATH)),
        enabled=bool(cfg.get("enabled", True)),
    )


def load_config(config_path: Optional[Union[str, Path]] = None) -> dict:
    """Best-effort read of ``eventLog`` from the CLI config (``{}`` without PyYAML).

    Defaults to the CLI config's resolved path (``cli_config.default_cli_config_path()``
    — ``--config``, then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/cli-config.yaml``,
    then ``~/.the-loop/cli-config.yaml``, decision-032). ``eventLog`` is top-level in the
    CLI config, unlike the PLUGIN config's
    ``observability.devLevel``/``runtimeLevel``/``browserLogging``.
    """
    path = (
        Path(config_path)
        if config_path is not None
        else cli_config.default_cli_config_path()
    )
    if not path.is_file():
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001 - a broken config must not break ingress
        return {}
    return data.get("eventLog") or {}


def emit(event: str, level: str = "info", **fields) -> None:
    """Emit through the configured log; silently a no-op when unconfigured."""
    if _log is not None:
        _log.emit(event, level=level, **fields)


def reset() -> None:
    """Deconfigure the module-level log (tests)."""
    global _log
    _log = None


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
