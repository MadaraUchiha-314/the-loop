"""Standing sessions: named harness sessions that belong to no work item (issue-277).

Everything the-loop spawns for delivery work is owned by a ticket — the tmux
name is minted from a :class:`~the_loop.sessions.WorkItemRef`, the registry file
is named after one, and every question the agent asks goes back to the ticket it
came from. A **standing session** is the other kind: declared in the CLI config
under ``standingSessions``, brought up by ``the-loop start``, addressed by
**name**, and talked to on the control plane or in Slack.

This module owns the three things a standing session *is* before anything runs:
its **ref grammar** (``standing:<name>`` — the string the channels pipeline uses
to tell the two namespaces apart), its **declaration** (:class:`StandingConfig`,
parsed from the CLI config) and its **record** (:class:`StandingRegistry`, one
JSON file per name under ``<state.root>/local/standing/``). What a standing
session *does* is :mod:`the_loop.core.standing`'s.

The separation from :mod:`the_loop.sessions.registry` is deliberate and is the
security property of the feature: nothing in the router, the dispatcher or the
session registry knows the ``standing:`` prefix, so no GitHub event has a path
into a standing session and no standing session can be mistaken for a work
item's.

Spec: docs/specs/issue-277/design.md §D1, §D3.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger("the-loop.standing")

__all__ = [
    "NAME_RE",
    "STANDING_PREFIX",
    "SlackBinding",
    "StandingConfig",
    "StandingRecord",
    "StandingRegistry",
    "StandingSession",
    "parse_standing_ref",
    "standing_ref",
    "tmux_target_for",
    "utcnow",
]

#: The prefix that marks a standing session's ref. Chosen so it cannot be read as
#: a work-item ref: ``WorkItemRef.parse`` requires ``<owner>/<repo>#<number>``
#: after the provider, and a standing ref has neither a ``/`` nor a ``#``.
STANDING_PREFIX = "standing:"

#: What a standing session may be called. Narrow on purpose: the name is
#: interpolated into a tmux session name and into a file name, so it is
#: lowercase alphanumerics and hyphens, and it may not start with a hyphen (a
#: leading ``-`` reads as an option to every CLI it is passed to).
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

#: Statuses a record can hold. ``running`` means the-loop last spawned it and did
#: not stop it; whether a pane is alive *now* is tmux's answer, never the file's.
RUNNING = "running"
STOPPED = "stopped"


def standing_ref(name: str) -> str:
    """``standing:<name>`` — the string a channel binding carries."""
    return f"{STANDING_PREFIX}{name}"


def parse_standing_ref(ref: str) -> Optional[str]:
    """The session name in ``ref``, or ``None`` when it is not a standing ref.

    The **only** place a ``standing:`` string is recognised. Two callers, both in
    the inbound channels pipeline; keeping it to one function is what makes "no
    work-item path knows this prefix" checkable rather than asserted.
    """
    text = (ref or "").strip()
    if not text.startswith(STANDING_PREFIX):
        return None
    name = text[len(STANDING_PREFIX) :]
    return name if NAME_RE.match(name) else None


def tmux_target_for(name: str) -> str:
    """The tmux session name hosting ``name``.

    ``loop-standing-<name>`` cannot collide with a work item's ``loop-<slug>``:
    a slug is ``<provider>-<path…>-<number>``, so reaching this string would take
    a provider called ``standing``, and there is none. It is inside
    ``runner._LOOP_TARGET_RE``, so the guard that stops the-loop signalling
    processes in a tmux session it did not create applies unchanged, and it
    carries no ``.``/``:`` so tmux keeps the name it is given (issue-154).
    """
    return f"loop-standing-{name}"


def utcnow() -> str:
    """The timestamp format every the-loop record uses. Public: the core module
    stamps records with it, and two spellings of "now" in one store is how a
    listing ends up sorting wrongly."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# -- the declaration -------------------------------------------------------------


@dataclass(frozen=True)
class SlackBinding:
    """One session's ``slack`` block: whether it has a thread, and in which channel."""

    enabled: bool = False
    channel: str = ""  # "" = the central channels.slack.channel


@dataclass(frozen=True)
class StandingSession:
    """One declared standing session, with the ``routing`` defaults already applied."""

    name: str
    description: str = ""
    harness: str = "claude"
    harness_args: Tuple[str, ...] = ()
    cwd: str = "."
    prompt: str = ""
    prompt_file: str = ""
    auto_start: bool = True
    slack: SlackBinding = field(default_factory=SlackBinding)

    @property
    def tmux_target(self) -> str:
        return tmux_target_for(self.name)

    def boot_text(self) -> str:
        """The operator's own prompt text — from ``prompt`` or ``promptFile``.

        Raises ``ValueError`` naming the path when ``promptFile`` cannot be read:
        a session whose brief is missing is started wrong, not started blank.
        """
        if self.prompt:
            return self.prompt
        if not self.prompt_file:
            return ""
        try:
            return Path(self.prompt_file).expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(
                f"standing session {self.name!r}: cannot read promptFile "
                f"{self.prompt_file!r}: {exc}"
            ) from None


@dataclass(frozen=True)
class StandingConfig:
    """The parsed ``standingSessions`` block.

    :meth:`from_mapping` **raises** on a block it cannot make sense of, rather
    than resolving the ambiguity itself (requirements R1.1, R1.3, R1.5). Callers
    that must survive a bad config — the lifecycle rows, ``standing list`` —
    catch it and report the message; none of them guesses.
    """

    enabled: bool = False
    sessions: Tuple[StandingSession, ...] = ()

    def get(self, name: str) -> Optional[StandingSession]:
        for session in self.sessions:
            if session.name == name:
                return session
        return None

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(session.name for session in self.sessions)

    @classmethod
    def from_mapping(cls, cli_config: Optional[Mapping]) -> "StandingConfig":
        config = dict(cli_config or {})
        block = config.get("standingSessions") or {}
        if not isinstance(block, Mapping):
            raise ValueError(
                "standingSessions: the section is not a mapping; expected "
                "`enabled` and `sessions`"
            )
        routing = config.get("routing") or {}
        if not isinstance(routing, Mapping):
            routing = {}
        default_harness = str(routing.get("defaultHarness") or "claude")
        harness_args = routing.get("harnessArgs") or {}
        if not isinstance(harness_args, Mapping):
            harness_args = {}
        default_cwd = str(routing.get("spawnWorkdir") or ".")

        entries = block.get("sessions") or []
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
            raise ValueError("standingSessions.sessions: expected a list of entries")
        sessions: List[StandingSession] = []
        seen: Dict[str, int] = {}
        for index, raw in enumerate(entries):
            if not isinstance(raw, Mapping):
                raise ValueError(
                    f"standingSessions.sessions[{index}]: expected a mapping"
                )
            name = str(raw.get("name") or "")
            if not NAME_RE.match(name):
                raise ValueError(
                    f"standingSessions.sessions[{index}]: name {name!r} is not "
                    "lowercase letters/digits/hyphens starting with a letter or "
                    "digit (max 40); the name becomes a tmux session and a file name"
                )
            if name in seen:
                raise ValueError(
                    f"standingSessions.sessions[{index}]: name {name!r} is already "
                    f"declared at sessions[{seen[name]}]; two entries with one name "
                    "have no defined winner"
                )
            seen[name] = index
            prompt = str(raw.get("prompt") or "")
            prompt_file = str(raw.get("promptFile") or "")
            if prompt and prompt_file:
                raise ValueError(
                    f"standingSessions.sessions[{index}] ({name}): declares both "
                    "`prompt` and `promptFile`; there is no precedence between "
                    "them — keep one"
                )
            harness = str(raw.get("harness") or default_harness)
            declared_args = raw.get("harnessArgs")
            if declared_args is None:
                args = tuple(str(a) for a in (harness_args.get(harness) or []))
            elif isinstance(declared_args, Sequence) and not isinstance(
                declared_args, (str, bytes)
            ):
                args = tuple(str(a) for a in declared_args)
            else:
                raise ValueError(
                    f"standingSessions.sessions[{index}] ({name}): harnessArgs "
                    "must be a list of strings"
                )
            slack_raw = raw.get("slack") or {}
            if not isinstance(slack_raw, Mapping):
                raise ValueError(
                    f"standingSessions.sessions[{index}] ({name}): slack must be "
                    "a mapping"
                )
            sessions.append(
                StandingSession(
                    name=name,
                    description=str(raw.get("description") or ""),
                    harness=harness,
                    harness_args=args,
                    cwd=str(raw.get("cwd") or default_cwd),
                    prompt=prompt,
                    prompt_file=prompt_file,
                    auto_start=bool(raw.get("autoStart", True)),
                    slack=SlackBinding(
                        enabled=bool(slack_raw.get("enabled", False)),
                        channel=str(slack_raw.get("channel") or ""),
                    ),
                )
            )
        return cls(enabled=bool(block.get("enabled", False)), sessions=tuple(sessions))


# -- the record ------------------------------------------------------------------


@dataclass
class StandingRecord:
    """What the-loop remembers about one standing session between processes."""

    name: str
    harness: str = "claude"
    harness_session_id: str = ""
    cwd: str = ""
    tmux_target: str = ""
    status: str = RUNNING  # running | stopped
    created_at: str = ""
    started_at: str = ""
    last_message_at: str = ""
    slack_channel: str = ""
    slack_thread: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "harness": self.harness,
            "harnessSessionId": self.harness_session_id,
            "cwd": self.cwd,
            "tmuxTarget": self.tmux_target,
            "status": self.status,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "lastMessageAt": self.last_message_at,
            "slackChannel": self.slack_channel,
            "slackThread": self.slack_thread,
        }

    @classmethod
    def from_dict(cls, data: Mapping) -> "StandingRecord":
        name = str(data.get("name") or "")
        if not NAME_RE.match(name):
            raise ValueError(f"standing record: invalid name {name!r}")
        return cls(
            name=name,
            harness=str(data.get("harness") or "claude"),
            harness_session_id=str(data.get("harnessSessionId") or ""),
            cwd=str(data.get("cwd") or ""),
            # Never trusted from the file: derived from the name, so a
            # hand-edited record cannot aim a kill at another tmux session.
            tmux_target=tmux_target_for(name),
            status=str(data.get("status") or RUNNING),
            created_at=str(data.get("createdAt") or ""),
            started_at=str(data.get("startedAt") or ""),
            last_message_at=str(data.get("lastMessageAt") or ""),
            slack_channel=str(data.get("slackChannel") or ""),
            slack_thread=str(data.get("slackThread") or ""),
        )

    @property
    def is_running(self) -> bool:
        return self.status == RUNNING


class StandingRegistry:
    """File-per-name record store under ``root``, with atomic writes.

    The same discipline as :class:`~the_loop.sessions.SessionRegistry` — tempfile
    plus ``os.replace``, one file per entity, an unreadable file skipped rather
    than fatal — and deliberately none of its shared code: these records key on a
    name, not a ref, and nothing that resolves refs may reach them.
    """

    def __init__(self, root):
        self.root = Path(root)

    def path_for(self, name: str) -> Path:
        if not NAME_RE.match(name or ""):
            raise ValueError(f"invalid standing-session name {name!r}")
        return self.root / f"{name}.json"

    def read(self, name: str) -> Optional[StandingRecord]:
        try:
            raw = json.loads(self.path_for(name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as exc:
            logger.warning("unreadable standing record for %s: %s", name, exc)
            return None
        try:
            return StandingRecord.from_dict(raw)
        except (ValueError, TypeError, AttributeError) as exc:
            logger.warning("unparseable standing record for %s: %s", name, exc)
            return None

    def write(self, record: StandingRecord) -> StandingRecord:
        target = self.path_for(record.name)
        if not record.created_at:
            record.created_at = utcnow()
        record.tmux_target = tmux_target_for(record.name)
        self.root.mkdir(parents=True, exist_ok=True)
        handle, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".tmp")
        try:
            with os.fdopen(handle, "w") as stream:
                json.dump(record.to_dict(), stream, indent=2)
                stream.write("\n")
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except FileNotFoundError:
                pass
            raise
        return record

    def delete(self, name: str) -> bool:
        try:
            self.path_for(name).unlink()
            return True
        except FileNotFoundError:
            return False

    def list(self) -> List[StandingRecord]:
        if not self.root.is_dir():
            return []
        records: List[StandingRecord] = []
        for path in sorted(self.root.glob("*.json")):
            record = self.read(path.stem)
            if record is not None:
                records.append(record)
        return records
