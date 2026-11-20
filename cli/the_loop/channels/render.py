"""The long form for Slack: defused, then split into ``markdown`` blocks (issue-549, task 6).

The long form is the event's whole text, the words GitHub receives. Slack draws
standard markdown in a ``markdown`` block, so the text goes as written, once it
is defused (:mod:`the_loop.channels.defuse`). This module only decides where it
breaks:

* a part is at most :data:`LONG_FORM_PART_CHARS` characters, one ``markdown``
  block, one thread reply (Slack caps the ``markdown`` blocks of one message at
  12,000 characters together);
* a split falls between top-level markdown blocks (R2.4), never inside a table,
  a code block, a list item or a word;
* one block too large for a part on its own is split at lines (R2.5); a fenced
  code block split this way is closed and reopened with the same fence line; a
  table too large for a part becomes an aligned code block first (R2.3);
* when there is more than one part, each carries an ``(n/m)`` mark (R2.6).

The block boundaries come from the line-based parser the digest used
(:func:`block_spans`, moved here from ``digest.py``, which still uses it). One
pass over the lines; every pattern is linear, so a crafted 64 KB comment costs
what prose costs (abuse case 3). Pure: no Slack, no disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .. import strings
from .defuse import defuse
from .mrkdwn import FENCE_RE, outside_code, unfold

__all__ = [
    "LONG_FORM_PART_CHARS",
    "BlockSpan",
    "LongForm",
    "block_spans",
    "render_long_form",
    "split_long_form",
    "table_as_code",
]

#: The most characters one long-form part holds, mark included: one
#: ``markdown`` block under Slack's 12,000-character total per message, with
#: margin (design.md § Technology choices).
LONG_FORM_PART_CHARS = 11_000

# -- the block parser (from the digest, issue-338) -------------------------------

TABLE_ROW_RE = re.compile(r"^\s*\|")
TABLE_RULE_RE = re.compile(r"^\s*\|?\s*:?-{2,}")
HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
ITEM_RE = re.compile(
    r"^(\s*)(?:[-*+]|\d{1,3}[.)]|[A-Z][.)]|[a-z]\))\s+(?:\[([ xX])\]\s*)?(.*)$"
)
QUOTE_RE = re.compile(r"^\s*>\s?")
TRACE_LINE_RE = re.compile(
    r"^(?:Traceback \(most recent call last\):?\s*$"
    r"|\s+File \".*\", line \d+.*"
    r"|\s+at \S.*"
    r"|[\w.]*(?:Error|Exception)\b.*"
    r"|\s*\^+\s*$)"
)
TRACE_START_RE = re.compile(
    r"^(?:Traceback \(most recent call last\):?\s*$|\s+at \S.*\(.*:\d+.*\)\s*$)"
)


@dataclass(frozen=True)
class BlockSpan:
    """One top-level block: its kind and its lines, ``lines[start:end]``.

    ``kind`` is ``heading``, ``paragraph``, ``list``, ``code``, ``table`` or
    ``trace``. ``closed`` is False only for a code block whose fence never
    closes (it then runs to the end of the text).
    """

    kind: str
    start: int
    end: int
    closed: bool = True


def block_spans(lines: Sequence[str]) -> List[BlockSpan]:
    """The top-level blocks of ``lines``, in order, in one pass. Blank lines
    between blocks belong to none."""
    spans: List[BlockSpan] = []
    paragraph: Optional[int] = None
    count = len(lines)
    i = 0

    def flush(at: int) -> None:
        nonlocal paragraph
        if paragraph is not None:
            spans.append(BlockSpan("paragraph", paragraph, at))
            paragraph = None

    while i < count:
        line = lines[i]
        fence = FENCE_RE.match(line)
        if fence:
            flush(i)
            marker = fence.group(1)
            j = i + 1
            while j < count and not lines[j].lstrip().startswith(marker):
                j += 1
            spans.append(BlockSpan("code", i, min(j + 1, count), closed=j < count))
            i = j + 1
            continue
        if (
            TABLE_ROW_RE.match(line)
            and i + 1 < count
            and TABLE_ROW_RE.match(lines[i + 1])
        ):
            flush(i)
            j = i
            while j < count and TABLE_ROW_RE.match(lines[j]):
                j += 1
            spans.append(BlockSpan("table", i, j))
            i = j
            continue
        if (
            TRACE_START_RE.match(line)
            and i + 1 < count
            and TRACE_LINE_RE.match(lines[i + 1])
        ):
            flush(i)
            j = i
            while j < count and (
                TRACE_LINE_RE.match(lines[j]) or lines[j].startswith("    ")
            ):
                j += 1
            spans.append(BlockSpan("trace", i, j))
            i = j
            continue
        if not line.strip():
            flush(i)
            i += 1
            continue
        if HEADING_LINE_RE.match(line):
            flush(i)
            spans.append(BlockSpan("heading", i, i + 1))
            i += 1
            continue
        if ITEM_RE.match(line):
            flush(i)
            j = i + 1
            while j < count:
                probe = lines[j]
                if ITEM_RE.match(probe):
                    j += 1
                    continue
                if (
                    not probe.strip()
                    or FENCE_RE.match(probe)
                    or HEADING_LINE_RE.match(probe)
                    or TABLE_ROW_RE.match(probe)
                ):
                    break
                j += 1  # a lazy continuation, as GitHub draws it
            spans.append(BlockSpan("list", i, j))
            i = j
            continue
        if paragraph is None:
            paragraph = i
        i += 1
    flush(count)
    return spans


# -- a table as code (R2.3) ------------------------------------------------------

_CELL_SPLIT = re.compile(r"(?<!\\)\|")


def _cells(row: str) -> List[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return [cell.strip() for cell in _CELL_SPLIT.split(row)]


def table_as_code(lines: Sequence[str]) -> List[str]:
    """A markdown table's lines as the lines of a fenced code block, columns
    aligned, every cell kept in its order. The rule line becomes dashes.

    Alignment pads cells; when that would make the block longer than the table
    as written (a crafted table of many empty cells), the rows are kept exactly
    as written instead, so the fallback never grows the text (abuse case 3).
    """
    rows = [_cells(line) for line in lines if not TABLE_RULE_RE.match(line)]
    width = max((len(row) for row in rows), default=0)
    sizes = [0] * width
    for row in rows:
        for index, cell in enumerate(row):
            sizes[index] = max(sizes[index], len(cell))
    drawn: List[str] = []
    for number, row in enumerate(rows):
        padded = row + [""] * (width - len(row))
        drawn.append(
            " | ".join(cell.ljust(sizes[k]) for k, cell in enumerate(padded)).rstrip()
        )
        if number == 0 and len(rows) > 1:
            drawn.append("-+-".join("-" * size for size in sizes))
    if sum(len(line) + 1 for line in drawn) > sum(len(line) + 1 for line in lines):
        drawn = [line.strip() for line in lines]
    return ["```"] + drawn + ["```"]


# -- the splitter (R2.4, R2.5) ---------------------------------------------------


def _split_line(line: str, room: int) -> List[str]:
    """One line too long for ``room``, cut at spaces (never inside a word when
    a space exists within reach). Linear: each cut looks back at most ``room``."""
    pieces: List[str] = []
    while len(line) > room:
        cut = line.rfind(" ", 0, room + 1)
        if cut <= 0:
            cut = room  # one word longer than a part: no boundary exists
            pieces.append(line[:cut])
            line = line[cut:]
        else:
            pieces.append(line[:cut])
            line = line[cut + 1 :]
    pieces.append(line)
    return pieces


def _chunk_lines(
    lines: Sequence[str], first_room: int, room: int, overhead: int
) -> List[List[str]]:
    """``lines`` grouped into chunks whose joined length plus ``overhead`` fits:
    the first chunk in ``first_room``, the others in ``room``. The first chunk
    may be empty, when not even one line fits in ``first_room``."""
    chunks: List[List[str]] = [[]]
    used = 0
    limit = first_room - overhead

    def new_chunk() -> None:
        nonlocal used, limit
        chunks.append([])
        used = 0
        limit = room - overhead

    for line in lines:
        sep = 1 if chunks[-1] else 0
        if used + sep + len(line) <= limit:
            chunks[-1].append(line)
            used += sep + len(line)
            continue
        if chunks[-1] or limit < room - overhead:
            new_chunk()
        if len(line) <= limit:
            chunks[-1].append(line)
            used = len(line)
            continue
        pieces = _split_line(line, limit)
        for piece in pieces[:-1]:
            chunks[-1].append(piece)
            new_chunk()
        chunks[-1].append(pieces[-1])
        used = len(pieces[-1])
    return chunks


def _fence_of(opener: str) -> str:
    """The marker that closes the fence ``opener`` opened (```` ``` ```` or ``~~~``,
    as long as the opener's run)."""
    stripped = opener.lstrip()
    char = stripped[0]
    return char * (len(stripped) - len(stripped.lstrip(char)))


def _oversized(
    kind: str, lines: Sequence[str], closed: bool, first_room: int, room: int
) -> List[str]:
    """One block too large for a part, split at lines: the first piece within
    ``first_room`` (or ``""`` when nothing fits there), the rest within ``room``.
    A code block's pieces each reopen the fence and close it."""
    if kind != "code":
        chunks = _chunk_lines(lines, first_room, room, 0)
        return ["\n".join(chunk) for chunk in chunks]
    opener = lines[0]
    closer = _fence_of(opener)
    body = lines[1:-1] if closed and len(lines) > 1 else lines[1:]
    overhead = len(opener) + len(closer) + 2
    chunks = _chunk_lines(body, first_room, room, overhead)
    return ["\n".join([opener, *chunk, closer]) if chunk else "" for chunk in chunks]


def split_long_form(
    text: str, budget: int = LONG_FORM_PART_CHARS
) -> Tuple[List[str], int]:
    """``(parts, tables_as_code)``: ``text`` split into parts of at most
    ``budget`` characters, in the author's order, and how many tables fell back
    to code. No marks, no defusing: :func:`render_long_form` adds both.

    Whole blocks are packed greedily; the blank lines between two blocks in one
    part are kept as written. A block too large for a part on its own starts in
    the room the current part has left and continues at line boundaries.
    """
    lines = text.split("\n")
    parts: List[str] = []
    current = ""
    previous_end = 0
    tables = 0
    for span in block_spans(lines):
        block_lines = lines[span.start : span.end]
        kind, closed = span.kind, span.closed
        block = "\n".join(block_lines)
        if kind == "table" and len(block) > budget:
            block_lines = table_as_code(block_lines)
            kind, closed = "code", True
            block = "\n".join(block_lines)
            tables += 1
        sep = "\n" * (span.start - previous_end + 1) if current else ""
        previous_end = span.end
        if len(current) + len(sep) + len(block) <= budget:
            current += sep + block
            continue
        if len(block) <= budget:
            parts.append(current)
            current = block
            continue
        first_room = budget - len(current) - len(sep) if current else budget
        pieces = _oversized(kind, block_lines, closed, first_room, budget)
        if pieces[0]:
            current += sep + pieces[0]
        if current:
            parts.append(current)
        parts.extend(pieces[1:-1])
        current = pieces[-1] if len(pieces) > 1 else ""
    if current:
        parts.append(current)
    return [part for part in parts if part.strip()], tables


# -- the long form (R2) ----------------------------------------------------------


@dataclass(frozen=True)
class LongForm:
    """An event's long form, ready to post: one ``markdown`` block per part, in
    order. ``tables_as_code`` counts the tables that fell back to code, for the
    delivery log (non-functional: observability)."""

    parts: Tuple[str, ...] = ()
    tables_as_code: int = 0


def _mark_reserve() -> int:
    return len(strings.t("channels.slack.long-form.part-mark", n=9999, m=9999)) + 2


def render_long_form(text: str, budget: int = LONG_FORM_PART_CHARS) -> LongForm:
    """``text`` as the long form: ``<details>`` opened, defused, split into parts
    of at most ``budget`` characters, each marked ``(n/m)`` when there is more
    than one. Every word of ``text`` is kept (R1.1); empty in, no parts out."""
    text = defuse(outside_code(text, unfold)).strip("\n")
    if not text.strip():
        return LongForm()
    parts, tables = split_long_form(text, budget - _mark_reserve())
    total = len(parts)
    if total > 1:
        parts = [
            strings.t("channels.slack.long-form.part-mark", n=n, m=total)
            + "\n\n"
            + part
            for n, part in enumerate(parts, 1)
        ]
    return LongForm(parts=tuple(parts), tables_as_code=tables)
