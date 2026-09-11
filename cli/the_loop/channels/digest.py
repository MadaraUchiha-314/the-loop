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
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

__all__ = [
    "DEFAULT_DIGEST_MODE",
    "DIGEST_MODES",
    "condense",
    "fit",
    "shorten_paths",
    "strip_comments",
    "to_mrkdwn",
    "truncate",
]

#: What happens to a text section longer than ``maxChars`` (R1.4).
DIGEST_MODES: Tuple[str, ...] = ("digest", "truncate")
DEFAULT_DIGEST_MODE = "digest"

# -- drawing markdown as mrkdwn (R3.4) ---------------------------------------------

_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_BOLD_UNDERSCORE = re.compile(r"(?<!\w)__([^_\n]+)__(?!\w)")
_STRIKE = re.compile(r"~~([^~\n]+)~~")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_LINK = re.compile(r"!?\[([^\[\]\n]+)\]\(([^()\s]+)\)")
_TASK_DONE = re.compile(r"^(\s*)[-*+]\s+\[[xX]\]\s*", re.MULTILINE)
_TASK_OPEN = re.compile(r"^(\s*)[-*+]\s+\[ \]\s*", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*+]\s+(?=\S)", re.MULTILINE)
#: `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^…>` — the one thing in a
#: comment's text that ACTS on Slack (A2). Rewritten after the comment scan, so
#: the-loop's own `<!-- … -->` markers are already gone.
_BROADCAST = re.compile(r"<!(?!--)")


def strip_comments(text: str) -> str:
    """Every ``<!-- … -->`` removed — the-loop's markers and envelopes, and any
    other (A5). A forward scan: an unterminated opener is kept as text."""
    out: List[str] = []
    pos = 0
    while True:
        start = text.find("<!--", pos)
        if start < 0:
            out.append(text[pos:])
            break
        end = text.find("-->", start + 4)
        if end < 0:
            out.append(text[pos:])
            break
        out.append(text[pos:start])
        pos = end + 3
    return "".join(out)


_CODE_SPAN = re.compile(r"`[^`\n]+`")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HOLE = "\x00"


def _outside_code(text: str, draw: Callable[[str], str]) -> str:
    """``draw`` applied to ``text`` outside fenced blocks and inline code spans,
    which Slack shows verbatim — a ``# comment`` in a shell snippet is not a
    heading, and ``**`` in a code span is two asterisks."""
    out: List[str] = []
    prose: List[str] = []
    fence = ""

    def flush() -> None:
        if not prose:
            return
        segment = "\n".join(prose)
        prose.clear()
        spans: List[str] = []

        def hold(match: "re.Match[str]") -> str:
            spans.append(match.group(0))
            return f"{_HOLE}{len(spans) - 1}{_HOLE}"

        drawn = draw(_CODE_SPAN.sub(hold, segment.replace(_HOLE, "")))
        for index, span in enumerate(spans):
            drawn = drawn.replace(f"{_HOLE}{index}{_HOLE}", span, 1)
        out.append(drawn)

    for line in text.split("\n"):
        opener = _FENCE.match(line)
        if fence:
            out.append(line)
            if line.lstrip().startswith(fence):
                fence = ""
            continue
        if opener:
            flush()
            fence = opener.group(1)
            out.append(line)
            continue
        prose.append(line)
    flush()
    return "\n".join(out)


def _inline_rules(text: str) -> str:
    text = _BOLD.sub(r"*\1*", text)
    text = _BOLD_UNDERSCORE.sub(r"*\1*", text)
    text = _STRIKE.sub(r"~\1~", text)
    return _LINK.sub(r"<\2|\1>", text)


def _inline(text: str) -> str:
    """The inline rules — emphasis, strike, links — on text whose line-level
    shape (headings, bullets) the caller has already handled; code spans kept."""
    return _outside_code(text, _inline_rules)


def _neutralise(text: str) -> str:
    return _BROADCAST.sub("&lt;!", text)


def _line_rules(text: str) -> str:
    text = _HEADING.sub(r"*\1*", text)
    text = _TASK_DONE.sub("\\1☑ ", text)
    text = _TASK_OPEN.sub("\\1☐ ", text)
    text = _BULLET.sub("\\1• ", text)
    return _inline_rules(text)


def to_mrkdwn(text: str) -> str:
    """GitHub markdown drawn as Slack mrkdwn (R3.4): the words unchanged, the
    marks Slack cannot draw replaced by the ones it can, HTML comments gone,
    broadcast sequences neutralised (everywhere — a fence is no safe harbour),
    code fences and spans left exactly as written. Idempotent on its own output."""
    return _outside_code(_neutralise(strip_comments(text)), _line_rules)


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

_TABLE_ROW = re.compile(r"^\s*\|")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}")
_HEADING_LINE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
_ITEM = re.compile(
    r"^(\s*)(?:[-*+]|\d{1,3}[.)]|[A-Z][.)]|[a-z]\))\s+(?:\[([ xX])\]\s*)?(.*)$"
)
_QUOTE = re.compile(r"^\s*>\s?")
_TRACE_LINE = re.compile(
    r"^(?:Traceback \(most recent call last\):?\s*$"
    r"|\s+File \".*\", line \d+.*"
    r"|\s+at \S.*"
    r"|[\w.]*(?:Error|Exception)\b.*"
    r"|\s*\^+\s*$)"
)
_TRACE_START = re.compile(
    r"^(?:Traceback \(most recent call last\):?\s*$|\s+at \S.*\(.*:\d+.*\)\s*$)"
)
#: The end of a sentence: the mark, any closing quote / bracket / emphasis, then
#: whitespace or the end. Abbreviations are filtered by :func:`_sentence_ends`.
_SENTENCE_END = re.compile(r"[.!?]+[\"'’)\]*_~`]*(?=\s|$)")
_ABBREVIATIONS = ("e.g", "i.e", "vs", "etc", "cf", "no", "fig", "approx")
_CLAUSE_END = re.compile(r"[,;:]|\s—|\s–")
_REPLY_WORD = re.compile(r"\breply\b", re.I)

_POINTERS = {
    "code": "code: {n} lines",
    "table": "table: {n} rows",
    "trace": "stack trace: {n} lines",
}


@dataclass
class _Block:
    kind: str  # heading | paragraph | list | code | table | trace
    text: str = ""
    items: List[Tuple[str, str]] = field(default_factory=list)  # (box, text)
    count: int = 0


def _sentence_ends(text: str) -> List[int]:
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


def _sentences(text: str) -> List[str]:
    out: List[str] = []
    start = 0
    for end in _sentence_ends(text):
        piece = text[start:end].strip()
        if piece:
            out.append(piece)
        start = end
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _parse(text: str) -> List[_Block]:
    """One pass over the lines into blocks (design § 1.2)."""
    lines = text.split("\n")
    blocks: List[_Block] = []
    paragraph: List[str] = []
    i = 0

    def flush() -> None:
        if paragraph:
            blocks.append(_Block("paragraph", " ".join(paragraph)))
            paragraph.clear()

    while i < len(lines):
        line = lines[i]
        fence = _FENCE.match(line)
        if fence:
            flush()
            marker = fence.group(1)
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith(marker):
                j += 1
            blocks.append(_Block("code", count=j - i - 1))
            i = j + 1
            continue
        if (
            _TABLE_ROW.match(line)
            and i + 1 < len(lines)
            and _TABLE_ROW.match(lines[i + 1])
        ):
            flush()
            j = i
            rows = 0
            while j < len(lines) and _TABLE_ROW.match(lines[j]):
                if not _TABLE_RULE.match(lines[j]):
                    rows += 1
                j += 1
            blocks.append(_Block("table", count=max(rows - 1, 0)))
            i = j
            continue
        if (
            _TRACE_START.match(line)
            and i + 1 < len(lines)
            and _TRACE_LINE.match(lines[i + 1])
        ):
            flush()
            j = i
            while j < len(lines) and (
                _TRACE_LINE.match(lines[j]) or lines[j].startswith("    ")
            ):
                j += 1
            blocks.append(_Block("trace", count=j - i))
            i = j
            continue
        if not line.strip():
            flush()
            i += 1
            continue
        heading = _HEADING_LINE.match(line)
        if heading:
            flush()
            blocks.append(_Block("heading", heading.group(1)))
            i += 1
            continue
        item = _ITEM.match(line)
        if item:
            flush()
            items: List[Tuple[str, str]] = []
            j = i
            while j < len(lines):
                current = _ITEM.match(lines[j])
                if current:
                    box = current.group(2)
                    glyph = "" if box is None else ("☑ " if box.strip() else "☐ ")
                    items.append((glyph, current.group(3).strip()))
                    j += 1
                    continue
                probe = lines[j]
                if (
                    not probe.strip()
                    or _FENCE.match(probe)
                    or _HEADING_LINE.match(probe)
                    or _TABLE_ROW.match(probe)
                ):
                    break
                # lazy continuation, as GitHub draws it: the line joins the item
                glyph, body = items[-1]
                items[-1] = (glyph, body + " " + probe.strip())
                j += 1
            blocks.append(_Block("list", items=items))
            i = j
            continue
        paragraph.append(_QUOTE.sub("", line).strip())
        i += 1
    flush()
    return blocks


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


def _cut(text: str, room: int) -> str:
    """``text`` shortened to fit ``room``: at the last sentence end within it,
    else the last clause end (plus ``…``), else the last space (plus ``…``),
    else ``""`` — never inside a word when a boundary exists (R1.2)."""
    if len(text) <= room:
        return text
    if room <= 1:
        return ""
    ends = [end for end in _sentence_ends(text) if end <= room]
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
        f"_… full text: <{url}|GitHub>_"
        if url
        else "_… the full text is on the ticket_"
    )


def condense(text: str, limit: int, url: str = "") -> str:
    """The digest of ``text`` within ``limit`` characters (R1–R3).

    The ask first (bold), then every block in the author's order — lists as
    numbered lines, code / tables / traces as pointers — while the budget holds;
    the block that no longer fits is cut at a sentence; one closing line links
    the full text whenever anything was cut, left out or replaced.
    """
    text = _neutralise(strip_comments(text)).strip()
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
    return text[:limit].rstrip() + f"\n… ({rest} more characters — see the link)"


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
