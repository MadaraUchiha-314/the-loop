"""Lifecycle hooks (issue-344): the operator's code at the moments a work item's
delivery turns — declared once in the CLI config, run where the thing they decide is
about to happen, locally or over JSON-RPC.

This package is the seam. :mod:`.contract` defines the six points and the
``LifecycleHooks`` base class (re-exported for authors as :mod:`the_loop.sdk.hooks`);
:mod:`.declaration` parses the top-level ``hooks``; :mod:`.executors` and :mod:`.remote`
are what an entry becomes; :mod:`.runner` runs the chain. This module holds the
**process-wide runner**, the way :mod:`the_loop.eventlog` holds the process-wide log:

* a daemon calls :func:`configure_from_file` at start and refuses to run on a
  declaration that cannot load (R3.6);
* every call site calls :func:`run`, which on an unconfigured process loads the
  resolved CLI config **lazily** — so ``the-loop ask`` inside a session (with the
  daemon's config path exported, issue-393) runs the daemon's hooks — and, when that
  load fails, records ``hooks.load_failed`` and runs with none: the daemon holding the
  same file has already refused to start.

Spec: docs/specs/issue-344/  ·  Decision: 137
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Mapping, Optional, TypeVar, Union

from .. import cli_config, eventlog
from .contract import (
    POINTS,
    Context,
    InputReceived,
    LifecycleHooks,
    PhaseChanged,
    SessionSpawn,
    SessionSpawned,
    WaitingForInput,
    WorkItem,
    WorkItemComplete,
    WorkItemStart,
)
from .declaration import (
    CONFIG_KEY,
    Declaration,
    HooksConfigError,
    config_base_dir,
    read_declaration,
)
from .executors import load
from .runner import Runner

logger = logging.getLogger("the-loop.lifecycle")

__all__ = [
    "CONFIG_KEY",
    "POINTS",
    "Context",
    "Declaration",
    "HooksConfigError",
    "InputReceived",
    "LifecycleHooks",
    "PhaseChanged",
    "Runner",
    "SessionSpawn",
    "SessionSpawned",
    "WaitingForInput",
    "WorkItem",
    "WorkItemComplete",
    "WorkItemStart",
    "configure",
    "configure_from_config",
    "configure_from_file",
    "current",
    "read_declaration",
    "reset",
    "run",
]

C = TypeVar("C", bound=Context)

_runner: Optional[Runner] = None
_lock = threading.Lock()


def configure(runner: Optional[Runner]) -> None:
    """Install ``runner`` as the process-wide chain (``None`` deconfigures)."""
    global _runner
    _runner = runner


def current() -> Optional[Runner]:
    return _runner


def reset() -> None:
    """Deconfigure (tests)."""
    configure(None)


def configure_from_config(
    config: Mapping[str, Any], config_path: Union[str, Path]
) -> Runner:
    """Parse and load the ``hooks`` of an already-loaded CLI config, resolving a
    relative ``path`` against ``config_path``'s directory, and install the result.
    Raises :class:`HooksConfigError` — the caller decides whether that is fatal."""
    declaration = read_declaration(config)
    executors = load(declaration, config_base_dir(config_path))
    runner = Runner(executors)
    configure(runner)
    if executors:
        eventlog.emit(
            "hooks.loaded",
            hooks=[e.name for e in executors],
            count=len(executors),
            config=str(config_path),
        )
        logger.info(
            "loaded %d lifecycle hook(s) from %s: %s",
            len(executors),
            config_path,
            ", ".join(e.name for e in executors),
        )
    return runner


def configure_from_file(strict: bool = True) -> Runner:
    """:func:`configure_from_config` from the CLI config at the resolved path.

    ``strict`` reads the file the way a daemon must — an unparseable file raises — and
    a declaration that cannot load raises either way. No file at all declares nothing.
    """
    path = cli_config.default_cli_config_path()
    if not path.is_file():
        return configure_from_config({}, path)
    loaded = cli_config.load_cli_config(path, strict=strict) or {}
    return configure_from_config(loaded if isinstance(loaded, Mapping) else {}, path)


def run(ctx: C) -> C:
    """Run the process-wide chain on ``ctx`` and return it. Never raises.

    Configures lazily on first use (see the module docstring); a lazy load that fails
    installs an empty runner, so the failure is recorded once, not on every point.
    """
    runner = _runner
    if runner is None:
        with _lock:
            runner = _runner
            if runner is None:
                runner = _lazy_configure()
    return runner.run(ctx)


def _lazy_configure() -> Runner:
    try:
        return configure_from_file(strict=False)
    except Exception as exc:  # noqa: BLE001 — a one-shot command proceeds hookless
        error = (
            f"{exc.__class__.__name__}: {exc}"
            if not isinstance(exc, HooksConfigError)
            else str(exc)
        )
        logger.warning(
            "lifecycle hooks are NOT running in this process: the declaration could not "
            "be loaded (%s). A daemon started on this config would have refused to start",
            error,
        )
        eventlog.emit("hooks.load_failed", level="warning", error=error, strict=False)
        runner = Runner(())
        configure(runner)
        return runner
