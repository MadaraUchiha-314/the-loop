"""Text from GitHub made inert before Slack parses it (issue-549, task 5).

The Slack channel posts text it does not control: GitHub comments and reviews,
CI output a session quoted, and the session's own short form. Slack acts on some
of that text: ``<!here>`` pages a channel, ``<@U…>`` notifies a person, and
``<url|label>`` opens a link. :func:`defuse` applies five steps, in the order
design.md § Security design fixes, to the short form and the long form alike:

1. strip the-loop's markers and other HTML comments (R2.8);
2. neutralise broadcast sequences (abuse case 1);
3. defuse user mentions (abuse case 2): the only live mentions are the ones the
   channel adds afterwards, from configuration (R7);
4. keep only ``http``, ``https`` and ``mailto`` links; any other link is text
   (abuse case 4);
5. escape the angle-bracket syntax left, so no cell, heading or label can open
   a link or a mention.

The steps work on the whole text, so a table cell, a heading and a link label
are covered as prose is. A code fence is no exception: whether Slack parses
inside one is not documented, so the defuser fails closed. Each pattern is
linear in its input (a character class that excludes its own delimiter), so a
64 KB comment costs what prose costs (abuse case 3).
"""

from __future__ import annotations

import re

from ..redact import neutralise_broadcasts, strip_html_comments

__all__ = [
    "MARKDOWN_LINK_RE",
    "SAFE_SCHEMES",
    "USER_MENTION_RE",
    "defuse",
    "defuse_user_mentions",
    "escape_angle_brackets",
    "keep_safe_links",
    "neutralise_broadcasts",
    "strip_html_comments",
]

#: A Slack user mention in text: ``<@U…>`` or ``<@W…>``, with or without a
#: ``|label``. It becomes the plain ``@U…``, which notifies no one.
USER_MENTION_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")

#: A markdown link or image: ``[label](target)``, the target bare (one level of
#: balanced parentheses allowed, as GitHub reads ``javascript:alert(1)``) or in
#: angle brackets.
MARKDOWN_LINK_RE = re.compile(
    r"!?\[([^\[\]\n]+)\]\((?:<([^<>\n]*)>|((?:[^()\s]|\([^()\s]*\))+))\)"
)

#: A reference definition, ``[1]: target``, which makes ``[label][1]`` a link.
_DEFINITION_RE = re.compile(
    r"^( {0,3})\[([^\]\n]+)\]:[ \t]*<?([^\s<>]+)>?", re.MULTILINE
)

#: The link schemes that stay links. Any other scheme, and a link with none,
#: is shown as text.
SAFE_SCHEMES = frozenset({"http", "https", "mailto"})

_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")

#: Markdown's autolink, ``<https://…>``: unwrapped to the bare URL, which Slack
#: links on its own. Anything else in angle brackets is escaped by step 5.
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^\s<>|]+)>", re.IGNORECASE)

#: The characters that would end a target once it is drawn as ``<url|label>``.
_TARGET_ESCAPES = {"|": "%7C", "<": "%3C", ">": "%3E", " ": "%20"}


def _is_safe(target: str) -> bool:
    scheme = _SCHEME.match(target)
    return bool(scheme) and scheme.group(1).lower() in SAFE_SCHEMES


def defuse_user_mentions(text: str) -> str:
    """Step 3: ``<@U123|name>`` becomes ``@U123``, inert."""
    return USER_MENTION_RE.sub(r"@\1", text)


def keep_safe_links(text: str) -> str:
    """Step 4: a markdown link to ``http``, ``https`` or ``mailto`` stays a link,
    with the characters that could close a Slack link percent-encoded. Any other
    link becomes ``label (target)``, plain text, and a reference definition to
    an unsafe target is escaped so it defines nothing. A safe autolink is
    unwrapped."""

    def link(match: "re.Match[str]") -> str:
        whole, label = match.group(0), match.group(1)
        target = match.group(2) if match.group(2) is not None else match.group(3)
        if not _is_safe(target):
            return f"{label} ({target})"
        for char, code in _TARGET_ESCAPES.items():
            target = target.replace(char, code)
        bang = "!" if whole.startswith("!") else ""
        return f"{bang}[{label}]({target})"

    def definition(match: "re.Match[str]") -> str:
        if _is_safe(match.group(3)):
            return match.group(0)
        # `\[` makes the line text: no reference link can point at it
        return match.group(1) + "\\" + match.group(0)[len(match.group(1)) :]

    text = MARKDOWN_LINK_RE.sub(link, text)
    text = _DEFINITION_RE.sub(definition, text)
    return _AUTOLINK.sub(r"\1", text)


def escape_angle_brackets(text: str) -> str:
    """Step 5: every ``<`` left becomes ``&lt;``, so nothing can open Slack's
    ``<…>`` syntax. A ``>`` alone opens nothing, so block quotes and arrows keep
    their shape."""
    return text.replace("<", "&lt;")


def defuse(text: str) -> str:
    """``text`` with the five steps applied, in order. Every word is kept.
    Idempotent: defusing a defused text changes nothing."""
    if not text:
        return ""
    text = strip_html_comments(text)
    text = neutralise_broadcasts(text)
    text = defuse_user_mentions(text)
    text = keep_safe_links(text)
    return escape_angle_brackets(text)
