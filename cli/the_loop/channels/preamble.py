"""What opens a short form: the recap line and the mentions (issue-549, task 14).

Two lines the channel builds itself, from configuration and from the loop's own
record, never from model output. They open the short form and count toward its
600-character cap (:func:`the_loop.channels.shortform.build_short_form`'s
``preamble``), and they are added **after** defusing, so they are the only live
mentions a message carries (abuse case 2).

* **Mentions (R7).** An awaiting message (the session's question, a decision,
  an approval gate) mentions each authorized user whose Slack identity resolves
  to a member id, once per wait. :func:`wait_key` names the wait; the channel
  remembers which waits it announced, and forgets them when the work item
  leaves the waiting state, so a gate that reopens is a new wait. An identity
  that does not resolve mentions no one (abuse case 6).
* **Recap (R9).** When the last message from an authorized human in the
  conversation is older than :data:`RECAP_AFTER_S` (12 hours, fixed, R9.4) and
  the loop recorded a change since, the short form opens with one line naming
  those changes. :func:`change_of` reads a change from the loop's own events —
  phase changes, gate outcomes, completion, escalation — before the room policy
  decides whether to post them, so bookkeeping still feeds the recap (R10.2).
  No bus event carries a PR opening/merge or a failed check today, so the recap
  names none; when one does, :func:`change_of` is the one place to add it.

Pure: no Slack, no disk, no clock — the caller passes the time.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Tuple

from .. import strings
from .directory import is_member_id
from .events import APPROVAL_EVENTS

__all__ = [
    "MENTION_EVENTS",
    "RECAP_AFTER_S",
    "RECAP_MAX_CHANGES",
    "Preamble",
    "change_of",
    "mention_line",
    "recap_line",
    "wait_key",
]

#: The recap threshold (R9.1, R9.4): fixed in code, documented in the channels
#: capability doc, not configurable.
RECAP_AFTER_S = 12 * 60 * 60

#: How many changes the recap line names; older ones are counted, not named.
RECAP_MAX_CHANGES = 6

#: Awaiting messages (R7.1): the only messages that mention anyone (R7.4).
MENTION_EVENTS = frozenset(
    {"session.awaiting_input", "decision-pending", *APPROVAL_EVENTS}
)

#: Gate outcomes the recap names (the outcomes a human approval gate emits).
_GATE_OUTCOMES = frozenset({"approved", "approved-with-comments", "changes-requested"})

#: What a phase, node or outcome named in a recap may look like: the runtime's
#: own identifiers. Anything else is left out rather than drawn.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


@dataclass(frozen=True)
class Preamble:
    """The lines that open one short form, and what delivering it records.

    ``wait`` is the wait this message announces (``""`` for a message that is
    not awaiting); ``recapped`` says the recap line is in ``text``.
    """

    text: str = ""
    wait: str = ""
    recapped: bool = False


def wait_key(event: Any) -> str:
    """The wait an awaiting ``event`` announces, or ``""`` (R7.3).

    A gate's wait is its event type at its node; the session's question is its
    words, so the same question asked again is the same wait and a new question
    is a new one.
    """
    event_type = str(getattr(event, "event_type", "") or "")
    if event_type not in MENTION_EVENTS:
        return ""
    detail = getattr(event, "detail", None) or {}
    node = str(detail.get("node") or detail.get("phase") or "")
    if event_type in ("session.awaiting_input", "decision-pending"):
        text = str(getattr(event, "text", "") or "")
        digest = hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
        return f"{event_type}:{node}:{digest[:16]}"
    return f"{event_type}:{node}"


def mention_line(member_ids: Iterable[str]) -> str:
    """The mentions for ``member_ids``, in order, each once; ``""`` when none
    is a member id (R7.2). Built here, after defusing, so they notify."""
    seen: List[str] = []
    for ident in member_ids:
        ident = str(ident or "").strip()
        if is_member_id(ident) and ident not in seen:
            seen.append(ident)
    if not seen:
        return ""
    return strings.t(
        "channels.slack.mention.line",
        mentions=" ".join(f"<@{ident}>" for ident in seen),
    )


def _name(value: Any) -> str:
    text = str(value or "")
    return text if _NAME_RE.match(text) else ""


def change_of(event: Any) -> Optional[Tuple[str, str]]:
    """The change ``event`` records for the recap, as ``(kind, value)``, or
    ``None``. Built from the event type and the runtime's identifiers in its
    detail, never from its text (R9.3)."""
    event_type = str(getattr(event, "event_type", "") or "")
    detail = getattr(event, "detail", None) or {}
    phase = _name(detail.get("phase"))
    outcome = str(detail.get("outcome") or "")
    if (
        event_type in ("phase.completed", "phase.progress")
        and outcome in _GATE_OUTCOMES
    ):
        where = phase or _name(detail.get("node"))
        return ("gate", f"{where}:{outcome}") if where else None
    if event_type == "phase.started" and phase:
        return ("phase", phase)
    if event_type == "work-item-complete":
        return ("complete", "")
    if event_type == "work-item.closed":
        return ("closed", "")
    if event_type == "conflict-escalated":
        return ("escalated", "")
    return None


def _draw(kind: str, value: str) -> str:
    if kind == "gate":
        where, _, outcome = value.partition(":")
        return strings.t(
            "channels.slack.recap.change.gate", phase=where, outcome=outcome
        )
    if kind == "phase":
        return strings.t("channels.slack.recap.change.phase", phase=value)
    if kind == "complete":
        return strings.t("channels.slack.recap.change.complete")
    if kind == "closed":
        return strings.t("channels.slack.recap.change.closed")
    if kind == "escalated":
        return strings.t("channels.slack.recap.change.escalated")
    return ""


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def recap_line(
    changes: Sequence[Mapping[str, Any]],
    *,
    last_human: Any,
    recapped_at: Any,
    now: float,
) -> str:
    """The recap line, or ``""`` (R9.1, R9.2).

    ``changes`` are the delivery memory's ``{at, kind, value}`` records, oldest
    first; ``last_human`` when an authorized human last spoke in the
    conversation; ``recapped_at`` when a recap was last posted. A recap is due
    when that human spoke more than :data:`RECAP_AFTER_S` ago and a change was
    recorded since both; it names every change since the human spoke, the
    newest :data:`RECAP_MAX_CHANGES` of them.
    """
    spoke = _float(last_human)
    if spoke <= 0 or now - spoke <= RECAP_AFTER_S:
        return ""  # no human has spoken, or not long enough ago
    since = [c for c in changes if _float(c.get("at")) > spoke]
    fresh = max(spoke, _float(recapped_at))
    if not any(_float(c.get("at")) > fresh for c in since):
        return ""  # nothing changed since (R9.2), or already recapped
    drawn: List[str] = []
    for change in since:
        line = _draw(str(change.get("kind") or ""), str(change.get("value") or ""))
        if line and (not drawn or drawn[-1] != line):
            drawn.append(line)
    if not drawn:
        return ""
    named = drawn[-RECAP_MAX_CHANGES:]
    earlier = len(drawn) - len(named)
    if earlier:
        named.insert(0, strings.t("channels.slack.recap.more", count=earlier))
    return strings.t(
        "channels.slack.recap.line",
        hours=int((now - spoke) // 3600),
        changes=" · ".join(named),
    )
