"""Core capability: standing sessions — the sessions that own no work item (issue-277).

The verbs behind ``the-loop standing …``, ``POST /api/v1/standing-sessions/*``,
the MCP tools and ``loop.standing`` on the SDK — and the three calls
:mod:`the_loop.core.lifecycle` makes so ``the-loop start|stop|status`` covers
these sessions too.

Output discipline is :mod:`the_loop.core.sessions`': core never prints. Every
verb returns rows and ``messages`` (each tagged ``out``/``err``) plus the exit
code the CLI should use, so the command layer stays a renderer and every other
surface gets the same words.

Spec: docs/specs/issue-277/design.md.
"""

from __future__ import annotations

import getpass
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .. import eventlog
from ..harness import build_adapters
from ..harness.base import HarnessAdapter, TrustResult, UnsupportedRunnerError
from ..harness_plugins import PluginConfig
from ..runner import SESSION_DEAD, SESSION_LIVE, SESSION_UNKNOWN, TmuxRunner
from ..standing import (
    RUNNING,
    STOPPED,
    StandingConfig,
    StandingRecord,
    StandingRegistry,
    StandingSession,
    standing_ref,
    tmux_target_for,
    utcnow,
)
from ..state import layout_from_config
from ..trust import TrustConfig
from ..webhook.dispatcher import TmuxConfig

logger = logging.getLogger("the-loop.core.standing")

__all__ = [
    "CONTROL_VERBS",
    "control_standing",
    "get_standing",
    "list_standing",
    "restart_standing",
    "say_standing",
    "start_standing",
    "stop_standing",
]

#: The verbs the control surfaces accept.
CONTROL_VERBS = ("start", "stop", "restart")

#: What every standing session is told before the operator's own brief. Not
#: configurable, and deliberately so (design D7): it states the boundary — you
#: own no work item — and a template key would exist only to let it be deleted.
#: The same reasoning ``$interaction_directive`` already follows for work-item
#: prompts, where a custom template that omits the placeholder gets the
#: directive appended anyway.
_DIRECTIVE = """You are **{name}**, a the-loop *standing session*.

A standing session is not a work item's session. You were started by
`the-loop start` (or by an operator's `the-loop standing start`), you own no
ticket, no spec chain and no pull request, and you finish when an operator stops
you rather than when something is delivered.

What that means concretely:

- **Do not answer a phase-selection gate, approve a phase, or post a control
  keyword (`the-loop start`/`stop`/`pause`/`resume`) on any ticket.** Those are a
  named human's declarations; a session with no work item has no standing to make
  them, and posting one would arm or steer somebody else's work item.
- **Do not open pull requests or push branches** unless your operator asks you to
  in this conversation.
- You may **read** freely — `the-loop sessions list`, `the-loop status`,
  `the-loop events`, `the-loop graph show`, the GitHub surfaces — and report what
  you find.
- Every comment you do post carries the loop-prevention marker
  `<!-- the-loop:agent-comment -->` and a short visible attribution line, exactly
  as a work-item session's would.

**Where your operator speaks to you:** {surfaces}. There is no ticket to comment
on, so a question you ask into the void is never answered — say what you need on
the surfaces above and wait.
"""


def _layout(config: Optional[dict] = None):
    return layout_from_config(config or {})


def _routing(config: Optional[dict]) -> dict:
    routing = (config or {}).get("routing") or {}
    return routing if isinstance(routing, dict) else {}


def _registry(config: Optional[dict], registry_dir: str = "") -> StandingRegistry:
    return StandingRegistry(registry_dir or _layout(config).standing_dir)


def _tmux_config(config: Optional[dict]) -> TmuxConfig:
    return TmuxConfig.from_mapping(_routing(config).get("tmux") or {})


def _runner(config: Optional[dict]) -> TmuxRunner:
    return TmuxRunner(remain_on_exit=_tmux_config(config).remain_on_exit)


def _local_actor() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 — no controlling user (container/cron)
        return ""


def _adapter(entry: StandingSession, config: Optional[dict]) -> HarnessAdapter:
    """The harness adapter for ``entry``, carrying its own extra args.

    Trust and plugin preparation come from ``routing.harnessTrust`` /
    ``routing.harnessPlugins`` unchanged: a standing session sits on the same
    workspace-trust and plugin-enablement problem every unattended spawn has
    (issue-90, issue-143), and the-loop must not widen permissions here any more
    than it does there.
    """
    routing = _routing(config)
    adapters = build_adapters(
        harness_args={entry.harness: list(entry.harness_args)},
        trust=TrustConfig.from_mapping(routing.get("harnessTrust") or {}),
        plugins=PluginConfig.from_mapping(routing.get("harnessPlugins") or {}),
    )
    adapter = adapters.get(entry.harness)
    if adapter is None:
        raise ValueError(
            f"unknown harness {entry.harness!r} for standing session "
            f"{entry.name!r} (one of {', '.join(sorted(adapters))})"
        )
    return adapter


def _surfaces(entry: StandingSession, config: Optional[dict]) -> str:
    """Where this session's operator can reach it — rendered into the directive."""
    where = [
        f"the control plane (`the-loop standing say {entry.name} --text …`, or "
        "`POST /api/v1/standing-sessions/say`)",
        f"an attached terminal (`tmux attach -t {entry.tmux_target}`)",
    ]
    if entry.slack.enabled and _slack_enabled(config):
        where.append("the Slack thread this session was announced in")
    return "; ".join(where)


def _slack_enabled(config: Optional[dict]) -> bool:
    channels = (config or {}).get("channels") or {}
    slack = (channels.get("slack") or {}) if isinstance(channels, dict) else {}
    return bool(isinstance(slack, dict) and slack.get("enabled"))


def _boot_prompt(entry: StandingSession, config: Optional[dict]) -> str:
    """The directive, then the operator's own brief. Never the other way round."""
    directive = _DIRECTIVE.format(
        name=entry.name, surfaces=_surfaces(entry, config)
    ).strip()
    brief = entry.boot_text().strip()  # ValueError on an unreadable promptFile
    if not brief:
        return directive
    return f"{directive}\n\n---\n\n{brief}"


def _tolerant_config(config: Optional[dict]) -> Optional[StandingConfig]:
    """The declaration, or ``None`` when it cannot be parsed — for ``stop`` only.

    Every other verb lets :meth:`StandingConfig.from_mapping` raise: a read that
    quietly reports nothing, or a start that quietly starts nothing, is a config
    error an operator never sees. ``stop`` is the exception because it is the
    **recovery** verb — it works off the registry, not the declaration, and an
    operator whose config is broken still has to be able to stop the sessions it
    started before it broke.
    """
    try:
        return StandingConfig.from_mapping(config)
    except ValueError as exc:
        logger.warning("standingSessions is malformed (%s); stopping by registry", exc)
        return None


# -- reads ---------------------------------------------------------------------


def _row(
    name: str,
    entry: Optional[StandingSession],
    record: Optional[StandingRecord],
    running: bool,
) -> Dict[str, Any]:
    return {
        "name": name,
        "declared": entry is not None,
        "description": entry.description if entry else "",
        "autoStart": bool(entry.auto_start) if entry else False,
        "harness": (record.harness if record else (entry.harness if entry else "")),
        "cwd": (record.cwd if record and record.cwd else (entry.cwd if entry else "")),
        "tmuxTarget": tmux_target_for(name),
        "ref": standing_ref(name),
        "status": record.status if record else "absent",
        "running": running,
        "harnessSessionId": record.harness_session_id if record else "",
        "slackChannel": record.slack_channel if record else "",
        "slackThread": record.slack_thread if record else "",
        "startedAt": record.started_at if record else "",
        "lastMessageAt": record.last_message_at if record else "",
    }


def list_standing(
    config: Optional[dict] = None, registry_dir: str = ""
) -> List[Dict[str, Any]]:
    """One row per declared **or** recorded standing session, merged by name.

    Both halves are reported, because both are real: a declared session that has
    never run is what ``start`` will bring up, and a recorded one that is no
    longer declared is a live process an operator still has to stop.

    ``ValueError`` when the block cannot be parsed. A read that answered "no
    standing sessions" for a config with a typo in it would be the worst of both
    worlds — a wrong answer that looks like a fact.
    """
    parsed = StandingConfig.from_mapping(config)
    entries = {entry.name: entry for entry in parsed.sessions}
    registry = _registry(config, registry_dir)
    records = {record.name: record for record in registry.list()}
    runner = _runner(config)
    rows = []
    for name in sorted(set(entries) | set(records)):
        record = records.get(name)
        running = bool(record) and runner.has_live_session(tmux_target_for(name))
        rows.append(_row(name, entries.get(name), record, running))
    return rows


def get_standing(
    name: str, config: Optional[dict] = None, registry_dir: str = ""
) -> Dict[str, Any]:
    """One session's row. ``LookupError`` when it is neither declared nor recorded."""
    for row in list_standing(config, registry_dir):
        if row["name"] == name:
            return row
    raise LookupError(
        f"no standing session {name!r} — it is neither declared in "
        "standingSessions.sessions nor recorded as started"
    )


# -- start ---------------------------------------------------------------------


def _outcome(row: Dict[str, Any], outcome: str, detail: str = "") -> Dict[str, Any]:
    row["outcome"] = outcome
    row["detail"] = detail
    return row


def _prepare_environment(adapter: HarnessAdapter, entry: StandingSession) -> None:
    """Pre-seed the harness's own config for ``entry.cwd`` — best-effort.

    The dispatcher's rule (issue-90), for the same reason: a config-write hiccup
    must not stop the session starting, and a failure degrades to exactly the
    pre-issue-90 behaviour — a session that may stop on an interactive dialog —
    which is loud in both logs and the event log.
    """
    try:
        result = adapter.prepare_environment(entry.cwd)
    except Exception as exc:  # noqa: BLE001 — an adapter bug never blocks a start
        result = TrustResult(ok=False, error=str(exc))
    if not result.ok:
        logger.warning(
            "could not prepare the %s environment for standing session %s: %s — "
            "the session may stop on an interactive dialog",
            adapter.name or adapter.binary,
            entry.name,
            result.error,
        )
        eventlog.emit(
            "workspace.trust_failed",
            level="warning",
            standing=entry.name,
            harness=adapter.name or adapter.binary,
            cwd=entry.cwd,
            error=result.error,
        )


def _start_one(
    entry: StandingSession,
    config: Optional[dict],
    registry: StandingRegistry,
    runner: TmuxRunner,
) -> Dict[str, Any]:
    record = registry.read(entry.name)
    target = entry.tmux_target
    state = runner.session_state(target)
    row = _row(entry.name, entry, record, running=state == SESSION_LIVE)

    if state == SESSION_UNKNOWN:
        # tmux did not answer. Never read silence as absence (issue-146): a spawn
        # on a busy server is how a live session gets collided with.
        return _outcome(
            row,
            "failed",
            f"tmux did not answer whether {target} exists; not spawning over it",
        )
    if state == SESSION_LIVE:
        if record is None:
            # A live pane the-loop cannot account for — the work-item spawn
            # path's refusal, for the same reason: there is nothing here to talk
            # to, and killing a running agent is worse than refusing.
            eventlog.emit(
                "standing.spawn_failed",
                level="error",
                standing=entry.name,
                tmux_target=target,
                error="tmux session exists but the-loop has no record for it",
            )
            return _outcome(
                row,
                "failed",
                f"a tmux session named {target} exists but the-loop has no record "
                f"of it — inspect it with `tmux attach -r -t {target}`, then either "
                f"`tmux kill-session -t {target}` or leave it be",
            )
        if not record.is_running:
            record.status = RUNNING
            registry.write(record)
        return _outcome(_row(entry.name, entry, record, True), "already-running")
    if state == SESSION_DEAD:
        # The session exists with every pane dead — a retained corpse
        # (`remain-on-exit`). Nothing is running in it, so clearing it costs
        # nothing but the scrollback, record or no record. Only a LIVE occupant
        # is refused above.
        runner.kill_target(target)

    try:
        prompt = _boot_prompt(entry, config)
    except ValueError as exc:
        eventlog.emit(
            "standing.spawn_failed",
            level="error",
            standing=entry.name,
            error=str(exc),
        )
        return _outcome(row, "failed", str(exc))

    cwd = str(Path(entry.cwd).expanduser())
    if not os.path.isdir(cwd):
        detail = (
            f"cwd {entry.cwd!r} is not a directory; a standing session is never "
            "spawned into a directory that is not there"
        )
        eventlog.emit(
            "standing.spawn_failed", level="error", standing=entry.name, error=detail
        )
        return _outcome(row, "failed", detail)

    try:
        adapter = _adapter(entry, config)
    except ValueError as exc:
        return _outcome(row, "failed", str(exc))
    if not adapter.is_available():
        detail = (
            f"harness CLI {adapter.binary!r} not found on PATH — install it or "
            f"point the {entry.harness} adapter at the binary"
        )
        eventlog.emit(
            "standing.spawn_failed",
            level="error",
            standing=entry.name,
            harness=entry.harness,
            error=detail,
        )
        return _outcome(row, "failed", detail)
    _prepare_environment(adapter, entry)

    tmux = _tmux_config(config)
    resumed = False
    session_id = record.harness_session_id if record else ""
    if session_id and tmux.resume_on_respawn:
        result = runner.spawn_in(
            target,
            adapter,
            prompt,
            cwd=cwd,
            session_id=session_id,
            resume=True,
        )
        if result.ok and runner.survived(target, tmux.resume_probe_seconds):
            resumed = True
        else:
            # `claude --resume <unknown-id>` exits in well under a second, so a
            # resume that did not take is a corpse, not a session. Fall back
            # rather than register it (the issue-89 rule).
            eventlog.emit(
                "standing.resume_failed",
                level="warning",
                standing=entry.name,
                harness_session_id=session_id,
                error=result.error or "the resumed pane did not survive the probe",
            )
            runner.kill_target(target)
            session_id = ""
    if not resumed:
        session_id = str(uuid.uuid4())
        try:
            result = runner.spawn_in(
                target, adapter, prompt, cwd=cwd, session_id=session_id
            )
        except UnsupportedRunnerError as exc:
            return _outcome(row, "failed", str(exc))
        if not result.ok:
            eventlog.emit(
                "standing.spawn_failed",
                level="error",
                standing=entry.name,
                harness=entry.harness,
                tmux_target=target,
                error=result.error,
            )
            return _outcome(row, "failed", result.error)

    record = registry.write(
        StandingRecord(
            name=entry.name,
            harness=entry.harness,
            harness_session_id=session_id,
            cwd=cwd,
            tmux_target=target,
            status=RUNNING,
            created_at=record.created_at if record else "",
            started_at=utcnow(),
            last_message_at=record.last_message_at if record else "",
            slack_channel=record.slack_channel if record else "",
            slack_thread=record.slack_thread if record else "",
        )
    )
    eventlog.emit(
        "standing.resumed" if resumed else "standing.started",
        standing=entry.name,
        harness=entry.harness,
        harness_session_id=session_id,
        tmux_target=target,
        cwd=cwd,
    )
    _announce(entry, record, registry, config)
    return _outcome(
        _row(entry.name, entry, record, True),
        "resumed" if resumed else "started",
        f"{'resumed' if resumed else 'started'} {target} "
        f"({entry.harness} {session_id})",
    )


def _announce(
    entry: StandingSession,
    record: StandingRecord,
    registry: StandingRegistry,
    config: Optional[dict],
) -> None:
    """Post the session's Slack announcement and bind the thread it starts.

    Best-effort by contract (R4.5): a Slack workspace that is unreachable, a
    channel the bot is not in, or a channels block that is off, all leave the
    session up. The thread is bound under ``standing:<name>``, which is the whole
    of the Slack integration — replies in it come back through the pipeline that
    already exists.
    """
    if not entry.slack.enabled or not _slack_enabled(config):
        return
    if record.slack_thread:
        return  # already has a thread; a restart keeps talking in the same one
    try:
        from dataclasses import replace as _replace

        from ..channels.base import OutboundEvent
        from ..channels.slack import (
            SlackBotChannel,
            SlackChannelConfig,
            slack_state_path,
        )

        slack_config = SlackChannelConfig.from_mapping(config)
        if entry.slack.channel:
            slack_config = _replace(slack_config, channel=entry.slack.channel)
        channel = SlackBotChannel(slack_config, slack_state_path(config))
        result = channel.post(
            OutboundEvent(
                event_type="standing.started",
                work_item=standing_ref(entry.name),
                text=(
                    f"the-loop standing session `{entry.name}` is up "
                    f"({entry.harness}). Reply in this thread to talk to it — "
                    "replies from an authorized member are pasted straight into "
                    "its terminal."
                ),
                detail={"harness": entry.harness, "tmux": entry.tmux_target},
            )
        )
    except Exception as exc:  # noqa: BLE001 — the channel never gates the session
        logger.warning(
            "standing session %s: Slack announcement failed: %s", entry.name, exc
        )
        eventlog.emit(
            "standing.announce_failed",
            level="warning",
            standing=entry.name,
            error=str(exc),
        )
        return
    if not result.ok or not result.thread:
        eventlog.emit(
            "standing.announce_failed",
            level="warning",
            standing=entry.name,
            error=result.error or "the channel returned no thread",
        )
        return
    record.slack_thread = result.thread
    record.slack_channel = slack_config.channel
    registry.write(record)
    eventlog.emit(
        "standing.announced",
        standing=entry.name,
        channel=result.channel,
        thread=result.thread,
    )


def start_standing(
    name: str = "",
    config: Optional[dict] = None,
    auto_only: bool = False,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Start one declared session, or every declared one when ``name`` is empty.

    ``auto_only`` narrows "every" to the ``autoStart`` entries — what
    ``the-loop start`` asks for. Idempotent: a session whose pane is alive is
    reported ``already-running`` and is not touched.

    ``ValueError`` when the block cannot be parsed, and ``LookupError`` when
    ``name`` is not declared: a start that silently started nothing is how a
    config typo becomes a supervisor that was never watching.
    """
    parsed = StandingConfig.from_mapping(config)
    entries = list(parsed.sessions)
    if name:
        entry = parsed.get(name)
        if entry is None:
            raise LookupError(
                f"no standing session {name!r} is declared in standingSessions.sessions"
            )
        entries = [entry]
    elif auto_only:
        entries = [entry for entry in entries if entry.auto_start]
    registry = _registry(config, registry_dir)
    runner = _runner(config)
    rows = [_start_one(entry, config, registry, runner) for entry in entries]
    ok = all(
        row["outcome"] in ("started", "resumed", "already-running") for row in rows
    )
    return {"sessions": rows, "ok": ok}


# -- stop ----------------------------------------------------------------------


def _stop_one(
    name: str,
    entry: Optional[StandingSession],
    record: Optional[StandingRecord],
    config: Optional[dict],
    registry: StandingRegistry,
    runner: TmuxRunner,
) -> Dict[str, Any]:
    target = tmux_target_for(name)
    if record is None:
        # Nothing the-loop started. It will not signal processes in a tmux
        # session it cannot account for — the same rule the start path refuses
        # on, and the remedy is the same: `tmux kill-session -t <target>`.
        return _outcome(
            _row(name, entry, None, False),
            "not-running",
            "the-loop has no record of this session; nothing of its own to stop",
        )
    if not runner.has_session(target):
        if record and record.is_running:
            record.status = STOPPED
            registry.write(record)
        return _outcome(_row(name, entry, registry.read(name), False), "not-running")
    # SIGTERM the harness first and only then kill the tmux session: Claude Code
    # flushes its conversation on exit, and a `kill-session` straight to SIGHUP
    # is how a resumable id becomes an unresumable one (design D4).
    tmux = _tmux_config(config)
    runner.terminate_harness_in(
        target, standing_ref(name), grace=tmux.harness_kill_grace_seconds
    )
    result = runner.kill_target(target)
    if record:
        record.status = STOPPED
        registry.write(record)
    if not result.ok:
        eventlog.emit(
            "standing.stop_failed",
            level="warning",
            standing=name,
            tmux_target=target,
            error=result.error,
        )
        return _outcome(_row(name, entry, record, False), "failed", result.error)
    eventlog.emit("standing.stopped", standing=name, tmux_target=target)
    return _outcome(_row(name, entry, record, False), "stopped", f"stopped {target}")


def stop_standing(
    name: str = "", config: Optional[dict] = None, registry_dir: str = ""
) -> Dict[str, Any]:
    """Stop one session, or every **recorded** one when ``name`` is empty.

    Reading the registry rather than the config is what makes R2.6 fall out: a
    session disabled or undeclared *after* it was started is still stoppable,
    the same property ``stop_all`` gives the services — and why this is the one
    verb that survives a config it cannot parse (see :func:`_tolerant_config`).
    """
    parsed = _tolerant_config(config)
    entries = {entry.name: entry for entry in (parsed.sessions if parsed else ())}
    registry = _registry(config, registry_dir)
    records = {record.name: record for record in registry.list()}
    runner = _runner(config)
    # Records, not the declaration: `stop` releases what the-loop started, and a
    # declared entry that was never started has nothing to release.
    names = [name] if name else sorted(records)
    rows = [
        _stop_one(one, entries.get(one), records.get(one), config, registry, runner)
        for one in names
    ]
    ok = all(row["outcome"] in ("stopped", "not-running") for row in rows)
    return {"sessions": rows, "ok": ok}


def restart_standing(
    name: str, config: Optional[dict] = None, registry_dir: str = ""
) -> Dict[str, Any]:
    """Stop then start one session, keeping its conversation."""
    if not name:
        raise ValueError("restart names one standing session; it has no 'all' form")
    stopped = stop_standing(name, config, registry_dir)
    started = start_standing(name, config, registry_dir=registry_dir)
    return {
        "sessions": started["sessions"],
        "ok": bool(stopped["ok"] and started["ok"]),
        "stopped": stopped["sessions"],
    }


def control_standing(
    name: str, verb: str, config: Optional[dict] = None, registry_dir: str = ""
) -> Dict[str, Any]:
    """``start`` / ``stop`` / ``restart`` by name — the one control entry point."""
    if verb not in CONTROL_VERBS:
        raise ValueError(f"unknown verb {verb!r} (one of {', '.join(CONTROL_VERBS)})")
    if verb == "start":
        return start_standing(name, config, registry_dir=registry_dir)
    if verb == "stop":
        return stop_standing(name, config, registry_dir=registry_dir)
    return restart_standing(name, config, registry_dir=registry_dir)


# -- say -----------------------------------------------------------------------


def _framed(name: str, text: str, actor: str) -> str:
    who = f" ({actor})" if actor else ""
    return f"Message from your operator{who} to standing session `{name}`:\n\n{text}"


def say_standing(
    name: str,
    text: str,
    actor: str = "",
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Paste ``text`` into a running standing session and submit it.

    Fail-closed like ``sessions reply``: a message answers a session that
    exists, so it must never *create* one. An unknown name, a stopped session or
    a dead pane are refusals naming ``the-loop standing start <name>``.

    ``actor`` is whatever the caller claims — recorded for the audit trail, never
    trusted as authentication (decision-059's boundary is unchanged here).
    """
    if not text or not text.strip():
        raise ValueError("the message is empty; nothing to deliver")
    registry = _registry(config, registry_dir)
    record = registry.read(name)
    if record is None:
        raise LookupError(
            f"no standing session {name!r} has been started — a message never "
            f"spawns one; run `the-loop standing start {name}` first"
        )
    runner = _runner(config)
    target = record.tmux_target
    if not record.is_running or not runner.has_live_session(target):
        raise LookupError(
            f"standing session {name!r} has no live tmux pane to paste into — a "
            f"message never respawns one; run `the-loop standing start {name}` first"
        )
    result = runner.deliver_to(target, _framed(name, text, actor))
    if not result.ok:
        return {
            "name": name,
            "delivered": False,
            "exitCode": 1,
            "messages": [
                {
                    "stream": "err",
                    "text": f"error: could not deliver the message: {result.error}",
                }
            ],
        }
    record.last_message_at = utcnow()
    registry.write(record)
    eventlog.emit(
        "standing.said",
        standing=name,
        tmux_target=target,
        actor=actor or _local_actor() or None,
    )
    return {
        "name": name,
        "delivered": True,
        "exitCode": 0,
        "messages": [
            {"stream": "out", "text": f"delivered into {target} (standing.said)"}
        ],
    }
