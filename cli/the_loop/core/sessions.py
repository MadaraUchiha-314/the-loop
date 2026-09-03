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
import json
import logging
import os
import re
import shutil
import uuid
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .. import cli_config, eventlog
from ..authz import mark_self_authored
from ..cleanup import SESSION, TMUX, WORKSPACE
from ..comments import post_issue_comment, post_issue_comment_with_url
from ..control import (
    CLEANUP,
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

logger = logging.getLogger("the-loop.core.sessions")

CONTROL_VERBS = (START, PAUSE, RESUME, STOP, CLEANUP)

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
    from ..poller.daemon import _build_dispatcher

    routing = dict(_routing(config))
    routing["registryDir"] = registry_dir
    # The config this call was given, never the default path (the `_routing`
    # rule): the opener (issue-317) reads it per call through the getter.
    dispatcher, resolved = _build_dispatcher(
        routing,
        _layout(config),
        cli_config_getter=(lambda: dict(config)) if config else None,
    )
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


# -- transcript (issue-209) ----------------------------------------------------


def _claude_projects_root() -> Path:
    """Where Claude Code keeps per-project session transcripts.

    ``CLAUDE_CONFIG_DIR`` is honoured because it is the *harness's* own
    relocation mechanism — the-loop reads what the harness reads, and adds no
    config key of its own (NFR2).
    """
    base = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(base) / "projects"


def _project_dir_name(cwd: str) -> str:
    """``cwd`` as Claude Code spells its project directory.

    Every character outside ``[A-Za-z0-9]`` becomes ``-``, one for one —
    verified against a real installation's layout (``/home/user/the-loop`` →
    ``-home-user-the-loop``); consecutive non-alphanumerics are NOT collapsed
    into one dash.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def _transcript_endpoint(
    registry: SessionRegistry, work_item: WorkItemRef
) -> Optional[Session]:
    """The endpoint whose transcript ``work_item`` names — closed included.

    Unlike dispatch resolution (``record_owning``), a **closed** session is a
    valid answer here: the transcript file outlives the registration, and
    reading what a finished agent did is the review use case (R1.4). Same
    cheapest-first shape: the ref's own record by path, then the scan for a
    record holding it as a pull-request endpoint.
    """
    record = registry.find_by_work_item(work_item, include_closed=True)
    if record is not None:
        endpoint = record.endpoint_for(work_item)
        if endpoint is not None:
            return endpoint
    for record in registry.list_sessions():
        endpoint = record.endpoint_for(work_item)
        if endpoint is not None:
            return endpoint
    return None


def _resolve_transcript(root: Path, candidate: Path, sid: str) -> Optional[Path]:
    """The real file to serve, or ``None`` — fail-closed containment (R2.1).

    The resolved path (symlinks followed) must sit inside the resolved projects
    root, so a crafted registry record or a symlink planted in the root reads
    as "no transcript", indistinguishable from a missing file. When the derived
    directory misses, the root's immediate subdirectories are scanned for the
    session's file (R1.2): a munge-scheme drift between harness versions
    degrades to one directory listing, not a 404. Session ids are UUIDs, so a
    collision across projects is not a practical concern.
    """
    try:
        resolved_root = root.resolve()
    except OSError:  # pragma: no cover — an unresolvable HOME
        return None
    candidates = [candidate]
    if not candidate.is_file() and root.is_dir():
        candidates += sorted(
            child / f"{sid}.jsonl" for child in root.iterdir() if child.is_dir()
        )
    for option in candidates:
        if not option.is_file():
            continue
        resolved = option.resolve()
        if resolved.is_relative_to(resolved_root) and resolved.is_file():
            return resolved
    return None


def _tail_lines(path: Path, tail: int) -> Tuple[int, List[str]]:
    """``(total non-blank lines, the last ``tail`` of them)`` in one pass.

    The deque is the only buffer (NFR3): ``tail: 0`` means keep everything, and
    is the sole way the whole file ends up in memory. Undecodable bytes are
    replaced rather than failing the read — the transcript is another tool's
    output, and refusing to serve it over one byte helps nobody.
    """
    total = 0
    kept: "deque[str]" = deque(maxlen=tail or None)
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            total += 1
            kept.append(line)
    return total, list(kept)


def _transcript_target(
    ref: str,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Tuple[Any, Path]:
    """The endpoint whose transcript this is, and where the file is (issue-209).

    the-loop runs the harness as a CLI in tmux, so a session's turns and tool
    calls are the harness's file, not the service's: for Claude Code,
    ``<projects root>/<munged cwd>/<harnessSessionId>.jsonl`` — both halves
    recorded at registration, so the path is derived, never asked for.

    Fail-closed by design: the plane serves transcripts, not the filesystem. The
    session id is validated before any filesystem touch (a registry record is
    writable through ``POST /sessions/register``), and only a regular
    ``<id>.jsonl`` resolving inside the projects root is ever returned. Every
    refusal is a :class:`LookupError` naming the reason, which the route maps to
    404.

    Split out of :func:`get_transcript` for the stream's transcript watch
    (issue-239), which needs to **stat** this file every tick without reading it.
    One derivation, one set of refusals: a second copy in the broker would be a
    second place for this boundary to be got wrong.
    """
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    endpoint = _transcript_endpoint(registry, work_item)
    if endpoint is None:
        raise LookupError(
            f"no session registered for {work_item.ref}, so no transcript can "
            "be resolved"
        )
    if endpoint.harness != "claude":
        raise LookupError(
            f"no derivable transcript for harness {endpoint.harness!r} — only "
            "Claude Code's JSONL location is documented (Cursor keeps chats in "
            "an undocumented SQLite store)"
        )
    sid = endpoint.harness_session_id
    if not sid:
        # A PR endpoint is linked before its first dispatch assigns it a
        # conversation (issue-172) — a normal state, not a bad record.
        raise LookupError(
            f"no harness conversation recorded for {work_item.ref} yet — the "
            "session id is assigned on first dispatch, so there is no "
            "transcript to resolve"
        )
    if "/" in sid or "\\" in sid or ".." in sid:
        raise LookupError(
            f"the recorded session id for {work_item.ref} is not a derivable "
            "transcript file name"
        )
    root = _claude_projects_root()
    candidate = root / _project_dir_name(endpoint.cwd) / f"{sid}.jsonl"
    path = _resolve_transcript(root, candidate, sid)
    if path is None:
        raise LookupError(
            f"no transcript at {candidate} — the session may not have written one yet"
        )
    return endpoint, path


def transcript_path(
    ref: str,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Path:
    """Where a work item's transcript file is, with every refusal above applied.

    The stream's transcript watch (issue-239) needs to **stat** this file every
    tick without reading it, and must not re-derive the path: one derivation, one
    set of refusals, so the boundary cannot be got wrong in a second place.
    """
    return _transcript_target(ref, config=config, registry_dir=registry_dir)[1]


def get_transcript(
    ref: str,
    tail: int = 200,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """The harness's own transcript for a work item's session (issue-209).

    The path — and every refusal that can stop one being derived — is
    :func:`transcript_path`; this adds the tail and the envelope.

    A read like :func:`get_session` — no ``messages``/``exitCode`` envelope.
    """
    if tail < 0:
        raise ValueError("tail must be >= 0 (0 means the whole file)")
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    endpoint, path = _transcript_target(ref, config=config, registry_dir=registry_dir)
    total, lines = _tail_lines(path, tail)
    entries: List[Dict[str, Any]] = []
    for line in lines:
        try:
            parsed = json.loads(line)
        except ValueError:
            parsed = None
        # A line that is not a JSON object is served, flagged, in place —
        # dropped data is worse than ugly data (R1.1).
        entries.append(parsed if isinstance(parsed, dict) else {"malformed": line})
    return {
        "workItem": work_item.ref,
        "harness": endpoint.harness,
        "harnessSessionId": endpoint.harness_session_id,
        "path": str(path),
        "totalLines": total,
        "truncated": total > len(entries),
        "entries": entries,
    }


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


#: A pull request named by number alone, with or without GitHub's ``#``.
_PR_NUMBER_RE = re.compile(r"^#?(\d+)$")


def _pull_request_ref(work_item: WorkItemRef, given: str) -> WorkItemRef:
    """``given`` as a ref: a bare number is the work item's own repository.

    A bare number is what a session that has just run ``gh pr create`` has to
    hand, and it is resolved against the **work item's** owner/repo/host rather
    than the checkout's — the work item is the thing being linked, and it is the
    only coordinate this call is sure of. A pull request in another repository
    (the multi-repo shape, issue-183) is named by its full ref, which says where
    it belongs and is therefore used unchanged.
    """
    match = _PR_NUMBER_RE.match((given or "").strip())
    if match is None:
        return WorkItemRef.parse(given)  # ValueError on anything else
    number = int(match.group(1))
    if number <= 0:
        raise ValueError(f"pull-request number must be positive, not {number}")
    return replace(work_item, number=number)


def link_pull_request(
    ref: str,
    pull_request: str,
    config: Optional[dict] = None,
    registry_dir: str = "",
) -> Dict[str, Any]:
    """Record that ``pull_request`` delivers ``ref``'s work item (issue-274).

    The binding the router prefers over every inference, written by the one
    component that knows it for certain: the session that just opened the pull
    request. Until this existed the only writer was
    :meth:`~the_loop.webhook.dispatcher.Dispatcher._record_pr_binding`, which
    runs when a routing decision is made — and therefore only once the linkage is
    *already* derivable from the payload. A pull request the-loop authors itself
    carries none of the three derivations (no closing reference, because a spec
    pull request must not close its ticket; ``loop/<id>-…`` rather than the
    ``issue-<n>`` branch convention; a bare mention rather than a closing
    keyword), so its events resolved to the pull request as a work item of its
    own and were refused as unstarted.

    Idempotent, because the authoring step is re-run: a pull request already
    listed is reported and exits 0. A work item with no session record on this
    machine exits 1 and writes nothing — recording an endpoint for a record that
    does not exist would invent a work item.
    """
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    pr = _pull_request_ref(work_item, pull_request)
    if pr.ref == work_item.ref:
        raise ValueError(
            f"{work_item.ref} does not deliver itself; name the pull request "
            "that delivers it"
        )
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    if registry.find_by_work_item(work_item) is None:
        return {
            "workItem": work_item.ref,
            "pullRequest": pr.ref,
            "linked": False,
            "exitCode": 1,
            "messages": [
                {
                    "stream": "err",
                    "text": (
                        f"no session recorded for {work_item.ref} — register the "
                        "session before recording the pull requests it opens"
                    ),
                }
            ],
        }
    linked = registry.link_pull_request(work_item, pr) is not None
    text = (
        f"recorded {pr.ref} as delivering {work_item.ref}"
        if linked
        else f"{pr.ref} is already recorded as delivering {work_item.ref}"
    )
    return {
        "workItem": work_item.ref,
        "pullRequest": pr.ref,
        "linked": linked,
        "exitCode": 0,
        "messages": [{"stream": "out", "text": text}],
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


# -- ask & reply (issue-208) -----------------------------------------------------


def ask_session(
    ref: str, question: str, config: Optional[dict] = None
) -> Dict[str, Any]:
    """Post an agent's question on its work item and record the wait.

    The point of the verb (issue-208): the loop-prevention marker is stamped
    **centrally** (:func:`~the_loop.authz.mark_self_authored`, idempotent)
    instead of each agent being trusted to remember it, and the wait becomes a
    first-class ``session.awaiting_input`` event instead of something the
    control plane infers.

    The event is emitted on the failure path too (at ``warning``): the agent is
    waiting whether or not GitHub was reachable, and when the comment never
    landed, the control plane's reply route is the only surface that can carry
    the answer. The exit code still says the post failed.
    """
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if not question or not question.strip():
        raise ValueError("the question is empty; nothing to ask")
    control = _control_config(config)
    actor = _local_actor()
    # One event on the bus (issue-309): the ledger records it FIRST — the record
    # IS the question comment, marked and enveloped — and then every subscribed
    # channel gets it, best-effort by contract (R1.2): the result computed below
    # never depends on what any channel did. The ledger is built over this
    # verb's own writer so a `gh` binary chosen here is the one used.
    from ..channels.base import Event
    from ..channels.bus import publish as bus_publish
    from ..channels.github import GitHubLedger

    ledger = GitHubLedger(
        dict(config or {}),
        post_comment=lambda item, body, gh_binary="gh": post_issue_comment_with_url(
            item, body, gh_binary=control.gh_binary
        ),
    )
    channel_results = []
    ok, error, url = False, "", ""
    try:
        published = bus_publish(
            Event(
                event_type="session.awaiting_input",
                work_item=work_item.ref,
                text=question,
                detail={"actor": actor},
                source="cli",
            ),
            dict(config or {}),
            ledger=ledger,
        )
        record = published.record
        ok = bool(record and record.ok)
        error = (record.error if record else "") or ""
        url = (record.url if record else "") or ""
        channel_results = published.posts
    except Exception as exc:  # noqa: BLE001 — a channel bug never fails the ask
        logger.warning("channel broadcast failed: %s", exc)
        if not ok:
            ok, error, url = post_issue_comment_with_url(
                work_item, mark_self_authored(question), gh_binary=control.gh_binary
            )
    eventlog.emit(
        "session.awaiting_input",
        level="info" if ok else "warning",
        work_item=work_item.ref,
        question=question,
        actor=actor,
        comment_url=url or None,
        comment_posted=ok,
    )
    messages: List[Dict[str, str]] = []
    if ok:
        where = f" — {url}" if url else ""
        messages.append({"stream": "out", "text": f"asked on {work_item.ref}{where}"})
        for posted in channel_results:
            messages.append(
                {
                    "stream": "out" if posted.ok else "err",
                    "text": (
                        f"also asked on the {posted.channel} channel"
                        if posted.ok
                        else (
                            f"note: the {posted.channel} channel did not take the "
                            f"question ({posted.error}); the work item has it"
                        )
                    ),
                }
            )
        messages.append(
            {
                "stream": "out",
                "text": (
                    "recorded the wait (session.awaiting_input) — now stop and "
                    "wait; the answer arrives as a new event in this session"
                ),
            }
        )
    else:
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"error: could not post the question on {work_item.ref} ({error})"
                ),
            }
        )
        for posted in channel_results:
            if posted.ok:
                messages.append(
                    {
                        "stream": "out",
                        "text": f"still asked on the {posted.channel} channel",
                    }
                )
        messages.append(
            {
                "stream": "err",
                "text": (
                    "recorded the wait anyway (session.awaiting_input, "
                    "comment_posted=false) — an operator can still answer "
                    "through the control plane's reply route"
                ),
            }
        )
    return {
        "workItem": work_item.ref,
        "asked": ok,
        "commentUrl": url,
        "exitCode": 0 if ok else 1,
        "messages": messages,
    }


def reply_session(
    ref: str,
    text: str,
    actor: str = "",
    comment: bool = True,
    config: Optional[dict] = None,
    registry_dir: str = "",
    portable_dir: str = "",
) -> Dict[str, Any]:
    """Deliver an operator's answer into a waiting session's tmux pane (issue-208).

    The ref resolves the way dispatch resolves it (issue-230): the ref's own
    record first, else the record holding it as a **pull-request endpoint** —
    so an inner loop's chat bar reaches that PR's pane, not a 404. A closed PR
    endpoint falls back to the record's own session, the same rule
    ``SessionRegistry.session_for`` applies to events.

    Fail-closed by design: a reply answers an agent that is waiting, so it must
    never *create* one — no session, a paused session, or a dead/absent pane are
    refusals (``LookupError``/``ValueError``, mapped to 404/400 by the API), and
    the dispatcher's respawn machinery is deliberately not invoked.

    ``actor`` is whatever the caller claims — recorded on the event and the
    ticket for the audit trail, never trusted as authentication (the service's
    boundary stays the exposure guard and the deploying gateway, decision-059).
    """
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if not text or not text.strip():
        raise ValueError("the reply text is empty; nothing to deliver")
    registry = SessionRegistry(_registry_dir(config, registry_dir))
    record = registry.record_owning(work_item)
    if record is None:
        raise LookupError(
            f"no session registered for {work_item.ref} — a reply never spawns "
            "one; answer on the ticket, or start the work item first"
        )
    if record.is_paused:
        raise ValueError(
            f"the session for {work_item.ref} is paused and delivery is held; "
            "resume it first"
        )
    session = record.endpoint_for(work_item)
    if session is None or not session.is_live:
        # A PR whose endpoint closed with its pull request falls back to the
        # work item's own session — still the one that owns the work.
        session = record
    if session.is_paused:
        raise ValueError(
            f"the session for {work_item.ref} is paused and delivery is held; "
            "resume it first"
        )
    result = TmuxRunner().deliver(session, _framed_reply(work_item, text, actor))
    if result.session_missing:
        raise LookupError(
            f"the session for {work_item.ref} has no live tmux pane to paste "
            "into — a reply never respawns one; answer on the ticket, or "
            "start/resume the work item first"
        )
    messages: List[Dict[str, str]] = []
    if not result.ok:
        # Transient tmux trouble (busy server, timeout): the caller may retry.
        messages.append(
            {
                "stream": "err",
                "text": f"error: could not deliver the reply: {result.error}",
            }
        )
        return {
            "workItem": work_item.ref,
            "delivered": False,
            "exitCode": 1,
            "messages": messages,
        }
    eventlog.emit("session.reply_sent", work_item=work_item.ref, actor=actor or None)
    messages.append(
        {
            "stream": "out",
            "text": (
                f"delivered the reply into {session.tmux_target} (session.reply_sent)"
            ),
        }
    )
    if comment:
        posted, error = post_issue_comment(
            work_item,
            _reply_report(text, actor),
            gh_binary=_control_config(config).gh_binary,
        )
        if posted:
            messages.append(
                {"stream": "out", "text": f"recorded the reply on {work_item.ref}"}
            )
        else:
            messages.append(
                {
                    "stream": "err",
                    "text": (
                        f"note: could not record the reply on {work_item.ref} "
                        f"({error}); it was still delivered"
                    ),
                }
            )
    return {
        "workItem": work_item.ref,
        "delivered": True,
        "exitCode": 0,
        "messages": messages,
    }


def _framed_reply(work_item: WorkItemRef, text: str, actor: str) -> str:
    """The pasted prompt: the operator's text under a short provenance header."""
    who = f" ({actor})" if actor else ""
    return (
        f"Reply from the operator via the-loop control plane{who} to your "
        f"question on {work_item.ref}:\n\n{text}"
    )


def _reply_report(text: str, actor: str) -> str:
    """The ticket's record of the delivery — the-loop's own report, marked.

    The marker is licensed here because the-loop composed this comment (a
    delivery report, quoting the operator the way control-verb comments quote
    their actor) — and it is load-bearing: an unmarked copy of the answer would
    be forwarded by the poller into the very session the reply route already
    delivered it to.
    """
    who = f" from `{actor}`" if actor else ""
    quoted = "\n".join(f"> {line}" for line in (text.splitlines() or [""]))
    return mark_self_authored(
        f"🗣️ **the-loop** delivered a reply{who} into this work item's session "
        "via the control plane (`POST /api/v1/sessions/reply`):\n\n" + quoted
    )


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

    A **disarming** verb (pause/stop/cleanup) is recorded whether or not there
    was anything to act on, so a stopped or torn-down work item does not
    re-spawn on the next event. An **arming** one (start/resume) is recorded only
    when it actually acted (owner decision on PR #107).
    """
    if verb not in CONTROL_VERBS:
        raise ValueError(f"unknown control verb {verb!r} (one of {CONTROL_VERBS})")
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref

    registry_dir = _registry_dir(config, registry_dir)
    store = _control_store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []

    if verb in (PAUSE, STOP, CLEANUP):
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

    if verb == CLEANUP:
        return _cleanup(work_item, config, registry_dir, portable_dir, messages)

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


def _cleanup(
    work_item: WorkItemRef,
    config: Optional[dict],
    registry_dir: str,
    portable_dir: str,
    messages: List[Dict[str, str]],
) -> Tuple[str, int]:
    """Release the work item's local resources, through the *daemon's* dispatcher.

    Not a second teardown implementation: the graph transition, the tmux kills
    and the workspace removal behave exactly as they do for a cleanup issued by
    comment. Reports each irreversible fact on its own line — losing a checkout
    means losing whatever was uncommitted in it, and that is not something an
    operator should have to infer from a summary count.

    Exit code 0 even when nothing was found (issue-186 R4.3): "there is nothing
    of this work item left on this machine" is the state the verb asks for, not
    a failure.
    """
    dispatcher, routing = _dispatcher_for(config, registry_dir, portable_dir)
    try:
        outcome = dispatcher.cleanup_work_item(
            work_item,
            reason="cleanup requested from the CLI",
            actor=_local_actor(),
            source="cli",
        )
    finally:
        dispatcher.stop(timeout=5)

    if TMUX in outcome.removed:
        messages.append(
            {
                "stream": "out",
                "text": (
                    "ended "
                    + ", ".join(outcome.endpoints)
                    + " — their tmux sessions and transcripts are gone"
                ),
            }
        )
    if WORKSPACE in outcome.removed:
        messages.append(
            {
                "stream": "out",
                "text": (
                    f"removed the workspace checkout under {routing.workspace.root} "
                    "— uncommitted work in it is gone"
                ),
            }
        )
    if SESSION in outcome.removed:
        messages.append(
            {"stream": "out", "text": "removed the machine-local session record"}
        )
    for error in outcome.errors:
        messages.append({"stream": "err", "text": f"error: {error}"})
    if not outcome.found:
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"nothing to clean up for {work_item.ref}; recorded the "
                    "request, so it will not spawn on its own"
                ),
            }
        )
        return "nothing-to-clean", 0
    messages.append(
        {
            "stream": "out",
            "text": (
                f"cleaned up {work_item.ref} — its portable record (control, poll, "
                "graph) is kept, and nothing remote was touched"
            ),
        }
    )
    return ("cleaned" if outcome.ok else "partial"), (0 if outcome.ok else 1)


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
