"""One table of everything the-loop is tracking (issue-98).

The daemon already holds every fact an operator wants; they are just scattered
across three stores and never joined:

* the **session registry** (issue-15) — who is working what, on which runner;
* the **poller's ledger** (issue-80) — every work item the poller has *seen*,
  including ones it is tracking with no session yet (a spawn mid-retry, or one
  given up on) — the rows an operator looks for when "nothing is happening";
* the **tmux server** (issue-32) — whether a session's terminal is still alive,
  and the pids inside it;

plus the **pause ledger** (this package's ``pauses.py``).

This module is the join, kept free of argparse and of I/O policy so it can be
unit-tested directly: :func:`build_rows` produces :class:`Row` objects and
:func:`render_table` / :func:`render_detail` turn them into the plain,
column-aligned stdio the issue asked for (no TUI, nothing that needs colour to
be readable).

Spec: docs/specs/issue-98/design.md §5.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from .pauses import PauseStore
from .registry import Session, SessionRegistry, WorkItemRef

# Displayed statuses, in the order rows are grouped: live work first, then work
# an operator has parked, then what the poller sees but has no session for,
# then failures, then history.
STATUS_ACTIVE = "active"
STATUS_PAUSED = "paused"
STATUS_TRACKED = "tracked"
STATUS_SPAWN_FAILED = "spawn-failed"
STATUS_CLOSED = "closed"

STATUSES = (
    STATUS_ACTIVE,
    STATUS_PAUSED,
    STATUS_TRACKED,
    STATUS_SPAWN_FAILED,
    STATUS_CLOSED,
)
_STATUS_ORDER = {name: index for index, name in enumerate(STATUSES)}

# Columns wide enough to be useful, narrow enough to fit a terminal. The full
# value is always available in `--format json` and in `sessions show`.
_MAX_CELL = 36


def _elide(value: str, width: int = _MAX_CELL) -> str:
    if len(value) <= width:
        return value
    return value[: width - 1] + "…"


def work_item_url(ref: WorkItemRef) -> str:
    """The ticket URL for a ref, or ``""`` when the provider isn't GitHub.

    Derived, not stored: GitHub serves both issues and PRs from ``/issues/<n>``
    (a PR number redirects), so one shape covers both kinds without asking which
    it is.
    """
    if ref.provider != "github":
        return ""
    return f"https://github.com/{ref.owner}/{ref.repo}/issues/{ref.number}"


def pid_alive(pid: int) -> Optional[bool]:
    """Whether ``pid`` is still running; ``None`` when it cannot be determined."""
    if pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by someone else
    except OSError:
        return None
    return True


@dataclass
class Row:
    """One work item in the table — session facts joined with tracking facts."""

    ref: str
    url: str = ""
    status: str = STATUS_TRACKED
    harness: str = ""
    session_id: str = ""
    runner: str = ""
    host: str = ""  # "tmux:loop-…" | "process:1234" | ""
    host_live: Optional[bool] = None  # None = unknown (tmux absent, no pid)
    attach: str = ""  # ready-to-paste tmux attach command
    cwd: str = ""
    pr_ref: str = ""
    pr_url: str = ""
    pause_sources: List[str] = field(default_factory=list)
    pause_reason: str = ""
    paused_by: str = ""  # the login, when an authorized labeller paused it
    paused_at: str = ""
    created_at: str = ""
    last_event_at: str = ""
    tracked: bool = False  # present in the poller's ledger
    last_polled_at: str = ""
    spawn_attempts: int = 0
    spawn_gave_up: bool = False

    @property
    def sort_key(self) -> tuple:
        return (
            _STATUS_ORDER.get(self.status, len(STATUSES)),
            # Most recent activity first within a group.
            _invert(self.last_event_at or self.last_polled_at or self.created_at),
            self.ref,
        )

    @property
    def host_display(self) -> str:
        """``host`` plus a liveness marker: ``(live)`` / ``(dead)`` / ``(?)``."""
        if not self.host:
            return "-"
        mark = {True: "live", False: "dead", None: "?"}[self.host_live]
        return f"{self.host} ({mark})"

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "url": self.url,
            "status": self.status,
            "harness": self.harness,
            "sessionId": self.session_id,
            "runner": self.runner,
            "host": self.host,
            "hostLive": self.host_live,
            "attach": self.attach,
            "cwd": self.cwd,
            "pr": {"ref": self.pr_ref, "url": self.pr_url},
            "paused": bool(self.pause_sources),
            "pauseSources": list(self.pause_sources),
            "pauseReason": self.pause_reason,
            "pausedBy": self.paused_by,
            "pausedAt": self.paused_at,
            "createdAt": self.created_at,
            "lastEventAt": self.last_event_at,
            "tracked": self.tracked,
            "lastPolledAt": self.last_polled_at,
            "spawnAttempts": self.spawn_attempts,
            "spawnGaveUp": self.spawn_gave_up,
        }


def _invert(stamp: str) -> str:
    """Sort ISO-8601 stamps newest-first without a datetime round-trip."""
    return "".join(
        chr(0x10FFFF - ord(ch)) if ord(ch) < 0x10FFFF else ch for ch in stamp
    )


class _NullTmux:
    """Stand-in when tmux is unavailable: liveness is *unknown*, not *dead*."""

    def has_live_session(self, target: str) -> Optional[bool]:
        return None

    def live_pane_pids(self, target: str) -> List[int]:
        return []


def _tmux_or_null(tmux):
    """Use a real ``TmuxRunner`` only when tmux is actually installed."""
    if tmux is None:
        from ..runner import TmuxRunner

        tmux = TmuxRunner()
    if not getattr(tmux, "is_available", lambda: True)():
        return _NullTmux()
    return tmux


def _session_row(session: Session, pauses: PauseStore, tmux) -> Row:
    ref = session.work_item
    row = Row(
        ref=ref.ref,
        url=work_item_url(ref),
        status=STATUS_ACTIVE if session.status == "active" else STATUS_CLOSED,
        harness=session.harness,
        session_id=session.harness_session_id,
        runner=session.runner,
        cwd=session.cwd,
        pr_ref=session.pr_ref,
        pr_url=session.pr_url,
        created_at=session.created_at,
        last_event_at=session.last_event_at or "",
    )
    if session.runner == "tmux" and session.tmux_target:
        live = tmux.has_live_session(session.tmux_target)
        pids = tmux.live_pane_pids(session.tmux_target) if live else []
        host = f"tmux:{session.tmux_target}"
        if pids:
            host += f" pid {pids[0]}"
        row.host = host
        row.host_live = live
        row.attach = f"tmux attach -t {session.tmux_target}"
    elif session.owner_pid:
        # A print-mode harness has no process of its own between dispatches;
        # the daemon that spawned it is the process an operator can point at.
        row.host = f"process:{session.owner_pid}"
        row.host_live = pid_alive(session.owner_pid)

    record = pauses.record(ref)
    if record is not None:
        row.pause_sources = [record.source]
        row.pause_reason = record.reason
        row.paused_at = record.paused_at
        row.paused_by = record.by
        if row.status == STATUS_ACTIVE:
            row.status = STATUS_PAUSED
    return row


def build_rows(
    registry: SessionRegistry,
    pauses: PauseStore,
    poll_state=None,
    tmux=None,
    status: Optional[str] = None,
    work_item: str = "",
) -> List[Row]:
    """Join registry + poll state + pauses (+ tmux liveness) into sorted rows.

    ``poll_state`` is any object exposing the ``PollState`` read API
    (``tracked_refs``/``spawn_attempts``/``spawn_gave_up``/``last_polled_at``);
    ``None`` simply omits the tracking columns. ``tmux`` defaults to a real
    :class:`~the_loop.runner.TmuxRunner`, degrading to "unknown" liveness when
    tmux is not installed — an absent tmux must not be reported as a dead
    session.
    """
    tmux = _tmux_or_null(tmux)
    rows = {}
    for session in registry.list_sessions():
        row = _session_row(session, pauses, tmux)
        rows[row.ref] = row

    if poll_state is not None:
        for ref in poll_state.tracked_refs():
            row = rows.get(ref)
            if row is None:
                row = Row(ref=ref, status=STATUS_TRACKED)
                try:
                    row.url = work_item_url(WorkItemRef.parse(ref))
                except ValueError:
                    row.url = ""
                record = pauses.record(ref)
                if record is not None:
                    row.pause_sources = [record.source]
                    row.pause_reason = record.reason
                    row.paused_at = record.paused_at
                    row.paused_by = record.by
                    row.status = STATUS_PAUSED
                rows[ref] = row
            row.tracked = True
            row.spawn_attempts = poll_state.spawn_attempts(ref)
            row.spawn_gave_up = poll_state.spawn_gave_up(ref)
            row.last_polled_at = poll_state.last_polled_at(ref)
            if row.status == STATUS_TRACKED and row.spawn_gave_up:
                row.status = STATUS_SPAWN_FAILED

    # A pause on an item with neither a session nor a poll entry is still real
    # (an operator may park an item pre-emptively) — show it rather than lose it.
    for record in pauses.list_paused():
        if record.ref in rows:
            continue
        row = Row(ref=record.ref, status=STATUS_PAUSED, pause_sources=[record.source])
        row.pause_reason = record.reason
        row.paused_at = record.paused_at
        row.paused_by = record.by
        try:
            row.url = work_item_url(WorkItemRef.parse(record.ref))
        except ValueError:
            row.url = ""
        rows[record.ref] = row

    selected = list(rows.values())
    if work_item:
        selected = [row for row in selected if row.ref == work_item]
    if status:
        selected = [row for row in selected if row.status == status]
    return sorted(selected, key=lambda row: row.sort_key)


# -- rendering ------------------------------------------------------------------

_COLUMNS = (
    ("Work item", lambda row: row.ref),
    ("Status", lambda row: row.status),
    ("Harness", lambda row: row.harness or "-"),
    ("Runner", lambda row: row.runner or "-"),
    ("Where", lambda row: row.host_display),
    ("PR", lambda row: row.pr_ref or "-"),
    ("Last event", lambda row: row.last_event_at or row.last_polled_at or "-"),
)


def render_table(rows: Sequence[Row]) -> str:
    """Column-aligned plain text — the header plus one line per row."""
    table = [[title for title, _ in _COLUMNS]]
    table += [[_elide(get(row)) for _, get in _COLUMNS] for row in rows]
    widths = [max(len(line[i]) for line in table) for i in range(len(_COLUMNS))]
    return "\n".join(
        "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(line)).rstrip()
        for line in table
    )


def render_detail(row: Row) -> str:
    """Everything known about one work item, as labelled ``key: value`` lines."""
    pause = "no"
    if row.pause_sources:
        pause = f"yes (via {', '.join(row.pause_sources)}"
        pause += f" by @{row.paused_by})" if row.paused_by else ")"
        if row.pause_reason:
            pause += f" — {row.pause_reason}"
        if row.paused_at:
            pause += f" since {row.paused_at}"
    lines = [
        ("Work item", row.ref),
        ("URL", row.url or "-"),
        ("Status", row.status),
        ("Paused", pause),
        ("Harness", row.harness or "-"),
        ("Session id", row.session_id or "-"),
        ("Runner", row.runner or "-"),
        ("Where", row.host_display),
        ("Attach", row.attach or "-"),
        ("Working dir", row.cwd or "-"),
        ("Pull request", row.pr_url or row.pr_ref or "-"),
        ("Created", row.created_at or "-"),
        ("Last event", row.last_event_at or "-"),
        ("Polled by", "the-loop poll" if row.tracked else "-"),
        ("Last polled", row.last_polled_at or "-"),
        (
            "Spawn attempts",
            f"{row.spawn_attempts}{' (gave up)' if row.spawn_gave_up else ''}"
            if row.tracked
            else "-",
        ),
    ]
    width = max(len(label) for label, _ in lines)
    return "\n".join(f"{label.ljust(width)}  {value}" for label, value in lines)
