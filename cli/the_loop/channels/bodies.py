"""What a ledger writes for an event — one body selection for every tracker (issue-475).

Extracted from :mod:`.github` so the GitHub ledger and the Jira ledger
(:mod:`.jira`) write the same words for the same event: the event type picks the
shape (the table in :mod:`.github`'s docstring — the ask, a relay, a mirror, the
stamped default, a new ticket), and the tracker only decides how the body travels.
:func:`ledger_body` is that selection; GitHub posts what it returns as-is, Jira
replaces the self-marker with its visible form and converts the Markdown.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional, Tuple

from .. import durations, strings
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
    "default_block",
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
_MIRROR_LINES = strings.section("bodies.mirror")


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
    unknown = strings.t("channels.bodies.who.unknown-label")
    label = event.actor.label if event.actor else unknown
    if native and native != label:
        return f"`{label}` (`{event.source}:{native}`)"
    return (
        f"`{label}`"
        if label != unknown
        else strings.t("channels.bodies.who.unknown-member", source=event.source)
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
        thread=f"<{thread}>"
        if thread
        else strings.t("channels.bodies.mirror.a-thread"),
        kind=strings.t("channels.bodies.mirror.kind", kind=kind) if kind else "",
    )
    body = strings.t("channels.bodies.mirror.head", line=line) + _quoted(safe)
    rationale = str(detail.get("rationale") or "").strip()
    if rationale:
        body += strings.t("channels.bodies.mirror.why") + scrub(rationale).replace(
            "\n", " "
        )
    if event.event_type == "decision.recorded" and thread:
        body += strings.t("channels.bodies.mirror.discussed-at", thread=thread)
    return stamp(mark_self_authored(body), _envelope(event))


def relay_body(event: Event) -> str:
    """The record of a ``gate.feedback`` / ``control.command`` — scrubbed,
    **unmarked**, keywords intact, so the ledger's ingress reads it as this
    person's own words. The attribution says which channel it was typed on.

    The words come FIRST and unquoted, the attribution after them (issue-498): a
    control keyword counts only where a comment opens with it, so a header line
    above the words would turn every relayed command into prose."""
    if event.event_type != "gate.feedback":
        what = strings.t("channels.bodies.relay.what.control-command")
    elif str(event.detail.get("gate") or "") == "unknown":
        # The pipeline could not read the gate (issue-321): the record is a reply
        # the ledger's ingress judges, and must not claim an answer it never saw.
        what = strings.t("channels.bodies.relay.what.reply")
    else:
        what = strings.t("channels.bodies.relay.what.gate-answer")
    body = scrub(event.text).strip() + strings.t(
        "channels.bodies.relay.attribution",
        what=what,
        who=_who(event),
        source=event.source,
    )
    return stamp(body, _envelope(event))


#: Markdown's own punctuation, backslash-escaped where the-loop quotes a
#: session's words inside a sentence of its own.
_MARKDOWN_ACTIVE = re.compile(r"([\\`*_\[\]<>#|~!])")


#: What makes a tracker or a chat client link a bare address by itself.
_AUTOLINK_START = re.compile(r"(?i)(://|(?<=www)\.)")


def break_autolinks(text: str) -> str:
    """``text`` with a zero-width space inside every `://` and after every
    `www`, so a bare address is read and never linked. The words are unchanged
    to the eye."""
    return _AUTOLINK_START.sub(
        lambda match: ":\u200b//" if match.group(1) == "://" else "\u200b.", text
    )


def _inert(text: str) -> str:
    """``text`` on one line, as words only: no marker or envelope, no markup, no
    link — written out or bare — and no mention that notifies anyone."""
    line = " ".join(neutralise_broadcasts(strip_html_comments(text)).split())
    # A backslash does not stop GitHub's mention, so the `@` is cut from the name.
    line = _MARKDOWN_ACTIVE.sub(r"\\\1", line).replace("@", "@\u200b")
    return break_autolinks(line)


def default_block(event: Event) -> str:
    """What the-loop states below a question that has a default and a deadline
    (issue-551, R6.1): the default and the time it is taken. ``""`` for an ask
    without both — a default with no time is never taken by itself."""
    from ..core.sessionstate import parse_ts  # core imports the channels

    detail = event.detail or {}
    default = str(detail.get("default") or "").strip()
    moment = parse_ts(detail.get("default_at"))
    if not default or moment is None:
        return ""
    block = strings.t(
        "channels.bodies.ask.default-block",
        default=_inert(default),
        time=moment.strftime("%Y-%m-%d %H:%M UTC"),
        wait=_wait_words(detail.get("default_after")),
    )
    requested = _wait_words(detail.get("default_requested"))
    if requested:
        # R6.5: the question says the operator's minimum replaced the wait.
        block += strings.t("channels.bodies.ask.wait-raised", requested=requested)
    return block


def _wait_words(seconds: object) -> str:
    text = str(seconds or "")
    return durations.in_words(int(text)) if text.isdigit() and int(text) else ""


def ask_body(event: Event) -> str:
    """The ask's record is the question itself, marked (issue-208) and enveloped,
    with its default and deadline stated below it when it has them."""
    return stamp(
        mark_self_authored(event.text + default_block(event)), _envelope(event)
    )


def issue_title(text: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    first = first.lstrip("#").strip() or strings.t(
        "channels.bodies.issue.default-title"
    )
    if len(first) > TITLE_MAX_CHARS:
        first = first[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return first


def issue_body(event: Event) -> str:
    """A kickoff issue's body: the message, an attribution, the envelope — and NO
    self-authored marker, because the issue must be armable (a marked ``issues``
    event is dropped at ingress: the self-diagnosis rule, decision-103 D7)."""
    body = scrub(event.text).rstrip() + strings.t(
        "channels.bodies.issue.attribution", source=event.source, who=_who(event)
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
