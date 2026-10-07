"""What a ledger writes for an event — one body selection for every tracker (issue-475).

Extracted from :mod:`.github` so the GitHub ledger and the Jira ledger
(:mod:`.jira`) write the same words for the same event: the event type picks the
shape (the table in :mod:`.github`'s docstring — the ask, a relay, a mirror, the
stamped default, a new ticket), and the tracker only decides how the body travels.
:func:`ledger_body` is that selection; GitHub posts what it returns as-is, Jira
replaces the self-marker with its visible form and converts the Markdown.
"""

from __future__ import annotations

from typing import Mapping, Optional, Tuple

from ..authz import mark_self_authored
from ..redact import (
    defang_control_keywords,
    neutralise_broadcasts,
    scrub,
    strip_html_comments,
)
from .base import Event
from .envelope import Envelope, stamp

__all__ = [
    "MIRRORED",
    "RELAYED",
    "TITLE_MAX_CHARS",
    "ask_body",
    "control_keywords",
    "issue_body",
    "issue_title",
    "ledger_body",
    "mirror_body",
    "relay_body",
    "stamped_body",
]

#: A ticket title's cap: GitHub allows longer, a DM's first line rarely deserves more.
TITLE_MAX_CHARS = 80

#: The events whose record must reach the ledger's ingress as a HUMAN comment —
#: unmarked, keywords intact — because ingress is what acts on them.
_RELAYED = ("gate.feedback", "control.command")

#: The events whose record is the-loop's OWN marked comment — quoted, scrubbed,
#: keywords defanged — because the channel already delivered them into the
#: session and no gate may ever read them as a person's words (issue-389,
#: decision-133 D4): a reply, a thread handed over as context, a decision.
_MIRRORED = ("work-item.reply", "context.added", "decision.recorded")

#: What the visible line of each mirrored record says it is.
_MIRROR_LINES = {
    "work-item.reply": "reply from {who} on the **{source}** channel, recorded "
    "here as the answer of record",
    "context.added": "📎 context from {who} on the **{source}** channel — "
    "{count} message(s) from {thread}, recorded here and appended to "
    "`context.md` by the session",
    "decision.recorded": "📌 decision from {who} on the **{source}** channel"
    "{kind} — recorded here and written up as a decision record by the session",
}


def control_keywords(cli_config: Optional[Mapping]) -> Tuple[str, ...]:
    """Every control keyword this deployment recognises — defaults + configured."""
    from ..control import DEFAULT_KEYWORDS

    configured = (
        (dict(cli_config or {}).get("routing") or {}).get("control") or {}
    ).get("keywords") or {}
    keywords = dict(DEFAULT_KEYWORDS)
    if isinstance(configured, Mapping):
        keywords.update({str(k): str(v) for k, v in configured.items()})
    return tuple(keywords.values())


def _quoted(text: str) -> str:
    return "\n".join(f"> {line}" for line in (text.splitlines() or [""]))


def _who(event: Event) -> str:
    """The visible attribution: the person's label, and the channel-native id."""
    native = event.actor.id_on(event.source) if event.actor else ""
    label = event.actor.label if event.actor else "(unknown)"
    if native and native != label:
        return f"`{label}` (`{event.source}:{native}`)"
    return (
        f"`{label}`" if label != "(unknown)" else f"an unknown `{event.source}` member"
    )


def _envelope(event: Event) -> Envelope:
    return Envelope(
        type=event.event_type,
        source=event.source,
        actor=event.actor.to_dict() if event.actor else {},
    )


def mirror_body(event: Event, cli_config: Optional[Mapping]) -> str:
    """The record of a mirrored event — quoted, scrubbed, defanged, marked.

    A ``work-item.reply``, and since issue-389 a ``context.added`` snapshot and
    a ``decision.recorded`` decision: the visible line names the act, the
    person and — from ``event.detail`` — the thread, the count, the kind and
    the rationale, all composed from fixed words and the event's own fields.

    The marker is licensed here because the-loop composed this comment (a report
    quoting the channel user, the ``_reply_report`` precedent) — and it is
    load-bearing: an unmarked copy of the answer would be forwarded by the poller
    into the very session the pipeline already delivered it to, and an unmarked
    decision would be read by a gate as an approval (decision-133 D4).
    """
    # The quote is another author's words (issue-389 A5): every `<!-- … -->`
    # inside it goes — a pasted marker would make `mark_self_authored` treat
    # the body as already stamped, a pasted envelope would be parsed as the
    # record's own — and a Slack broadcast is neutralised so a snapshot never
    # pages a room when it is read back.
    safe = defang_control_keywords(
        neutralise_broadcasts(strip_html_comments(scrub(event.text))),
        control_keywords(cli_config),
    )
    detail = event.detail or {}
    thread = str(detail.get("thread") or "")
    kind = str(detail.get("kind") or "")
    line = _MIRROR_LINES.get(event.event_type, _MIRROR_LINES["work-item.reply"])
    line = line.format(
        who=_who(event),
        source=event.source,
        count=str(detail.get("count") or "?"),
        thread=f"<{thread}>" if thread else "a thread",
        kind=f" (kind: {kind})" if kind else "",
    )
    body = f"🗣️ **the-loop** — {line}:\n\n" + _quoted(safe)
    rationale = str(detail.get("rationale") or "").strip()
    if rationale:
        body += "\n\n_why:_ " + scrub(rationale).replace("\n", " ")
    if event.event_type == "decision.recorded" and thread:
        body += f"\n\n_discussed at:_ <{thread}>"
    return stamp(mark_self_authored(body), _envelope(event))


def relay_body(event: Event) -> str:
    """The record of a ``gate.feedback`` / ``control.command`` — quoted, scrubbed,
    **unmarked**, keywords intact, so the ledger's ingress reads it as this
    person's own words. The attribution says which channel it was typed on."""
    if event.event_type != "gate.feedback":
        what = "control command"
    elif str(event.detail.get("gate") or "") == "unknown":
        # The pipeline could not read the gate (issue-321): the record is a reply
        # the ledger's ingress judges, and must not claim an answer it never saw.
        what = "reply"
    else:
        what = "answer to the open gate"
    body = (
        f"🗣️ **the-loop** — {what} from {_who(event)} on the **{event.source}** "
        "channel, recorded here so the loop reads it from the work item:\n\n"
        + _quoted(scrub(event.text))
    )
    return stamp(body, _envelope(event))


def ask_body(event: Event) -> str:
    """The ask's record is the question itself, marked (issue-208) and enveloped."""
    return stamp(mark_self_authored(event.text), _envelope(event))


def issue_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = first.lstrip("#").strip() or "Work item from a channel"
    if len(first) > TITLE_MAX_CHARS:
        first = first[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return first


def issue_body(event: Event) -> str:
    """A kickoff issue's body: the message, an attribution, the envelope — and NO
    self-authored marker, because the issue must be armable (a marked ``issues``
    event is dropped at ingress: the self-diagnosis rule, decision-103 D7)."""
    body = (
        scrub(event.text).rstrip()
        + f"\n\n---\n\n🗣️ _Opened from the **{event.source}** channel by "
        f"{_who(event)} through the-loop._"
    )
    return stamp(body, _envelope(event))


def stamped_body(event: Event) -> str:
    """Any other recorded event: the-loop's own words, marked and enveloped."""
    return stamp(mark_self_authored(event.text), _envelope(event))


def ledger_body(event: Event, cli_config: Optional[Mapping]) -> str:
    """The comment a ledger writes for ``event`` (every type but ``work-item.create``)."""
    if event.event_type == "session.awaiting_input":
        return ask_body(event)
    if event.event_type in _RELAYED:
        return relay_body(event)
    if event.event_type in _MIRRORED:
        return mirror_body(event, cli_config)
    return stamped_body(event)


#: Public names for the two event groups the selection turns on.
RELAYED = _RELAYED
MIRRORED = _MIRRORED
