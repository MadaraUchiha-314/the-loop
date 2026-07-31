"""One configured root for everything the-loop's CLI generates (issue-106).

Before this, each generated file carried its own default path — the session
registry at ``.the-loop/sessions``, the poll state at
``.the-loop/poll-state.json``, the event log at ``.the-loop/logs/events.jsonl``,
the receiver pidfile at ``.the-loop/gh-webhook.pid``. Four defaults, four places
to change, and no single directory an operator could back up, relocate or wipe.

``state.root`` in the CLI config is that directory, and this module derives
every generated-path **default** from it:

===================  ===============================================
registry             ``<root>/sessions/``
control records      ``<root>/sessions/control/``
poll state           ``<root>/sessions/poll-state.json``
event log            ``<root>/logs/events.jsonl``
receiver pidfile     ``<root>/gh-webhook.pid``
===================  ===============================================

**Defaults only.** Every consumer still reads its own configured key first
(``routing.registryDir``, ``polling.stateFile``, ``eventLog.path``,
``webhooks.ghWebhook.pidfile``) and falls back here when it is unset — so an
existing config with explicit paths behaves byte-identically, and a config with
none of them relocates everything by setting one value. With the default root
three of the four resolve to exactly the pre-issue-106 paths.

The fourth, the poll state, moves under ``sessions/`` (the issue's "consolidate
the stateful session tracking" ask). Silently losing it would re-baseline every
watched thread and re-forward its entire comment history, so
:func:`resolve_poll_state_path` keeps a legacy file that exists and says so.

Knowing *where* the files are is half the question an operator moving machines
has; :data:`GENERATED_PATHS` answers the other half — which of them mean anything
somewhere else (issue-128, decision-046). Two do: the control records (what an
authorized user armed) and the poll state (which comments have been seen) are
facts about the world. The rest are handles to *this* machine — a harness
conversation id, an absolute ``cwd``, a pid, a local audit trail — and copying
them elsewhere is worse than losing them.

Spec: docs/specs/issue-106/design.md §5, docs/specs/issue-128/design.md §2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("the-loop.state")

__all__ = [
    "DEFAULT_STATE_ROOT",
    "GENERATED_PATHS",
    "GeneratedPath",
    "StateLayout",
    "layout_from_config",
    "resolve_poll_state_path",
]

DEFAULT_STATE_ROOT = ".the-loop"

# Where the poll state lived before issue-106 moved its default under
# ``sessions/``. Kept (with a warning) when it is still the only one on disk.
LEGACY_POLL_STATE = ".the-loop/poll-state.json"


@dataclass(frozen=True)
class StateLayout:
    """The generated-file layout under one root directory."""

    root: str = DEFAULT_STATE_ROOT

    @property
    def root_path(self) -> Path:
        return Path(self.root or DEFAULT_STATE_ROOT)

    @property
    def sessions_dir(self) -> str:
        """Session registry files — and the parent of every session-related file."""
        return str(self.root_path / "sessions")

    @property
    def control_dir(self) -> str:
        """Control records (issue-106), beside the sessions they steer."""
        return str(Path(self.sessions_dir) / "control")

    @property
    def poll_state(self) -> str:
        return str(Path(self.sessions_dir) / "poll-state.json")

    @property
    def event_log(self) -> str:
        return str(self.root_path / "logs" / "events.jsonl")

    @property
    def pidfile(self) -> str:
        return str(self.root_path / "gh-webhook.pid")


@dataclass(frozen=True)
class GeneratedPath:
    """One thing the CLI writes, and whether it means anything on another machine.

    ``why`` is not decoration. An entry whose author cannot say *why* it is local
    has probably put a machine handle inside something that is otherwise a fact
    about the world — which is the mistake this declaration exists to catch,
    while the path is being invented and the answer is still cheap.
    """

    name: str  # human label, used in prose and test failures
    attr: str  # the StateLayout property this derives from
    default: str  # the documented path, e.g. "<root>/sessions/<slug>.json"
    portable: bool  # does it mean anything on another machine?
    holds: str
    why: str


#: Every generated path, classified (issue-128, decision-046). Inert data: nothing
#: reads it at runtime. It is pinned by ``cli/tests/test_state_portability.py``,
#: which fails when :class:`StateLayout` grows a path no entry claims — so a new
#: generated file cannot be added without answering "does this travel?" — and when
#: ``docs/cli/state.md`` classifies one differently.
GENERATED_PATHS: Tuple[GeneratedPath, ...] = (
    GeneratedPath(
        name="session record",
        attr="sessions_dir",
        default="<root>/sessions/<slug>.json",
        portable=False,
        holds=(
            "harnessSessionId, cwd, runner, tmuxTarget, status, recentDeliveries — "
            "one file per work item with a session"
        ),
        why=(
            "a handle to a conversation and a directory that exist on one machine. "
            "Copied elsewhere it is not merely useless: find_by_work_item counts it "
            "as live, so the duplicate guard refuses the spawn the new machine needs "
            "and events are routed to a conversation that is not there. It also "
            "carries an absolute path from the operator's filesystem and a resumable "
            "session id, neither of which belongs in a repository."
        ),
    ),
    GeneratedPath(
        name="control record",
        attr="control_dir",
        default="<root>/sessions/control/<slug>.json",
        portable=True,
        holds="ref, command (start|stop|pause|resume), source, actor, requestedAt, note",
        why=(
            "a statement about the work item — an authorized user asked for it to be "
            "running — that is true whoever runs the daemon. Nothing on GitHub records "
            "that a stop was honoured, so a lost record cannot be rebuilt: the item "
            "silently stops being worked, or quietly re-arms."
        ),
    ),
    GeneratedPath(
        name="poll state",
        attr="poll_state",
        default="<root>/sessions/poll-state.json",
        portable=True,
        holds="per work item: seenComments, commentAttempts, spawn ledger, lastPolledAt",
        why=(
            "what GitHub already told us. A machine without it treats every watched "
            "thread as first-sight and re-baselines it. The attempt ledgers inside are "
            "local bookkeeping, carried anyway because they self-heal and splitting the "
            "file would cost a migration to buy nothing."
        ),
    ),
    GeneratedPath(
        name="event log",
        attr="event_log",
        default="<root>/logs/events.jsonl",
        portable=False,
        holds="one JSON object per line: every accept, drop, route, spawn, failure",
        why=(
            "a record of what this machine did, appended to continuously. Two machines "
            "appending to one tracked file conflict on every line, and the trail is "
            "read where it was written."
        ),
    ),
    GeneratedPath(
        name="receiver pidfile",
        attr="pidfile",
        default="<root>/gh-webhook.pid",
        portable=False,
        holds="the pid of the running gh-webhook receiver",
        why="a process id is meaningless on another host, and stale within a reboot.",
    ),
)


def layout_from_config(config: Optional[dict]) -> StateLayout:
    """Read ``state.root`` from a loaded CLI config (best-effort, never raises)."""
    state = ((config or {}).get("state")) or {}
    root = str(state.get("root") or "").strip()
    return StateLayout(root=root or DEFAULT_STATE_ROOT)


def control_dir_for(registry_dir: str) -> str:
    """Control records for a given registry directory.

    Derived from the registry dir rather than the layout so a config that points
    ``routing.registryDir`` somewhere explicit keeps its control records beside
    its sessions — the two are one store of session-related state, and splitting
    them across roots would make "which work items are armed?" unanswerable from
    the directory an operator is looking at.
    """
    return str(Path(registry_dir) / "control")


def resolve_poll_state_path(
    configured: str, layout: StateLayout, *, exists=Path.exists
) -> str:
    """The poll-state file to use: configured → new default → legacy default.

    ``exists`` is injectable for tests. The legacy fallback is deliberately
    conservative: it only applies when nothing is configured, the new location
    does **not** exist and the pre-issue-106 one does — i.e. exactly the
    first run after an upgrade, where adopting the empty new path would
    re-baseline every watched thread and re-forward its whole comment history.
    """
    if configured:
        return configured
    new_path = Path(layout.poll_state)
    if exists(new_path):
        return str(new_path)
    legacy = Path(LEGACY_POLL_STATE)
    if exists(legacy):
        logger.warning(
            "using the pre-issue-106 poll state at %s; its default is now %s "
            "(set polling.stateFile explicitly, or move the file, to silence "
            "this — an empty state file would re-forward every watched thread)",
            legacy,
            new_path,
        )
        return str(legacy)
    return str(new_path)
