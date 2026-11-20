"""GitHub markdown drawn as Slack mrkdwn (issue-338 D3; moved here by issue-549).

Lossless on the words: ``**bold**`` becomes ``*bold*``, headings and task boxes
are drawn with the marks Slack has, links become ``<url|label>``, HTML comments
go and broadcast sequences are neutralised. Code fences and code spans are left
exactly as written. The short form, the ``text`` fallback and the context
lines use it; the long form uses :func:`unfold` before it goes to Slack as
standard markdown (issue-549).

Every pattern is linear in its input (a character class that excludes its own
delimiter, or a line anchor), so a crafted 64 KB comment costs what prose costs.
"""

from __future__ import annotations

import re
from typing import Callable, List

from ..redact import neutralise_broadcasts, strip_html_comments

__all__ = [
    "CODE_SPAN_RE",
    "FENCE_RE",
    "inline",
    "outside_code",
    "strip_comments",
    "to_mrkdwn",
    "unfold",
]


_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_BOLD_UNDERSCORE = re.compile(r"(?<!\w)__([^_\n]+)__(?!\w)")
_STRIKE = re.compile(r"~~([^~\n]+)~~")
_HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_LINK = re.compile(r"!?\[([^\[\]\n]+)\]\(([^()\s]+)\)")
_TASK_DONE = re.compile(r"^(\s*)[-*+]\s+\[[xX]\]\s*", re.MULTILINE)
_TASK_OPEN = re.compile(r"^(\s*)[-*+]\s+\[ \]\s*", re.MULTILINE)
_BULLET = re.compile(r"^(\s*)[-*+]\s+(?=\S)", re.MULTILINE)
#: A collapsed block's tags (issue-472). Slack has no collapsible block and reads
#: `<…>` as link syntax, so the open and close lines go and the summary becomes a
#: bold line of its own; what was collapsed is simply shown.
_DETAILS_TAG = re.compile(r"^[ \t]*</?details\b[^>\n]*>[ \t]*\n?", re.MULTILINE)
_SUMMARY = re.compile(r"<summary\b[^>\n]*>([^<\n]*)</summary>")
#: `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^…>` — the one thing in a
#: comment's text that ACTS on Slack (A2). Rewritten after the comment scan, so
#: the-loop's own `<!-- … -->` markers are already gone. Both rules live in
#: :mod:`the_loop.redact` since issue-389, because the ledger applies them to a
#: quoted snapshot too; this module keeps its names for its own callers.
strip_comments = strip_html_comments


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
    return _LINK.sub(_link, text)


def _link(match: "re.Match[str]") -> str:
    """A markdown link as Slack's ``<url|label>`` only when its target is an
    ``http``, ``https`` or ``mailto`` URL. Anything else (``!channel``, ``@U…``,
    a link nested in a label that defuse left as text) stays text, so this step
    never makes a control sequence (abuse cases 1, 2, 4)."""
    label, target = match.group(1), match.group(2)
    if not re.match(r"(?:https?://|mailto:)", target, re.IGNORECASE):
        return match.group(0)
    return f"<{target}|{label}>"


def _inline(text: str) -> str:
    """The inline rules — emphasis, strike, links — on text whose line-level
    shape (headings, bullets) the caller has already handled; code spans kept."""
    return _outside_code(text, _inline_rules)


def _neutralise(text: str) -> str:
    return neutralise_broadcasts(text)


def _unfold(text: str) -> str:
    """``<details>`` blocks opened: the tags dropped, each summary drawn bold."""
    return _SUMMARY.sub(r"**\1**", _DETAILS_TAG.sub("", text))


def _line_rules(text: str) -> str:
    text = _unfold(text)
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


# Public names for the modules that build on this one (the renderer, the
# short-form builder).
CODE_SPAN_RE = _CODE_SPAN
FENCE_RE = _FENCE
outside_code = _outside_code
inline = _inline
unfold = _unfold
