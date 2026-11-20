"""Long text for a small screen (issue-338, decision-118).

The Slack channel used to cut every text section at ``maxChars`` — mid-sentence,
and often through the decision. This module condenses instead, **by structure and
deterministically**: the sentence that asks something goes first, a list of
choices becomes numbered lines, code fences / tables / stack traces become a
pointer, absolute paths lose their head, the rest follows in the author's order
until the budget is spent, the cut falls on a sentence, and one closing line
links the full text. No model reads the text, so every sentence a member reads
is the author's — the Slack message is the seat a decision is made from, and a
paraphrase there is the wrong tool (decision-118 D1).

Two layers, applied on different conditions:

* :func:`to_mrkdwn` — how GitHub markdown is *drawn* on Slack (``**bold**`` →
  ``*bold*``, headings, links, task boxes, bullets, HTML comments removed, a
  broadcast sequence neutralised). Lossless on the words; applied to **every**
  message (D3).
* :func:`condense` — the digest. Removes words, so it runs **only** above the
  cap (R4.1); :func:`fit` is the one entry point that decides.

Every pattern here is linear in the input — a character class that excludes its
own delimiter, or a line anchor — and the comment scan is forward-only, so a
crafted 64 KB comment costs what prose costs (abuse case A1).

Since issue-549 the drawing lives in :mod:`the_loop.channels.mrkdwn` and the
block parser in :mod:`the_loop.channels.render`; both stay importable from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .. import strings
from .defuse import USER_MENTION_RE
from .mrkdwn import (
    _CODE_SPAN,
    _inline,
    _neutralise,
    _outside_code,
    _unfold,
    strip_comments,
    to_mrkdwn,
)
from .shortform import (
    SUMMARY_MAX_CHARS,
    cut_at_boundary as _cut,
    sentences as _sentences,
)
from .render import (
    HEADING_LINE_RE as _HEADING_LINE,
    ITEM_RE as _ITEM,
    QUOTE_RE as _QUOTE,
    TABLE_RULE_RE as _TABLE_RULE,
    block_spans,
)

__all__ = [
    "DEFAULT_DIGEST_MODE",
    "DIGEST_MODES",
    "SUMMARY_MAX_CHARS",
    "condense",
    "fit",
    "sanitize_summary",
    "shorten_paths",
    "strip_comments",
    "to_mrkdwn",
    "truncate",
]


#: A Slack user mention in text — `<@U…>` / `<@W…>`, with or without a `|label`.
#: Neutralised in an agent-authored summary so it can ping no one (abuse case 3);
#: broadcast sequences (`<!here>` …) are handled by `neutralise_broadcasts`.
#: Defined by the defuser since issue-549; this name stays for this module.
_USER_MENTION_RE = USER_MENTION_RE

#: What happens to a text section longer than ``maxChars`` (R1.4).
DIGEST_MODES: Tuple[str, ...] = ("digest", "truncate")
DEFAULT_DIGEST_MODE = "digest"

# -- drawing markdown as mrkdwn (R3.4) ---------------------------------------------


# -- paths (R3.2) ----------------------------------------------------------------------

#: An absolute path of three or more segments, not inside a URL (the `/` after
#: `:`, `/` or `<`, or one following a word character, is not a path's start).
_PATH = re.compile(r"(?<![\w/:<])/(?:[\w.@+~-]+/){2,}[\w.@+~-]+")


def shorten_paths(text: str) -> str:
    """``/home/user/the-loop/cli/the_loop/channels/slack.py`` → ``…/channels/slack.py``."""

    def _short(match: "re.Match[str]") -> str:
        parts = match.group(0).split("/")
        return "…/" + "/".join(parts[-2:])

    return _PATH.sub(_short, text)


# -- the digest (R1, R2, R3) ---------------------------------------------------------

_REPLY_WORD = re.compile(r"\breply\b", re.I)

_POINTERS = strings.section("digest.pointer")


@dataclass
class _Block:
    kind: str  # heading | paragraph | list | code | table | trace
    text: str = ""
    items: List[Tuple[str, str]] = field(default_factory=list)  # (box, text)
    count: int = 0


def _parse(text: str) -> List[_Block]:
    """One pass over the lines into blocks (design § 1.2). The block boundaries
    come from :func:`the_loop.channels.render.block_spans` (issue-549 moved the
    parser there, for the long form); this draws each block the digest's way."""
    lines = text.split("\n")
    blocks: List[_Block] = []
    for span in block_spans(lines):
        body = lines[span.start : span.end]
        if span.kind == "paragraph":
            blocks.append(
                _Block(
                    "paragraph", " ".join(_QUOTE.sub("", line).strip() for line in body)
                )
            )
        elif span.kind == "heading":
            heading = _HEADING_LINE.match(body[0])
            blocks.append(_Block("heading", heading.group(1) if heading else body[0]))
        elif span.kind == "code":
            inside = len(body) - (2 if span.closed else 1)
            blocks.append(_Block("code", count=inside))
        elif span.kind == "table":
            rows = sum(1 for line in body if not _TABLE_RULE.match(line))
            blocks.append(_Block("table", count=max(rows - 1, 0)))
        elif span.kind == "trace":
            blocks.append(_Block("trace", count=len(body)))
        else:
            blocks.append(_Block("list", items=_list_items(body)))
    return blocks


def _list_items(body: List[str]) -> List[Tuple[str, str]]:
    """A list block's items as ``(box, text)``; a lazy continuation line joins
    the item above it, as GitHub draws it."""
    items: List[Tuple[str, str]] = []
    for line in body:
        current = _ITEM.match(line)
        if current:
            box = current.group(2)
            glyph = "" if box is None else ("☑ " if box.strip() else "☐ ")
            items.append((glyph, current.group(3).strip()))
        elif items:
            glyph, text = items[-1]
            items[-1] = (glyph, text + " " + line.strip())
    return items


def _find_ask(blocks: List[_Block]) -> Optional[str]:
    """The first question (R2.1); else the first *reply `…`* instruction. The
    sentence is removed from its block. Lists and pointers are never asks."""
    for want_question in (True, False):
        for block in blocks:
            if block.kind not in ("paragraph", "heading"):
                continue
            sentences = _sentences(block.text)
            for index, sentence in enumerate(sentences):
                bare = sentence.rstrip("\"'’)]*_~` ")
                hit = (
                    bare.endswith("?")
                    if want_question
                    else bool(
                        _REPLY_WORD.search(sentence) and _CODE_SPAN.search(sentence)
                    )
                )
                if hit:
                    del sentences[index]
                    block.text = " ".join(sentences)
                    return sentence
    return None


def _dress_ask(sentence: str) -> str:
    """The ask, bold — its own emphasis marks dropped so the bold is one span."""
    return "*" + _inline(sentence).replace("*", "").strip() + "*"


def _render(block: _Block) -> List[str]:
    if block.kind in _POINTERS:
        return ["_⟨" + _POINTERS[block.kind].format(n=block.count) + "⟩_"]
    if block.kind != "list" and not block.text.strip():
        return []  # a paragraph or heading the ask emptied
    if block.kind == "heading":
        return ["*" + _inline(block.text).replace("*", "") + "*"]
    if block.kind == "list":
        return [
            f"{n}. {glyph}{shorten_paths(_inline(text))}"
            for n, (glyph, text) in enumerate(block.items, 1)
        ]
    return [shorten_paths(_inline(block.text))]


def _footer(url: str) -> str:
    return (
        strings.t("channels.digest.footer.link", url=url)
        if url
        else strings.t("channels.digest.footer.ticket")
    )


def condense(text: str, limit: int, url: str = "") -> str:
    """The digest of ``text`` within ``limit`` characters (R1–R3).

    The ask first (bold), then every block in the author's order — lists as
    numbered lines, code / tables / traces as pointers — while the budget holds;
    the block that no longer fits is cut at a sentence; one closing line links
    the full text whenever anything was cut, left out or replaced.
    """
    text = _outside_code(_neutralise(strip_comments(text)), _unfold).strip()
    if not text:
        return ""
    blocks = _parse(text)
    ask = _find_ask(blocks)
    replaced = any(block.kind in _POINTERS for block in blocks)
    # Whole, when it fits once drawn (the boxes and bullets are shorter than the
    # markdown that made them) and nothing was replaced — no footer then.
    pieces, left_out = _assemble(blocks, ask, limit)
    if not left_out and not replaced:
        return "\n\n".join(pieces)
    footer = _footer(url)
    pieces, _ = _assemble(blocks, ask, max(limit - len(footer) - 2, 0))
    if not pieces:
        return _cut(text.split("\n", 1)[0], limit) if limit > 1 else ""
    return "\n\n".join(pieces + [footer])


def _assemble(
    blocks: List[_Block], ask: Optional[str], budget: int
) -> Tuple[List[str], bool]:
    """``(pieces, left_out)``: the ask and the blocks that fit in ``budget``,
    the first that does not cut at a boundary, nothing after it."""
    pieces: List[str] = []
    used = 0
    left_out = False

    def room_for(sep: int) -> int:
        return budget - used - sep

    if ask:
        dressed = _dress_ask(ask)
        line = _cut(dressed, max(room_for(0), 0))
        if line and not line.endswith("*"):
            line += "*"
        if line:
            pieces.append(line)
            used += len(line)
        left_out = line != dressed
    for block in blocks:
        if left_out:
            break
        lines = [line for line in _render(block) if line.strip()]
        if not lines:
            continue
        sep = 2 if pieces else 0
        rendered = "\n".join(lines)
        if len(rendered) <= room_for(sep):
            pieces.append(rendered)
            used += sep + len(rendered)
            continue
        # This block does not fit whole: take what fits, then stop.
        left_out = True
        if block.kind == "list":
            kept: List[str] = []
            for line in lines:
                inner = 1 if kept else sep
                if len(line) <= room_for(inner):
                    kept.append(line)
                    used += inner + len(line)
                    continue
                part = _cut(line, room_for(inner))
                if len(part) > 12:
                    kept.append(part)
                    used += inner + len(part)
                break
            if kept:
                pieces.append("\n".join(kept))
        elif block.kind not in _POINTERS:
            part = _cut(rendered, room_for(sep))
            if part:
                pieces.append(part)
                used += sep + len(part)
    return pieces, left_out


def truncate(text: str, limit: int) -> str:
    """13.10.0's cut: the first ``limit`` characters and a note (R1.4)."""
    text = text.strip()
    if len(text) <= limit:
        return text
    rest = len(text) - limit
    return text[:limit].rstrip() + strings.t("channels.digest.truncate.note", rest=rest)


def sanitize_summary(summary: str, limit: int = SUMMARY_MAX_CHARS) -> str:
    """An agent-authored summary, safe to render into a room (issue-393 R8/R12).

    The session writes this, so it is untrusted-adjacent: drawn as mrkdwn (which
    neutralises broadcast sequences and strips the-loop's own markers), with
    direct user mentions defused so a summary can ping no one, and capped so a
    runaway one cannot take over the message. Empty in, empty out — the caller
    then falls back to the digest excerpt.
    """
    text = (summary or "").strip()
    if not text:
        return ""
    defused = _USER_MENTION_RE.sub(r"@\1", text)  # `<@U…>` → plain `@U…`, inert
    drawn = to_mrkdwn(defused).strip()
    return truncate(drawn, limit)


def fit(text: str, limit: int, mode: str = DEFAULT_DIGEST_MODE, url: str = "") -> str:
    """One text section, ready for Slack: drawn as mrkdwn when it fits (R4.1),
    13.10.0's cut under ``truncate``, the digest otherwise (R1.1). The threshold
    is the **raw** length — a message written under the cap is never digested
    because its rendering grew."""
    text = text.strip()
    if len(text) <= limit:
        drawn = to_mrkdwn(text).strip()
        if len(drawn) <= limit:
            return drawn
        # Only the broadcast rewrite (`<!` → `&lt;!`) can grow a text; a text
        # that grew past the cap is over it, never posted over Slack's limit.
    if mode == "truncate":
        return truncate(to_mrkdwn(text), limit)
    return condense(text, limit, url)
