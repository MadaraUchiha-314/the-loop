"""What the-loop says when a session stalls or an ask's deadline passes.

The watcher publishes four events, and this module words them: the stall notice
and its end, "default taken", and the reminder for a question with no default.
Each is an :class:`~.base.Event` whose ``text`` is the comment the ledger writes
and whose ``summary`` is the Slack short form, so the two say the same thing in
each surface's own shape. Every word is in ``strings/en.json``.

Built from the loop's own facts: the ref, a node id, counts and times. The one
piece of session-written text, an ask's default, is quoted as inert words on
both surfaces and is never an answer to anything: the comment carries the
agent-comment marker, so no gate reads it.

Pure: no Slack, no GitHub, no disk, no clock.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .. import strings
from .base import Event
from .bodies import _inert
from .shortform import quoted_default
from .voice import _short_id

__all__ = [
    "ASK_DEFAULT_TAKEN",
    "ASK_REMINDED",
    "STALLED",
    "STALL_ENDED",
    "ask_key",
    "default_taken",
    "reminded",
    "stall_ended",
    "stall_key",
    "stalled",
]

STALLED = "session.stalled"
STALL_ENDED = "session.stall_ended"
ASK_DEFAULT_TAKEN = "session.ask_default_taken"
ASK_REMINDED = "session.ask_reminded"

#: A node id as the graph writes one. Anything else is left out of a message
#: rather than drawn: a notice may name a node the graph could not resolve.
_NODE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def stall_key(stall_id: str) -> str:
    """Where a channel remembers the notice of one stall."""
    return f"stall:{stall_id}"


def ask_key(ask_id: str) -> str:
    """Where a channel remembers the message of one question."""
    return f"ask:{ask_id}"


#: Every word of the four messages, by its name under `channels.sessionnotes`.
_WORDS = strings.section("channels.sessionnotes")


def _t(name: str, **slots: object) -> str:
    return _WORDS[name].format(**slots)


def _at(node: str) -> str:
    return _t("at", node=node) if _NODE_RE.match(node or "") else ""


def _short(seconds: int) -> str:
    """`22 min`, `2 h`, `3 h 5 min`: a time in a Slack line."""
    minutes = max(0, int(seconds)) // 60
    if minutes < 120:
        return _t("short.minutes", count=minutes)
    if minutes % 60 == 0:
        return _t("short.hours", count=minutes // 60)
    return _t("short.hours-minutes", hours=minutes // 60, minutes=minutes % 60)


def _long(seconds: int) -> str:
    """`22 minutes`, `2 hours`: a time in a sentence of a comment."""
    minutes = max(0, int(seconds)) // 60

    def words(count: int) -> str:
        return _t("long.minute") if count == 1 else _t("long.minutes", count=count)

    if minutes < 120:
        return words(minutes)
    if minutes % 60 == 0:
        return _t("long.hours", count=minutes // 60)
    return _t("long.hours-minutes", hours=minutes // 60, minutes=words(minutes % 60))


def _counted(name: str, count: int) -> str:
    """One of a string's `.0`, `.1`, `.2` and `.many` forms."""
    form = str(count) if count in (0, 1, 2) else "many"
    return _t(f"{name}.{form}", count=count)


def _clock(moment: Optional[datetime]) -> str:
    return moment.strftime("%H:%M UTC") if moment is not None else "?"


def stalled(
    ref: str,
    *,
    stall_id: str,
    node: str,
    idle_seconds: int,
    nudges: int,
    tmux_target: str,
) -> Event:
    """The stall notice: the node, how long the session has been idle, how
    many nudges did not restart it, and how a person wakes it."""
    at = _at(node)
    return Event(
        event_type=STALLED,
        work_item=ref,
        text=_t(
            "stalled.github",
            at=at,
            waited=_long(idle_seconds),
            nudged=_counted("stalled.github.nudged", nudges),
            ref=ref,
        ),
        summary=_t(
            "stalled.slack",
            item=_short_id(ref),
            at=at,
            waited=_short(idle_seconds),
            nudges=_counted("stalled.slack.nudges", nudges),
            attach=(
                _t("stalled.slack.attach", target=tmux_target) if tmux_target else ""
            ),
        ),
        detail={
            "stall_id": stall_id,
            "node": node if at else "",
            "nudges": str(nudges),
            "idle_seconds": str(idle_seconds),
        },
    )


def stall_ended(
    ref: str,
    *,
    stall_id: str,
    node: str,
    began: Optional[datetime],
    ended: Optional[datetime],
    notified: bool,
) -> Event:
    """The resolved form of the stall notice.

    ``notified`` says a notice was posted for this stall. Without one there is
    nothing to resolve: Slack edits only a message it remembers, and the
    publisher keeps the event off the ledger.
    """
    at = _at(node)
    seconds = (
        int((ended - began).total_seconds())
        if began is not None and ended is not None
        else 0
    )
    return Event(
        event_type=STALL_ENDED,
        work_item=ref,
        text=_t(
            "ended.github",
            at=at,
            start=_clock(began),
            end=_clock(ended),
            waited=_long(seconds),
        ),
        summary=_t(
            "ended.slack",
            item=_short_id(ref),
            at=at,
            end=_clock(ended),
            waited=_short(seconds),
        ),
        detail={
            "stall_id": stall_id,
            "node": node if at else "",
            "notified": "true" if notified else "",
        },
    )


def default_taken(
    ref: str,
    *,
    ask_id: str,
    default: str,
    deadline: Optional[datetime],
    question_url: str = "",
    delivered: bool = True,
) -> Event:
    """ "Default taken": nobody answered by the deadline, the session goes
    ahead with its own default, and that is not an approval of anything.

    ``delivered`` is whether the session was told. When it was not (it is
    paused, or its pane did not take the message) the note says the default
    applies and that the session does not know yet, never that it went ahead.

    The default is quoted as inert words on both surfaces, and is not carried
    in ``detail``: nothing draws it a second time without that.
    """
    told = "" if delivered else ".untold"
    return Event(
        event_type=ASK_DEFAULT_TAKEN,
        work_item=ref,
        text=_t(
            f"default-taken.github{told}",
            question=(
                _t("default-taken.github.question-link", url=question_url)
                if question_url
                else _t("default-taken.github.question")
            ),
            time=_clock(deadline),
            default=_inert(default),
        ),
        summary=_t(
            f"default-taken.slack{told}",
            time=_clock(deadline),
            default=quoted_default(default),
        ),
        detail={"ask_id": ask_id, "delivered": "true" if delivered else ""},
    )


def reminded(
    ref: str, *, ask_id: str, waited_seconds: int, question_url: str = ""
) -> Event:
    """The one reminder for a question with no default."""
    return Event(
        event_type=ASK_REMINDED,
        work_item=ref,
        text=_t(
            "reminded.github",
            waited=_long(waited_seconds),
            question=(
                _t("reminded.github.question-link", url=question_url)
                if question_url
                else _t("reminded.github.question")
            ),
        ),
        summary=_t(
            "reminded.slack", item=_short_id(ref), waited=_short(waited_seconds)
        ),
        detail={"ask_id": ask_id},
    )
