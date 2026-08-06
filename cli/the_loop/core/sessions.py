"""Core capability: sessions — the work-item ↔ harness-session registry (issue-161).

This module owns the **whole** session surface, reads and control verbs alike.
The control logic (apply locally → record on the portable record → report on
the ticket) lives here rather than in the CLI command: the CLI, the HTTP API
and the MCP tools all reach it through this one implementation, which is what
R1.1–R1.4 ask for. Nothing here shells out to the-loop's own CLI.

Output discipline: core never prints. Each verb returns the human-readable
lines it would have printed as ``messages`` (each tagged ``out`` or ``err``)
plus the exit code the CLI should use, so the command layer stays a renderer
and the API/MCP surfaces get the same words.
"""

from __future__ import annotations

import getpass
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import cli_config, eventlog
from ..comments import post_issue_comment
from ..control import (
    PAUSE,
    RESUME,
    START,
    STOP,
    ControlConfig,
    ControlStore,
    command_comment,
)
from ..harness import ClaudeCodeAdapter, CursorAgentAdapter
from ..runner import TmuxRunner
from ..sessions.registry import RegistryError, Session, SessionRegistry
from ..state import layout_from_config, legacy_layout
from ..webhook.dispatcher import TmuxConfig
from ..webhook.router import RoutedEvent
from ..workitem import WorkItemRef

CONTROL_VERBS = (START, PAUSE, RESUME, STOP)

#: The harness CLIs a registration may name, and the binary each one needs.
HARNESS_BINARIES = {
    "claude": ClaudeCodeAdapter.default_binary,
    "cursor": CursorAgentAdapter.default_binary,
}


def _layout(config: Optional[dict] = None):
    return layout_from_config(config or {})


def _routing(config: Optional[dict]) -> dict:
    """``routing`` out of the config this call was given, not off disk.

    Core is handed the operator's config by whichever surface called it, so
    re-reading the file here would let a caller's explicit config be silently
    overruled by whatever the default path happens to hold — and would make the
    facade unable to serve two configurations in one process.
    """
    if config:
        return (config.get("routing") or {}) if isinstance(config, dict) else {}
    return cli_config.load_routing_config()


def _registry_dir(config: Optional[dict], override: str = "") -> str:
    if override:
        return override
    return str(_routing(config).get("registryDir") or _layout(config).local_dir)


def _control_store(config: Optional[dict], portable_dir: str = "") -> ControlStore:
    layout = _layout(config)
    return ControlStore(
        portable_dir or layout.portable_dir, legacy=legacy_layout(layout)
    )


def _tmux_config(config: Optional[dict] = None) -> TmuxConfig:
    """``routing.tmux`` — retention/termination policy (issue-86, issue-94)."""
    return TmuxConfig.from_mapping(_routing(config).get("tmux") or {})


def _control_config(config: Optional[dict] = None) -> ControlConfig:
    return ControlConfig.from_mapping(_routing(config).get("control") or {})


def _local_actor() -> str:
    """Who invoked this — recorded for the audit trail, never trusted as auth."""
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — no controlling user (container/cron)
        return ""


def _dispatcher_for(config: Optional[dict], registry_dir: str, portable_dir: str):
    """The daemon's own dispatcher, pointed at the dirs this call names."""
    from ..commands.poll import _build_dispatcher

    routing = dict(_routing(config))
    routing["registryDir"] = registry_dir
    dispatcher, resolved = _build_dispatcher(routing, _layout(config))
    dispatcher.control_store = _control_store(config, portable_dir)
    return dispatcher, resolved


# -- reads ---------------------------------------------------------------------


def list_sessions(
    status: Optional[str] = None,
    config: Optional[dict] = None,
    registry_dir: str = "",
    portable_dir: str = "",
) -> List[Dict[str, Any]]:
    """Every registered session, with its last recorded control command.

    Each entry is the registry's own record verbatim (so ``workItem`` is the
    parsed object, as it is on disk) plus two additions: ``ref``, the flat
    string every caller actually keys on, and ``control``, the control record
    or ``None``. Nothing is projected away — the CLI, the API and the MCP tools
    all read one shape, and a field added to a session shows up in all three.
    """
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    control = _control_store(config, portable_dir)
    sessions = []
    for session in registry.list_sessions(status=status):
        record = control.get(session.work_item)
        sessions.append(
            {
                "ref": session.work_item.ref,
                **session.to_dict(),
                "control": record.to_dict() if record else None,
            }
        )
    return sessions


def get_session(
    ref: str,
    config: Optional[dict] = None,
    registry_dir: str = "",
    portable_dir: str = "",
) -> Dict[str, Any]:
    """One work item's session, or ``LookupError``."""
    parsed = WorkItemRef.parse(ref)
    for session in list_sessions(
        config=config, registry_dir=registry_dir, portable_dir=portable_dir
    ):
        if session["ref"] == parsed.ref:
            return session
    raise LookupError(f"no session registered for {ref}")


# -- registration --------------------------------------------------------------


def register_session(
    ref: str,
    harness: str,
    harness_session_id: str,
    cwd: str = ".",
    force: bool = False,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Link a work item to the harness session working it (issue-15, R2.2).

    A missing harness binary is a **warning**, not a refusal: the registration
    is a fact about who is working the item, and dispatch hard-errors later if
    the binary is still absent when an event arrives.
    """
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if harness not in HARNESS_BINARIES:
        raise ValueError(
            f"unknown harness {harness!r} (one of {sorted(HARNESS_BINARIES)})"
        )
    messages: List[Dict[str, str]] = []
    binary = HARNESS_BINARIES[harness]
    if shutil.which(binary) is None:
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"warning: harness CLI {binary!r} not found on PATH; events "
                    f"for {work_item.ref} cannot be dispatched until it is "
                    "installed"
                ),
            }
        )
    session = Session(
        work_item=work_item,
        harness=harness,
        harness_session_id=harness_session_id,
        cwd=str(Path(cwd).resolve()),
    )
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    try:
        registry.register(session, force=force)
    except RegistryError as exc:
        # A caller mistake (an active registration already exists), so the
        # surfaces map it the same way they map a malformed ref.
        raise ValueError(f"{exc} (pass force to replace)") from exc
    messages.append(
        {
            "stream": "out",
            "text": f"registered {work_item.ref} -> {harness}:{harness_session_id}",
        }
    )
    return {
        "workItem": work_item.ref,
        "harness": harness,
        "harnessSessionId": harness_session_id,
        "exitCode": 0,
        "messages": messages,
    }


def close_session(
    ref: str,
    keep_tmux: Optional[bool] = None,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Close a work item's registration and settle its tmux session.

    ``keep_tmux`` defaults to ``routing.tmux.keepSessionOnClose``. Keeping the
    session retains the transcript while still ending the harness inside it
    (unless ``killHarnessOnClose`` is false), so nothing can be typed into a
    closed work item's terminal (issue-94).
    """
    work_item = WorkItemRef.parse(ref)
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    session = registry.find_by_work_item(work_item)
    messages: List[Dict[str, str]] = []
    if not registry.close(work_item):
        messages.append(
            {"stream": "err", "text": f"no active session for {work_item.ref}"}
        )
        return {
            "workItem": work_item.ref,
            "closed": False,
            "exitCode": 1,
            "messages": messages,
        }
    if session is not None and session.tmux_target:
        tmux = _tmux_config(config)
        keep = tmux.keep_session_on_close if keep_tmux is None else keep_tmux
        if keep:
            if tmux.kill_harness_on_close:
                result = TmuxRunner().terminate_harness(
                    session, grace=tmux.harness_kill_grace_seconds
                )
                if result.ok and not result.session_missing:
                    messages.append(
                        {
                            "stream": "out",
                            "text": (
                                f"ended the harness in tmux session "
                                f"{session.tmux_target}"
                            ),
                        }
                    )
                elif not result.ok:
                    messages.append({"stream": "err", "text": f"note: {result.error}"})
            messages.append(
                {
                    "stream": "out",
                    "text": (
                        f"kept tmux session {session.tmux_target} — attach: tmux "
                        f"attach -r -t {session.tmux_target} (pass --kill-tmux to "
                        "end it)"
                    ),
                }
            )
        else:
            result = TmuxRunner().kill(session)  # best-effort (R7.2/R7.3)
            messages.append(
                {
                    "stream": "out",
                    "text": (
                        f"killed tmux session {session.tmux_target}"
                        if result.ok
                        else f"note: tmux session {session.tmux_target} was already gone"
                    ),
                }
            )
    messages.append({"stream": "out", "text": f"closed session for {work_item.ref}"})
    return {
        "workItem": work_item.ref,
        "closed": True,
        "exitCode": 0,
        "messages": messages,
    }


# -- control verbs -------------------------------------------------------------


def control_session(
    ref: str,
    verb: str,
    comment: bool = True,
    config: Optional[dict] = None,
    registry_dir: str = "",
    portable_dir: str = "",
) -> Dict[str, Any]:
    """Apply one control verb to a work item, end to end.

    Order matters and is preserved from the CLI implementation this replaces:
    the local effect first, the control record with it, and the ticket comment
    last — the comment is a *report* of what happened, so a failing ``gh``
    never leaves the ticket claiming something the-loop did not do.

    A **disarming** verb (pause/stop) is recorded whether or not there was
    anything to act on, so a stopped work item does not re-spawn on the next
    event. An **arming** one (start/resume) is recorded only when it actually
    acted (owner decision on PR #107).
    """
    if verb not in CONTROL_VERBS:
        raise ValueError(f"unknown control verb {verb!r} (one of {CONTROL_VERBS})")
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref

    registry_dir = _registry_dir(config, registry_dir)
    store = _control_store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []

    if verb in (PAUSE, STOP):
        store.record(work_item, verb, source="cli", actor=actor)

    effect, code = _apply(verb, work_item, config, registry_dir, portable_dir, messages)

    if verb in (START, RESUME) and effect in ("resumed", "running"):
        store.record(work_item, verb, source="cli", actor=actor)

    eventlog.emit(
        "control.command",
        work_item=work_item.ref,
        command=verb,
        source="cli",
        actor=actor,
        effect=effect,
    )
    if comment:
        _announce(work_item, verb, actor, messages, config)

    return {
        "verb": verb,
        "workItem": work_item.ref,
        "effect": effect,
        "exitCode": code,
        "messages": messages,
        # Kept for callers that only rendered the flat text before.
        "output": "\n".join(m["text"] for m in messages),
    }


def _apply(
    verb: str,
    work_item: WorkItemRef,
    config: Optional[dict],
    registry_dir: str,
    portable_dir: str,
    messages: List[Dict[str, str]],
) -> Tuple[str, int]:
    """``(effect, exit code)`` of applying ``verb`` — the local half."""
    registry = SessionRegistry(registry_dir)
    session = registry.find_by_work_item(work_item)

    if verb in (START, RESUME):
        if session is not None and session.is_paused:
            registry.resume(work_item)
            messages.append(
                {"stream": "out", "text": f"resumed session for {work_item.ref}"}
            )
            return "resumed", 0
        if verb == RESUME:
            where = "is not paused" if session is not None else "has no session"
            messages.append(
                {"stream": "err", "text": f"nothing to resume: {work_item.ref} {where}"}
            )
            return "noop", 1
        if session is not None:
            messages.append(
                {
                    "stream": "out",
                    "text": f"{work_item.ref} is already running ({session.harness})",
                }
            )
            return "running", 0
        return _spawn_for_start(work_item, config, registry_dir, portable_dir, messages)

    if verb == PAUSE:
        if registry.pause(work_item) is None:
            messages.append(
                {
                    "stream": "err",
                    "text": (
                        f"no running session for {work_item.ref} to pause; recorded "
                        "the pause, so it will not spawn on its own"
                    ),
                }
            )
            return "noop", 1
        messages.append(
            {
                "stream": "out",
                "text": (
                    f"paused session for {work_item.ref} — events are held until "
                    "you resume it"
                ),
            }
        )
        return "paused", 0

    # STOP
    if session is None:
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"no live session for {work_item.ref}; recorded the stop, so it "
                    "will not spawn on its own"
                ),
            }
        )
        return "noop", 1
    dispatcher, _ = _dispatcher_for(config, registry_dir, portable_dir)
    try:
        dispatcher.close_session(session, reason="stopped from the CLI")
    finally:
        dispatcher.stop(timeout=5)
    messages.append(
        {
            "stream": "out",
            "text": f"stopped execution for {work_item.ref} (session closed)",
        }
    )
    return "stopped", 0


def _spawn_for_start(
    work_item: WorkItemRef,
    config: Optional[dict],
    registry_dir: str,
    portable_dir: str,
    messages: List[Dict[str, str]],
) -> Tuple[str, int]:
    """Spawn a session for a start, through the *daemon's* dispatcher.

    Not a second spawn implementation: the workspace checkout, the harness
    trust pre-flight, the configured runner and the session announcement all
    behave exactly as they do for a start issued by comment. The synthesised
    event is marked ``labeled=True`` — local/API access to the control plane is
    a strictly higher privilege than commenting on an issue.

    The control record is armed *before* the spawn (the dispatcher's gate reads
    it) and **cleared again if no session came up**, so a start that could not
    run leaves nothing standing (owner decision on PR #107).
    """
    store = _control_store(config, portable_dir)
    dispatcher, routing = _dispatcher_for(config, registry_dir, portable_dir)
    if routing.spawn_on_unmatched == "never":
        messages.append(
            {
                "stream": "err",
                "text": (
                    "error: routing.spawnOnUnmatched is 'never', so the-loop will "
                    "not spawn sessions; set it to 'labeled' (or 'always') first"
                ),
            }
        )
        dispatcher.stop(timeout=5)
        return "rejected", 1

    store.record(work_item, START, source="cli", actor=_local_actor())
    routed = RoutedEvent(
        event="issues",
        action="control-start",
        delivery_id=f"cli-start-{uuid.uuid4()}",
        work_items=[work_item],
        payload={
            "action": "control-start",
            "repository": {"full_name": f"{work_item.owner}/{work_item.repo}"},
            "issue": {"number": work_item.number},
        },
        labeled=True,
    )
    messages.append(
        {"stream": "out", "text": f"starting a session for {work_item.ref}…"}
    )
    try:
        dispatcher.handle(routed)
    finally:
        # Drains the work item's queue so the spawn runs to completion before
        # the registry is read back.
        dispatcher.stop(timeout=routing.dispatch_timeout_seconds)

    session = SessionRegistry(registry_dir).find_by_work_item(work_item)
    if session is None:
        # Nothing came up, so leave nothing armed.
        store.clear(work_item)
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"error: could not start a session for {work_item.ref} — see "
                    "the log above (and `the-loop events --work-item …`) for why"
                ),
            }
        )
        return "failed", 1
    messages.append(
        {
            "stream": "out",
            "text": (
                f"started {session.harness} session for {work_item.ref} "
                f"(tmux: {session.tmux_target})"
            ),
        }
    )
    return "spawned", 0


def _announce(
    work_item: WorkItemRef,
    verb: str,
    actor: str,
    messages: List[Dict[str, str]],
    cli_conf: Optional[dict] = None,
) -> None:
    """Record the action on the ticket (best-effort — never fails the action)."""
    config = _control_config(cli_conf)
    ok, error = post_issue_comment(
        work_item,
        command_comment(verb, config, actor=actor),
        gh_binary=config.gh_binary,
    )
    if ok:
        messages.append(
            {
                "stream": "out",
                "text": f"commented {config.keyword(verb)!r} on {work_item.ref}",
            }
        )
        eventlog.emit("control.announced", work_item=work_item.ref, command=verb)
        return
    messages.append(
        {
            "stream": "err",
            "text": (
                f"note: could not comment on {work_item.ref} ({error}); the command "
                "was still applied locally"
            ),
        }
    )
    eventlog.emit(
        "control.announce_failed",
        level="warning",
        work_item=work_item.ref,
        command=verb,
        error=error,
    )
