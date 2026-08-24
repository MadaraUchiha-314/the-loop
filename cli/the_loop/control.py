"""Execution control: the keywords an authorized user steers the-loop with.

Before issue-106 the daemon had two gates and no *verb*. ``authorizedUsers``
(:mod:`the_loop.authz`) answers **who** may be an input, and the auto-execute
label answers **which** work items may run autonomously — but nothing answered
*when*, so adding the label was itself an irreversible trigger, and a comment
could only ever become **harness input** (text the agent reads), never an
instruction to the-loop itself.

This module is that missing vocabulary: the session commands — ``start``,
``stop``, ``pause``, ``resume``, plus ``contribute`` (issue-185: start's
sibling that selects the contribution loop), ``do`` (issue-225: the same
sibling one loop over — it selects the ad-hoc loop), ``review`` (issue-279:
the sibling that selects the REVIEW loop — the-loop as the reviewer of a pull
request, not its author) and ``cleanup`` (issue-186: the other end of the life
cycle — reclaim the local resources of a work item that has ended) — declared
in the CLI config (``routing.control.keywords``), recognised in a comment on
the work item or its PR, and *executed by the-loop* rather than forwarded to
the agent. All but ``execute``, ``contribute``, ``do`` and ``review`` are also
available from the CLI (``the-loop sessions start|stop|pause|resume|cleanup``),
which posts the same keyword back to the ticket so the thread stays a complete
record of who asked for what.

## Why the parser is this narrow

Recognising a command in a comment opens a new trust boundary: comment text can
now cause a *daemon action* (spawn/pause/resume/close), not just agent input.
The boundary is kept narrow by construction rather than by review:

* the vocabulary is **fixed and configured** — :func:`parse_command` returns one
  of the declared constants or nothing, never a substring of the body, so no
  payload-derived text can reach an argv, a path, a prompt or a work-item ref
  (the item acted on comes from the router's own extraction);
* a comment carrying **two different** commands is refused outright rather than
  resolved by precedence — a half-"stop" must not be read as a "start";
* it is only ever reached **after** the guards that already exist: the
  self-authored marker check (issue-104) and the authorized-actor check
  (issue-63), both upstream in the router/poller.

The one deliberate looseness: fenced code blocks are not stripped, so a keyword
quoted in a code block still counts. Literal matching is easier to reason about
than a half-markdown parser, and only an authorized user can reach it at all.

## The durable record

:class:`ControlStore` keeps the last command per work item in the ``control``
section of ``<state.root>/portable/<slug>.json`` (issue-128) — the portable half
of that work item's state, beside what the poller has seen and away from the
machine-local session handle. It answers one question for the dispatcher and the
poller — *did an authorized user ask for this work item to be running?* — which
is what makes a start request survive a daemon restart, and what lets
pause/stop land on a work item that has no session yet.

Spec: docs/specs/issue-106/design.md §1.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .authz import mark_self_authored
from .sessions import WorkItemRef
from .state import LegacyLayout
from .workitem import CONTROL, GRAPH, WorkItemStore

logger = logging.getLogger("the-loop.control")

__all__ = [
    "COMMANDS",
    "GRAPH_COMMANDS",
    "SPAWN_COMMANDS",
    "TEARDOWN_COMMANDS",
    "DEFAULT_KEYWORDS",
    "ControlConfig",
    "ControlRecord",
    "ControlResult",
    "ControlStore",
    "command_comment",
    "parse_command",
]

# The nine commands, in the order they are documented. `start`, `resume`,
# `contribute`, `do` and `review` mean "execution should be running"; `pause`
# and `stop` mean it should not. `execute` is different in kind (issue-177): it
# does not touch the session at all — it answers the graph's `phase-selection`
# gate, freezing the set of phases this work item will walk. `contribute`
# (issue-185) arms exactly as `start` does, and additionally selects the
# CONTRIBUTION loop for the work item's outer walk: the-loop joins an existing,
# in-progress item as a contributor rather than owning it from scratch. `do`
# (issue-225) is the same shape one loop over: it arms as `start` does and
# selects the AD-HOC loop — a tactical task that runs no PDLC process at all,
# worked until the requester says it is done. `review` (issue-279) is the shape
# a third time: it arms as `start` does and selects the REVIEW loop — the-loop
# reviews the pull request it was typed on, against an authorized reviewer's
# brief, and changes no code. `cleanup` (issue-186) is the other end of the life
# cycle: the work is over, so reclaim the LOCAL resources the work item
# accumulated — the tmux sessions, the checkout, the machine-local session
# record — and nothing else. All live here because they are **control** words an
# authorized human types on the ticket, so they belong to the same configurable
# vocabulary and the same named-actor authorization.
START, STOP, PAUSE, RESUME, EXECUTE, CONTRIBUTE, CLEANUP, DO, REVIEW = (
    "start",
    "stop",
    "pause",
    "resume",
    "execute",
    "contribute",
    "cleanup",
    "do",
    "review",
)
COMMANDS = (START, STOP, PAUSE, RESUME, EXECUTE, CONTRIBUTE, CLEANUP, DO, REVIEW)

#: Commands the *graph* acts on rather than the session registry. The
#: dispatcher records them and then lets the event through, because the thing
#: that must see the comment is the phase-selection gate.
GRAPH_COMMANDS = (EXECUTE,)

#: Commands whose effect is **destruction of local state** rather than a
#: session transition (issue-186). Named as a set so the dispatcher and the
#: control-plane core branch on a constant rather than a string literal — the
#: one command that removes things should be recognisable as such wherever it
#: is handled.
TEARDOWN_COMMANDS = (CLEANUP,)

# Commands whose effect is "this work item should be running" — what
# ControlStore.start_requested reports on. `contribute` (issue-185), `do`
# (issue-225) and `review` (issue-279) arm like `start`: the loop each selects
# differs, the request to be running does not. `cleanup` is deliberately
# absent, so recording one DISARMS the item exactly as a `stop` does: nothing
# may re-spawn a session for work whose resources have gone.
_ARMING_COMMANDS = (START, RESUME, CONTRIBUTE, DO, REVIEW)

#: The arming commands that may SPAWN a session where none exists — what the
#: dispatcher's spawn seams check. `resume` is deliberately absent: it can only
#: wake something that was paused, never conjure a session (issue-106).
SPAWN_COMMANDS = (START, CONTRIBUTE, DO, REVIEW)

DEFAULT_KEYWORDS: Dict[str, str] = {
    START: "the-loop start",
    STOP: "the-loop stop",
    PAUSE: "the-loop pause",
    RESUME: "the-loop resume",
    EXECUTE: "the-loop execute",
    CONTRIBUTE: "the-loop contribute",
    CLEANUP: "the-loop cleanup",
    # Two words, like every other keyword, and safe against prose by the SAME
    # boundary rule rather than by a special case: `the-loop does`,
    # `the-loop done` and `the-loop docs` all put a `\w` directly after `do`,
    # so none of them matches (issue-225).
    DO: "the-loop do",
    # Same boundary story (issue-279): `the-loop reviews`, `reviewed` and
    # `reviewer` all put a `\w` directly after `review`, so none of them
    # matches.
    REVIEW: "the-loop review",
}

# What may NOT sit directly against a keyword for it to count as a whole token.
# `\w`, `-` and `:` are the characters the keywords themselves are made of (plus
# the space between the two words), so excluding them means `the-loop start.`
# (trailing punctuation, end of a sentence, end of a line) matches while
# `the-loop startlater` and `xthe-loop start` do not.
_BOUNDARY_BEFORE = r"(?<![\w:-])"
_BOUNDARY_AFTER = r"(?![\w:-])"


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class ControlConfig:
    """Mirror of ``routing.control`` (see the config schema).

    ``require_start_command`` is the issue-106 headline: the auto-execute label
    becomes *necessary but not sufficient*, so a labelled work item waits for an
    authorized user's explicit start instead of spawning on the label alone. It
    defaults to true (fail closed); false restores the pre-issue-106 behaviour.
    """

    enabled: bool = True
    require_start_command: bool = True
    keywords: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYWORDS))
    gh_binary: str = "gh"

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "ControlConfig":
        data = data or {}
        configured = data.get("keywords") or {}
        keywords = dict(DEFAULT_KEYWORDS)
        for command in COMMANDS:
            if command in configured:
                # An empty string disables that ONE command (documented), which
                # is why this is not a truthiness filter.
                keywords[command] = str(configured[command] or "").strip()
        return cls(
            enabled=bool(data.get("enabled", True)),
            require_start_command=bool(data.get("requireStartCommand", True)),
            keywords=keywords,
            gh_binary=str(data.get("_ghBinary", "gh")),
        )

    def keyword(self, command: str) -> str:
        return self.keywords.get(command, "")


@dataclass(frozen=True)
class ControlResult:
    """What a comment body asked for: one command, ambiguity, or nothing.

    ``command`` is one of :data:`COMMANDS` or ``None``. ``ambiguous`` is set when
    the body carried two or more *different* commands — the caller must then do
    nothing at all (execute nothing, forward nothing).
    """

    command: Optional[str] = None
    ambiguous: bool = False
    matched: List[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.command is not None or self.ambiguous


def parse_command(body: Optional[str], config: ControlConfig) -> ControlResult:
    """The control command ``body`` carries, if any (pure, side-effect free).

    Whole-token, case-insensitive matching of the configured keywords. A body
    with the *same* command repeated is that command; a body with two different
    ones is :attr:`ControlResult.ambiguous` and must not be acted on.
    """
    if not config.enabled or not body:
        return ControlResult()
    found: List[str] = []
    for command in COMMANDS:
        keyword = config.keyword(command)
        if not keyword:
            continue
        pattern = _BOUNDARY_BEFORE + re.escape(keyword) + _BOUNDARY_AFTER
        if re.search(pattern, body, re.IGNORECASE):
            found.append(command)
    if not found:
        return ControlResult()
    if len(found) > 1:
        return ControlResult(ambiguous=True, matched=found)
    return ControlResult(command=found[0], matched=found)


def command_comment(command: str, config: ControlConfig, actor: str = "") -> str:
    """The comment body the CLI posts for a control action (issue-106 R4.2).

    Carries the **same keyword** an authorized user would have typed, so the
    ticket reads identically however the command was issued, plus a line saying
    it came from the CLI. Marked with the loop-prevention marker
    (:func:`the_loop.authz.mark_self_authored`) because the action has *already*
    been applied locally — without it, both ingress paths would read the-loop's
    own comment back and apply it again (the issue-104 contract).

    Built only from the configured keyword and the local ``actor`` name; no
    payload-derived text reaches it.
    """
    keyword = config.keyword(command) or command
    who = f" by `{actor}`" if actor else ""
    return mark_self_authored(
        f"{keyword}\n"
        "\n"
        f"_Issued from the-loop CLI{who} (`the-loop sessions {command}`). "
        "Recorded here so the work item's thread stays the full record of "
        "every control action; the-loop has already applied it locally._\n"
    )


@dataclass
class ControlRecord:
    """The last control command recorded for a work item."""

    ref: str
    command: str
    source: str = "comment"  # comment | cli
    actor: str = ""
    requested_at: str = ""
    note: str = ""  # e.g. the comment url

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "command": self.command,
            "source": self.source,
            "actor": self.actor,
            "requestedAt": self.requested_at,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ControlRecord":
        return cls(
            ref=str(data["ref"]),
            command=str(data["command"]),
            source=str(data.get("source") or "comment"),
            actor=str(data.get("actor") or ""),
            requested_at=str(data.get("requestedAt") or ""),
            note=str(data.get("note") or ""),
        )


def _as_ref(work_item: Union[str, WorkItemRef]) -> WorkItemRef:
    if isinstance(work_item, WorkItemRef):
        return work_item
    return WorkItemRef.parse(work_item)


class ControlStore:
    """The ``control`` section of each work item's portable record.

    Storage moved in issue-128: the last command per work item is now a section
    of ``<state.root>/portable/<slug>.json`` (:class:`the_loop.workitem.WorkItemStore`)
    rather than its own file under ``<registry dir>/control/``. The reason is
    portability, not tidiness — "an authorized user asked for this to be running"
    is true on any machine, so it belongs beside the other portable half (what
    the poller has seen) and away from the session handle, which is not. The
    public API here is unchanged, and a pre-issue-128 control record is still
    read (once) so an upgrade never forgets what was armed.

    A store whose directory cannot be read degrades to "nothing recorded": the
    daemon then simply refuses to spawn on its own (fail closed), rather than
    failing an event.
    """

    def __init__(self, root: Union[str, Path], legacy: Optional[LegacyLayout] = None):
        self.store = WorkItemStore(root, legacy=legacy)

    @property
    def root(self) -> Path:
        return self.store.root

    def record_frozen_graph(
        self, work_item: Union[str, WorkItemRef], frozen: Dict[str, Any]
    ) -> None:
        """Persist the graph a work item was frozen to walk (issue-177).

        Beside `control` in the same **portable** record, and for the same
        reason: "an authorized user chose these phases" is true on any machine,
        so it travels with the work item rather than with the session handle.
        """
        self.store.write_section(work_item, GRAPH, dict(frozen))

    def frozen_graph(
        self, work_item: Union[str, WorkItemRef]
    ) -> Optional[Dict[str, Any]]:
        """What :meth:`record_frozen_graph` wrote, or ``None`` if nothing has.

        The reader that makes the frozen selection *usable* by the daemon
        (issue-260) rather than only readable by a human: the routing choice a
        work item made at `phase-selection` is in here, and
        ``Dispatcher._tmux_for`` asks for it on every pull-request event. ``None``
        is the honest answer for every work item that has not answered the gate —
        which is every work item started before the choice existed.
        """
        return self.store.section(work_item, GRAPH)

    def record(
        self,
        work_item: Union[str, WorkItemRef],
        command: str,
        source: str = "comment",
        actor: str = "",
        note: str = "",
    ) -> ControlRecord:
        """Persist ``command`` as the work item's current control state."""
        if command not in COMMANDS:
            raise ValueError(f"unknown control command {command!r}")
        item = _as_ref(work_item)
        record = ControlRecord(
            ref=item.ref,
            command=command,
            source=source,
            actor=actor,
            requested_at=_utcnow(),
            note=note,
        )
        self.store.write_section(item, CONTROL, record.to_dict())
        logger.info(
            "recorded control command %s for %s (source=%s)", command, item.ref, source
        )
        return record

    def get(self, work_item: Union[str, WorkItemRef]) -> Optional[ControlRecord]:
        section = self.store.section(work_item, CONTROL)
        if not section:
            return None
        try:
            return ControlRecord.from_dict(section)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "skipping unreadable control record for %s: %s", work_item, exc
            )
            return None

    def start_requested(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Whether an authorized user asked for this work item to be running.

        True when the **last** recorded command was ``start`` or ``resume``, so
        a later ``pause``/``stop`` durably disarms the item: a labelled work item
        that was stopped does not quietly re-spawn on the next event.
        """
        record = self.get(work_item)
        return record is not None and record.command in _ARMING_COMMANDS

    def clear(self, work_item: Union[str, WorkItemRef]) -> bool:
        """Forget a work item's control state (it ended). False if there was none.

        Only the control section goes: the poll section of the same record is the
        poller's to drop, and it does so on the same closure path.
        """
        if self.get(work_item) is None:
            return False
        self.store.write_section(work_item, CONTROL, None)
        return True
