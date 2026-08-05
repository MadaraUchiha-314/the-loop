"""Core capability: sessions — the work-item ↔ harness-session registry (issue-161).

Reads come straight from the registry + the portable control sections. The four
control verbs (start/pause/resume/stop, issue-106) run through **the CLI's own
verb as a transitional adapter**: `the-loop sessions <verb>` is today's single
implementation of "apply locally, record on the portable record, report on the
ticket", and re-implementing that ordering here would be exactly the duplicated
-behaviour risk R1.5 forbids. The spawn is an argv list (never a shell) of this
same interpreter, with ``THE_LOOP_SERVICE_LOCAL=1`` set so the rewired CLI verb
executes its local path instead of routing back to the service (loop
prevention). Folding the dispatcher itself into core is the recorded follow-up.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Any, Dict, List, Optional

from ..control import ControlStore
from ..sessions.registry import SessionRegistry
from ..state import layout_from_config, legacy_layout
from ..workitem import WorkItemRef

#: Env var marking an invocation made *by the service into its own CLI*; the
#: rewired command sees it and takes the local execution path.
SERVICE_LOCAL_ENV = "THE_LOOP_SERVICE_LOCAL"

CONTROL_VERBS = ("start", "pause", "resume", "stop")


def _layout(config: Optional[dict] = None):
    return layout_from_config(config or {})


def list_sessions(
    status: Optional[str] = None, config: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """Every registered session, with its last recorded control command."""
    layout = _layout(config)
    registry = SessionRegistry(layout.local_dir)
    control = ControlStore(layout.portable_dir, legacy=legacy_layout(layout))
    sessions = []
    for session in registry.list_sessions(status=status):
        record = control.get(session.work_item)
        sessions.append(
            {
                "workItem": session.work_item.ref,
                "harness": session.harness,
                "harnessSessionId": session.harness_session_id,
                "tmuxTarget": session.tmux_target or "",
                "status": session.status,
                "lastEventAt": session.last_event_at or "",
                "control": record.command if record else "",
            }
        )
    return sessions


def get_session(ref: str, config: Optional[dict] = None) -> Dict[str, Any]:
    """One work item's session, or ``LookupError``."""
    parsed = WorkItemRef.parse(ref)
    for session in list_sessions(config=config):
        if session["workItem"] == parsed.ref:
            return session
    raise LookupError(f"no session registered for {ref}")


def control_session(
    ref: str,
    verb: str,
    comment: bool = True,
    config: Optional[dict] = None,
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Apply one control verb through the CLI's own implementation.

    Returns ``{verb, workItem, exitCode, output}``; raises ``ValueError`` for a
    malformed ref or an unknown verb before anything is spawned.
    """
    if verb not in CONTROL_VERBS:
        raise ValueError(f"unknown control verb {verb!r} (one of {CONTROL_VERBS})")
    parsed = WorkItemRef.parse(ref)
    argv = [
        sys.executable,
        "-m",
        "the_loop",
        "sessions",
        verb,
        "--work-item",
        parsed.ref,
    ]
    if not comment:
        argv.append("--no-comment")
    env = {**os.environ, SERVICE_LOCAL_ENV: "1"}
    proc = subprocess.run(  # noqa: S603 — fixed argv, no shell
        argv, capture_output=True, text=True, timeout=timeout, env=env
    )
    return {
        "verb": verb,
        "workItem": parsed.ref,
        "exitCode": proc.returncode,
        "output": (proc.stdout + proc.stderr).strip(),
    }
