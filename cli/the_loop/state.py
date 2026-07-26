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

Spec: docs/specs/issue-106/design.md §5.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("the-loop.state")

__all__ = [
    "DEFAULT_STATE_ROOT",
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
