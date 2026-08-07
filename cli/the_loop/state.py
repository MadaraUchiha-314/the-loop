"""One configured root for everything the-loop's CLI generates, organised by
what the files *are* (issue-106, issue-128).

Before issue-106, each generated file carried its own default path — the session
registry at ``.the-loop/sessions``, the poll state at
``.the-loop/poll-state.json``, the event log at ``.the-loop/logs/events.jsonl``,
the receiver pidfile at ``.the-loop/gh-webhook.pid``. Four defaults, four places
to change, and no single directory an operator could back up, relocate or wipe.
``state.root`` became that directory.

Issue-128 asked the next question — *which of it can I carry to another
machine?* — and the answer reorganised the layout. The old one grouped files by
**who wrote them** (registry / control / poller), which is why there were three
shapes, a nested ``control/`` directory and a ``.gitignore`` recipe that needed
two negations to express one idea. This one groups them by **what they are**:

===================  =========================================  ==========
portable state       ``<root>/portable/<slug>.json``            travels
session handles      ``<root>/local/<slug>.json``               local
event log            ``<root>/logs/events.jsonl``               local
receiver pidfile     ``<root>/gh-webhook.pid``                  local
===================  =========================================  ==========

One file per work item on each side. ``portable/`` holds what an authorized user
armed **and** what the poller has already seen — facts about the world, true
whoever runs the daemon, and not derivable from GitHub. ``local/`` holds the
handle to a harness conversation on *this* machine. So "track the portable
half" is one directory, and two machines conflict only if they worked the same
work item (the old single ``poll-state.json`` guaranteed a conflict).

**Defaults only.** ``routing.registryDir`` still overrides the local directory
verbatim. ``polling.stateFile`` is gone (a file where there is now a directory);
:mod:`the_loop.migrations` retires it loudly rather than ignoring it.

Upgrades never lose state: :data:`LegacyLayout` records where each store used to
live, and the stores read the old location when the new record has no such
section yet, so the first run after an upgrade neither re-baselines a watched
thread nor forgets what was armed. Writes always go to the new layout.

Spec: docs/specs/issue-106/design.md §5, docs/specs/issue-128/design.md §2, §9.
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
    "LegacyLayout",
    "StateLayout",
    "layout_from_config",
    "legacy_layout",
]

DEFAULT_STATE_ROOT = ".the-loop"


@dataclass(frozen=True)
class StateLayout:
    """The generated-file layout under one root directory."""

    root: str = DEFAULT_STATE_ROOT

    @property
    def root_path(self) -> Path:
        return Path(self.root or DEFAULT_STATE_ROOT)

    @property
    def portable_dir(self) -> str:
        """Work-item records: control + poll state, one file per work item."""
        return str(self.root_path / "portable")

    @property
    def portable_index(self) -> str:
        """The portable directory's index — derived, rewritten on every record write."""
        return str(self.root_path / "portable" / "index.json")

    @property
    def local_dir(self) -> str:
        """Session records — handles to harness conversations on this machine."""
        return str(self.root_path / "local")

    @property
    def event_log(self) -> str:
        return str(self.root_path / "logs" / "events.jsonl")

    @property
    def pidfile(self) -> str:
        return str(self.root_path / "gh-webhook.pid")


@dataclass(frozen=True)
class LegacyLayout:
    """Where the stores lived before issue-128 split them by portability.

    Read-only, and read only when the new record has no such section: the stores
    consult it so an upgrade neither re-baselines every watched thread nor
    forgets what an authorized user armed. Nothing writes here any more, so a
    work item converges on the new layout the first time it is touched — and an
    operator can delete the old paths once ``the-loop sessions list`` looks
    right. Deliberately not part of :class:`StateLayout`: these are not paths
    the-loop generates, they are paths it *remembers*.
    """

    sessions_dir: str  # <root>/sessions/       — session records
    control_dir: str  # <root>/sessions/control/ — control records
    poll_state: str  # <root>/sessions/poll-state.json
    pre_106_poll_state: str = ".the-loop/poll-state.json"


def legacy_layout(layout: StateLayout) -> LegacyLayout:
    """The pre-issue-128 locations under the same root."""
    sessions = layout.root_path / "sessions"
    return LegacyLayout(
        sessions_dir=str(sessions),
        control_dir=str(sessions / "control"),
        poll_state=str(sessions / "poll-state.json"),
    )


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
    default: str  # the documented path, e.g. "<root>/local/<slug>.json"
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
        name="work-item record",
        attr="portable_dir",
        default="<root>/portable/<slug>.json",
        portable=True,
        holds=(
            "control (the last start|stop|pause|resume, its actor and time) and "
            "poll (seenComments, commentAttempts, the spawn ledger, lastPolledAt)"
        ),
        why=(
            "statements about the work item and about what GitHub already told "
            "us — true whoever runs the daemon. Neither is derivable upstream: "
            "nothing on GitHub records that a stop was honoured, and a machine "
            "without the poll half treats every watched thread as first-sight."
        ),
    ),
    GeneratedPath(
        name="work-item index",
        attr="portable_index",
        default="<root>/portable/index.json",
        portable=True,
        holds=(
            "one entry per record beside it: ref, url, file name, which sections "
            "it holds"
        ),
        why=(
            "it describes portable records, so it travels with them or describes "
            "a directory that is not there. Derived on every write and read by "
            "nothing, so a copy is never wrong for long and two machines "
            "conflicting on it may resolve to either side."
        ),
    ),
    GeneratedPath(
        name="session record",
        attr="local_dir",
        default="<root>/local/<slug>.json",
        portable=False,
        holds=(
            "harnessSessionId, cwd, runner, tmuxTarget, status, recentDeliveries, "
            "and (issue-172) pullRequests — every PR delivering this work item "
            "with its own tmux session and conversation. One file per work item"
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
