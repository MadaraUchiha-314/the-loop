"""The short form: the top-level Slack message, read on a phone (issue-549, task 7).

Every Slack message from the-loop leads with a short form: what happened and
what is needed. It comes from the first of three sources that has one (R3):

1. **summary**: the agent's own short form, ``--summary`` on ``the-loop comment``
   and ``the-loop ask`` (R3.1, R3.2);
2. **lead**: for an event no agent wrote (the runtime, a graph hook, the
   daemon), the fixed line its type already has, the room lead of issue-393
   (:func:`the_loop.channels.voice.room_lead`, R3.5);
3. **built**: for a session-authored event with no summary, the first question
   in the long form, or else its first sentence, followed by the work item's
   link. This records ``channels.short_form_missing`` so the gap is visible (R3.4).

Whatever the source, the text is defused (:mod:`the_loop.channels.defuse`),
drawn as mrkdwn, and capped at :data:`SUMMARY_MAX_CHARS` on a sentence boundary
(R3.6). The same text is the message's ``text`` fallback, which notifications
and screen readers read (R2.7). The *Open on GitHub* button carries the event's
own URL, never a link found in the short form's text (abuse case 5).

Pure apart from the one event-log record; no Slack, no disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from .. import eventlog, strings
from .defuse import defuse
from .mrkdwn import outside_code, to_mrkdwn, unfold
from .render import HEADING_LINE_RE, ITEM_RE, QUOTE_RE, block_spans
from .voice import room_lead

__all__ = [
    "SESSION_EVENTS",
    "SUMMARY_MAX_CHARS",
    "ShortForm",
    "build_short_form",
    "cap_short_form",
    "cut_at_boundary",
    "is_session_authored",
    "long_form_adds",
    "sentence_ends",
    "sentences",
]

#: How long a short form may be (issue-393 R8, issue-549 R3.6). A short form is
#: meant to be 2–3 sentences; a generous ceiling keeps a runaway one from taking
#: over the message while never clipping a real one. The one constant: the
#: digest and the ``--summary`` verbs read it from here.
SUMMARY_MAX_CHARS = 600

#: Event types a session writes: its comment and its question. Without a
#: summary they get a built short form, never a runtime lead.
SESSION_EVENTS = frozenset({"comment.agent", "session.awaiting_input"})

#: Event sources that are a session speaking (the CLI verbs, a session's API).
_SESSION_SOURCES = frozenset({"cli", "session"})

# -- sentences (moved here from the digest, issue-338) ---------------------------

#: The end of a sentence: the mark, any closing quote / bracket / emphasis, then
#: whitespace or the end. Abbreviations are filtered by :func:`sentence_ends`.
_SENTENCE_END = re.compile(r"[.!?]+[\"'’)\]*_~`]*(?=\s|$)")
_ABBREVIATIONS = ("e.g", "i.e", "vs", "etc", "cf", "no", "fig", "approx")
_CLAUSE_END = re.compile(r"[,;:]|\s—|\s–")


def sentence_ends(text: str) -> List[int]:
    """Offsets just past each sentence end in ``text``."""
    ends: List[int] = []
    for match in _SENTENCE_END.finditer(text):
        window = text[max(0, match.start() - 12) : match.start()]
        token = window.rsplit(None, 1)[-1].lower() if window.strip() else ""
        if match.group(0).startswith(".") and (
            token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha())
        ):
            continue
        ends.append(match.end())
    return ends


def sentences(text: str) -> List[str]:
    """``text`` as its sentences, in order; a tail with no end mark is one."""
    out: List[str] = []
    start = 0
    for end in sentence_ends(text):
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def cut_at_boundary(text: str, room: int) -> str:
    """``text`` shortened to fit ``room``: at the last sentence end within it,
    else the last clause end (plus ``…``), else the last space (plus ``…``),
    else ``""`` — never inside a word when a boundary exists."""
    if len(text) <= room:
        return text
    if room <= 1:
        return ""
    ends = [end for end in sentence_ends(text) if end <= room]
    if ends:
        return text[: ends[-1]].rstrip()
    clause = None
    for match in _CLAUSE_END.finditer(text):
        if match.start() < room - 1:
            clause = match.start()
        else:
            break
    if clause:
        return text[:clause].rstrip() + "…"
    space = text.rfind(" ", 0, room - 1)
    if space > 0:
        return text[:space].rstrip() + "…"
    return text[: room - 1].rstrip() + "…"


def cap_short_form(text: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """``text`` (mrkdwn) within ``limit`` characters, cut at a sentence where
    one fits (R3.6). A cut never leaves a ``<url|label>`` link open: it falls
    before the link instead."""
    text = text.strip()
    if len(text) <= limit:
        return text
    capped = cut_at_boundary(text, limit)
    opened = capped.rfind("<")
    if opened > capped.rfind(">"):
        capped = cut_at_boundary(text[:opened].rstrip(), limit)
    return capped


# -- the short form ----------------------------------------------------------------


@dataclass(frozen=True)
class ShortForm:
    """One event's short form.

    ``text`` is mrkdwn, defused, within the cap: the top message's text.
    ``url`` is the event's own URL, for the *Open on GitHub* button (empty when
    the event has none). ``source`` says which rule produced it: ``summary``,
    ``lead`` or ``built``, for the delivery log.
    """

    text: str
    url: str = ""
    source: str = "summary"

    @property
    def fallback(self) -> str:
        """The message's ``text`` fallback: the short form itself (R2.7)."""
        return self.text


def is_session_authored(event: Any) -> bool:
    """Whether a session wrote ``event``'s words (its comment, its question),
    so a missing summary is a gap to build around rather than a runtime event
    with a fixed lead."""
    source = str(getattr(event, "source", "") or "")
    event_type = str(getattr(event, "event_type", "") or "")
    return source in _SESSION_SOURCES or event_type in SESSION_EVENTS


def _draw(text: str) -> str:
    return to_mrkdwn(defuse(text)).strip()


def _prose(text: str) -> List[Tuple[str, str]]:
    """The prose blocks of ``text`` in order, as ``(kind, line)``: paragraphs,
    each list item, headings. Code, tables and traces are skipped."""
    lines = text.split("\n")
    out: List[Tuple[str, str]] = []
    for span in block_spans(lines):
        body = lines[span.start : span.end]
        if span.kind == "paragraph":
            joined = " ".join(QUOTE_RE.sub("", line).strip() for line in body)
            out.append(("paragraph", joined))
        elif span.kind == "heading":
            heading = HEADING_LINE_RE.match(body[0])
            out.append(("heading", heading.group(1) if heading else body[0].strip()))
        elif span.kind == "list":
            for line in body:
                item = ITEM_RE.match(line)
                out.append(("list", item.group(3).strip() if item else line.strip()))
    return [(kind, line) for kind, line in out if line]


def _first_line(text: str) -> str:
    """The first question in ``text``'s prose; else the first sentence of its
    first paragraph or list item (a heading opens most comments, and says less);
    else of its first heading; else ``""``."""
    blocks = _prose(text)
    for _, block in blocks:
        for sentence in sentences(block):
            if sentence.rstrip("\"'’)]*_~` ").endswith("?"):
                return sentence
    body = [line for kind, line in blocks if kind != "heading"]
    first = body[0] if body else (blocks[0][1] if blocks else "")
    found = sentences(first)
    return found[0] if found else ""


def _link(url: str) -> str:
    if not url:
        return ""
    safe = url.replace("|", "%7C").replace(">", "%3E").replace("<", "%3C")
    return f"<{safe}|{strings.t('channels.slack.button.open-on-github')}>"


def _with_preamble(preamble: str, body: str, limit: int) -> str:
    preamble = preamble.strip()
    if not preamble:
        return cap_short_form(body, limit)
    room = limit - len(preamble) - 1
    if room <= 0:
        return cap_short_form(preamble, limit)
    capped = cap_short_form(body, room)
    return f"{preamble}\n{capped}" if capped else preamble


def build_short_form(
    event: Any,
    *,
    session_authored: Optional[bool] = None,
    preamble: str = "",
    limit: int = SUMMARY_MAX_CHARS,
) -> ShortForm:
    """``event``'s short form: its summary, else its runtime lead, else a built
    line (logged as ``channels.short_form_missing``); defused, drawn as mrkdwn,
    within ``limit``.

    ``session_authored`` overrides :func:`is_session_authored` when the caller
    knows better. ``preamble`` is mrkdwn the channel builds itself (the recap
    line, the mentions; trusted, so not defused); it opens the text and counts
    toward the cap (R7, R9.3).
    """
    url = str(getattr(event, "url", "") or "")
    summary = _draw(str(getattr(event, "summary", "") or ""))
    if summary:
        return ShortForm(_with_preamble(preamble, summary, limit), url, "summary")
    authored = (
        is_session_authored(event) if session_authored is None else session_authored
    )
    if not authored:
        lead = _draw(room_lead(event))
        return ShortForm(_with_preamble(preamble, lead, limit), url, "lead")
    eventlog.emit(
        "channels.short_form_missing",
        work_item=str(getattr(event, "work_item", "") or ""),
        event_type=str(getattr(event, "event_type", "") or ""),
        event_id=str(getattr(event, "event_id", "") or ""),
    )
    text = defuse(outside_code(str(getattr(event, "text", "") or ""), unfold))
    line = to_mrkdwn(_first_line(text)).strip()
    link = _link(url)
    if not link:
        return ShortForm(_with_preamble(preamble, line, limit), url, "built")
    body = _with_preamble(preamble, line, limit - len(link) - 1)
    return ShortForm(f"{body} {link}".strip(), url, "built")


def _normalise(text: str) -> str:
    return " ".join(text.split())


def long_form_adds(event: Any, short: ShortForm) -> bool:
    """Whether ``event``'s long form says more than ``short`` (R3.3): False when
    it is empty once defused, or when the short form already holds all of it."""
    text = str(getattr(event, "text", "") or "")
    drawn = _normalise(_draw(text))
    if not drawn:
        return False
    return drawn not in _normalise(short.text)
