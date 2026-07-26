"""Where the daemon keeps its runtime state — one directory, one gitignore line.

``.the-loop/`` used to mix two very different kinds of file: **config** an
operator writes and often checks in (``cli-config.yaml``, the schemas,
``collaborators.yaml``), and **runtime state** the daemon writes and nobody
should ever edit (the session registry, the poller's ledger, pidfiles, the
event log). The state half was scattered across five top-level paths, each with
its own gitignore line, and every new feature added another (issue-98 review).

Everything now lives under **``.the-loop/state/``**::

    .the-loop/
      cli-config.yaml              # config
      state/                       # runtime state — one gitignore line
        sessions/<slug>.json       # session registry     (routing.registryDir)
        paused.json                # pause ledger         (routing.pauseFile)
        poll-state.json            # poller ledger        (polling.stateFile)
        poll.pid  gh-webhook.pid   # daemon pidfiles
        logs/events.jsonl          # structured event log (eventLog.path)

**Nothing breaks on upgrade.** :func:`resolve` keeps reading the pre-move path
whenever that is the one that actually exists — a daemon mid-flight keeps its
session registry, its dedup ledger and its pidfiles exactly where it left them,
and says so once in the log. ``the-loop state migrate`` moves them over when the
operator is ready; ``the-loop state paths`` shows which layout is in force. An
explicitly configured path always wins and is never second-guessed.

Spec: docs/specs/issue-98/design.md §11; decision-039.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger("the-loop.state")

STATE_DIR = ".the-loop/state"


@dataclass(frozen=True)
class StatePath:
    """One piece of runtime state: where it lives now, and where it used to."""

    key: str  # the config key that overrides it, for messages
    current: str  # default under .the-loop/state/
    legacy: str  # the pre-issue-98 default
    description: str

    @property
    def is_dir(self) -> bool:
        return not Path(self.current).suffix


# Every runtime-state path the daemon writes, in the order `state paths` lists.
PATHS: List[StatePath] = [
    StatePath(
        key="webhooks.ghWebhook.routing.registryDir",
        current=f"{STATE_DIR}/sessions",
        legacy=".the-loop/sessions",
        description="session registry (one JSON file per session)",
    ),
    StatePath(
        key="webhooks.ghWebhook.routing.pauseFile",
        current=f"{STATE_DIR}/paused.json",
        legacy=".the-loop/paused.json",
        description="per-work-item pause ledger",
    ),
    StatePath(
        key="polling.stateFile",
        current=f"{STATE_DIR}/poll-state.json",
        legacy=".the-loop/poll-state.json",
        description="poller cross-cycle retry/dedup ledger",
    ),
    StatePath(
        key="polling.pidfile",
        current=f"{STATE_DIR}/poll.pid",
        legacy=".the-loop/poll.pid",
        description="poller pidfile",
    ),
    StatePath(
        key="webhooks.ghWebhook.pidfile",
        current=f"{STATE_DIR}/gh-webhook.pid",
        legacy=".the-loop/gh-webhook.pid",
        description="webhook receiver pidfile",
    ),
    StatePath(
        key="eventLog.path",
        current=f"{STATE_DIR}/logs/events.jsonl",
        legacy=".the-loop/logs/events.jsonl",
        description="structured event log",
    ),
]

_BY_CURRENT = {path.current: path for path in PATHS}

# Legacy paths already warned about, so a long-running daemon says it once.
_warned = set()


def _exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()


def resolve(default: str, configured: Optional[str] = None) -> str:
    """The path to actually use for a piece of runtime state.

    ``default`` is one of :data:`PATHS`' ``current`` values. ``configured`` is
    whatever the operator set (``None``/``""`` when they set nothing).

    * An explicitly configured path — anything other than the current default —
      is returned untouched. The operator chose it; nothing is inferred.
    * Otherwise the new path is used, **unless** it does not exist and the
      pre-move one does: a daemon that already has state keeps reading it, with
      a one-time note pointing at ``the-loop state migrate``.
    """
    if configured and configured != default:
        return configured
    path = _BY_CURRENT.get(default)
    if path is None:
        return default
    if _exists(path.current) or not _exists(path.legacy):
        return path.current
    if path.legacy not in _warned:
        _warned.add(path.legacy)
        logger.info(
            "using the pre-move %s at %s (the default is now %s) — run "
            "`the-loop state migrate` to consolidate the-loop's runtime state "
            "under %s/",
            path.description,
            path.legacy,
            path.current,
            STATE_DIR,
        )
    return path.legacy


@dataclass
class MigrationStep:
    """One planned/performed move, for `state migrate`'s report."""

    path: StatePath
    action: str  # moved | would-move | skipped-missing | skipped-target-exists
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


def plan() -> List[MigrationStep]:
    """What ``state migrate`` would do, without touching anything."""
    steps = []
    for path in PATHS:
        if not _exists(path.legacy):
            steps.append(MigrationStep(path, "skipped-missing"))
        elif _exists(path.current):
            steps.append(MigrationStep(path, "skipped-target-exists"))
        else:
            steps.append(MigrationStep(path, "would-move"))
    return steps


def migrate(dry_run: bool = False) -> List[MigrationStep]:
    """Move every pre-move state file/dir under ``.the-loop/state/``.

    Idempotent and non-destructive: an already-migrated entry is skipped, and
    one whose *target* exists is left alone rather than overwritten — that is a
    genuine conflict (state in both layouts) only the operator can settle.
    Stop the daemons first; a moved pidfile or registry under a running process
    is how you end up with two daemons believing they own the same work item.
    """
    steps = plan()
    if dry_run:
        return steps
    for step in steps:
        if step.action != "would-move":
            continue
        target = Path(step.path.current)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # os.replace refuses a cross-device move and a non-empty target
            # dir; shutil.move handles both and is what a state dir needs.
            shutil.move(step.path.legacy, str(target))
        except (OSError, shutil.Error) as exc:
            step.error = str(exc)
            step.action = "failed"
            logger.warning("could not move %s: %s", step.path.legacy, exc)
            continue
        step.action = "moved"
        logger.info("moved %s -> %s", step.path.legacy, step.path.current)
    return steps


def running_daemons() -> List[str]:
    """Pidfiles of daemons that look alive, in either layout (migrate guard)."""
    live = []
    for path in PATHS:
        if not path.current.endswith(".pid"):
            continue
        for candidate in (path.current, path.legacy):
            try:
                pid = int(Path(candidate).read_text().strip())
            except (OSError, ValueError):
                continue
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                continue
            except OSError:
                pass  # exists but not ours — still a running process
            live.append(f"{candidate} (pid {pid})")
    return live
