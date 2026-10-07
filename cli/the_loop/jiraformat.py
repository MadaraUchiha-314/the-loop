"""Markdown ⇄ Jira bodies (issue-475, design §C6, R4.5, R5.5).

the-loop writes Markdown — ``render()``, the gate comments, the PR briefing, the
phase-selection checklist. Jira takes **ADF** (Atlassian Document Format) on
Cloud's REST v3 and **wiki markup** on Data Center's REST v2. This module is the
one conversion, both ways, and :class:`~the_loop.jiraapi.JiraClient` is its only
caller on the wire.

Writing: the Markdown is parsed once with ``markdown-it-py`` (CommonMark, plus
GFM tables and strikethrough) into ADF; wiki markup is serialised **from that
ADF**, so the two outputs cannot disagree about what a construct is.

=====================  ==================================  =====================
Markdown               ADF (v3)                            wiki (v2)
=====================  ==================================  =====================
``#``…``######``       ``heading{level}``                  ``h1.``…``h6.``
``**b**`` ``_i_``      ``strong`` / ``em`` marks           ``*b*`` ``_i_``
`` `code` ``           ``code`` mark                       ``{{code}}``
``[t](u)``             ``link`` mark                       ``[t|u]``
``-`` / ``1.`` lists   ``bulletList`` / ``orderedList``    ``*`` / ``#``
``- [ ]`` ``- [x]``    ``taskList`` / ``taskItem{state}``  ``* (x)`` / ``* (/)``
fenced code            ``codeBlock{language}``             ``{code:lang}``
tables                 ``table``/``tableHeader``/…         ``||h||`` / ``|c|``
``> quote``            ``blockquote``                      ``{quote}``
``---``                ``rule``                            ``----``
=====================  ==================================  =====================

``<details>``, HTML comments and other raw HTML are dropped; a ``<summary>``'s
text is kept as a bold paragraph. One kind of HTML comment is **kept**: a bare
the-loop marker, ``<!-- the-loop:<name> -->``. The gates find their own comments
by these (``the-loop:phase-selection``, ``the-loop:goal-request``, …), and Jira
has no hidden text, so each becomes a visible ``[the-loop:<name>]`` sentinel and
reading turns a paragraph holding only that sentinel back into the HTML comment
— so a gate reads a Jira ticket exactly as it reads a GitHub issue. The
self-authored sentinel ``[the-loop:agent-comment]`` is the exception: it stays
literal text on read, because it *is* the Jira self-marker (``authz``). An
envelope (``<!-- the-loop:event {…} -->``) carries a payload and is dropped.

A Jira task item is a checkbox a person ticks in place, so the phase-selection
checklist is ticked on the ticket, and :func:`adf_to_markdown` turns a
``taskItem{state: DONE}`` back into ``- [x] …`` for ``selection``'s parser. On
wiki markup there are no checkboxes: a row is ``* (/) …`` (ticked) or
``* (x) …`` (not), and a person changes the icon.

Reading: :func:`adf_to_markdown` and :func:`wiki_to_markdown` produce the
Markdown the router and the gate hooks see. Text is **not** Markdown-escaped on
the way back — its readers are regexes and an agent, not a renderer. An ADF
node this module does not know is read as its plain text, with a debug log
naming the node type; nothing is dropped silently.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger("the-loop.jiraformat")

__all__ = [
    "SELF_SENTINEL_NAME",
    "adf_to_markdown",
    "adf_to_wiki",
    "from_jira",
    "markdown_to_adf",
    "markdown_to_wiki",
    "to_jira",
    "wiki_to_markdown",
]

#: The marker name that stays visible text when read back (the Jira self-marker).
SELF_SENTINEL_NAME = "agent-comment"

#: A bare the-loop marker inside HTML: ``<!-- the-loop:phase-selection -->``.
_MARKER_IN_HTML = re.compile(r"<!--\s*the-loop:([a-z0-9][a-z0-9:-]*)\s*-->")
_SUMMARY = re.compile(r"<summary\b[^>]*>(.*?)</summary>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
#: A paragraph that is nothing but a sentinel: ``[the-loop:phase-selection]``.
_SENTINEL_LINE = re.compile(r"^\[the-loop:([a-z0-9][a-z0-9:-]*)\]$")
_TASK_PREFIX = re.compile(r"^\[([ xX])\]\s+")
_BREAK_TAG = re.compile(r"^<br\s*/?>$", re.IGNORECASE)
_TAG_NAME = re.compile(r"^</?([A-Za-z][A-Za-z0-9-]*)")
#: Inline elements GitHub renders (or strips) as markup; an inline "tag" that is
#: none of these — ``<PR title>``, ``<path>`` — is a placeholder and kept as text.
_HTML_ELEMENTS = frozenset(
    "a abbr b bdi bdo br cite code data del dfn em i img ins kbd mark q rp rt "
    "ruby s samp small span strong sub summary sup time u var wbr details div p "
    "pre table tr td th thead tbody hr h1 h2 h3 h4 h5 h6 ul ol li dl dt dd "
    "blockquote picture source video".split()
)

#: The languages Jira's ``{code}`` macro formats; any other renders as ``{code}``.
_WIKI_LANGUAGES = frozenset(
    "actionscript ada applescript bash c c# c++ cpp css erlang go groovy haskell "
    "html java javascript js json lua none nyan objc perl php python r rainbow "
    "ruby scala sh sql swift visualbasic xml yaml".split()
)

_parser: Any = None


def _markdown_parser() -> Any:
    global _parser
    if _parser is None:
        from markdown_it import MarkdownIt

        _parser = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    return _parser


# ---------------------------------------------------------------- the dispatch


def to_jira(markdown: str, rest_version: str) -> Any:
    """``markdown`` as the body REST ``rest_version`` takes: ADF on 3, wiki on 2."""
    if str(rest_version) == "3":
        return markdown_to_adf(markdown)
    return markdown_to_wiki(markdown)


def from_jira(body: Any) -> str:
    """A body Jira returned, as Markdown: ADF (a mapping) or wiki (a string)."""
    if isinstance(body, str):
        return wiki_to_markdown(body)
    if isinstance(body, Mapping):
        return adf_to_markdown(body)
    return ""


# ============================================================ Markdown → ADF


class _Ids:
    """Deterministic ``localId``s for task lists and items (golden-file stable)."""

    def __init__(self) -> None:
        self.lists = 0
        self.items = 0

    def task_list(self) -> str:
        self.lists += 1
        return f"the-loop-tasks-{self.lists}"

    def task_item(self) -> str:
        self.items += 1
        return f"the-loop-task-{self.items}"


def markdown_to_adf(markdown: str) -> Dict[str, Any]:
    """``markdown`` as an ADF document (Jira Cloud, REST v3)."""
    from markdown_it.tree import SyntaxTreeNode

    root = SyntaxTreeNode(_markdown_parser().parse(markdown or ""))
    return {"type": "doc", "version": 1, "content": _blocks(root.children, _Ids())}


def _text(text: str, marks: Sequence[Mapping[str, Any]] = ()) -> Dict[str, Any]:
    node: Dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = [dict(m) for m in marks]
    return node


def _paragraph(content: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"type": "paragraph", "content": content}


def _blocks(nodes: Iterable[Any], ids: _Ids) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node in nodes:
        out.extend(_block(node, ids))
    return out


def _inline_of(node: Any) -> List[Any]:
    """The inline children of a block that holds one ``inline`` token."""
    for child in node.children:
        if child.type == "inline":
            return list(child.children)
    return []


def _block(node: Any, ids: _Ids) -> List[Dict[str, Any]]:
    kind = node.type
    if kind == "paragraph":
        content = _inline(_inline_of(node), ())
        return [_paragraph(content)] if content else []
    if kind == "heading":
        return [
            {
                "type": "heading",
                "attrs": {"level": int(node.tag[1:])},
                "content": _inline(_inline_of(node), ()),
            }
        ]
    if kind == "bullet_list":
        tasks = _task_list(node, ids)
        if tasks is not None:
            return [tasks]
        return [{"type": "bulletList", "content": _items(node, ids)}]
    if kind == "ordered_list":
        start = int((node.attrs or {}).get("start") or 1)
        return [
            {
                "type": "orderedList",
                "attrs": {"order": start},
                "content": _items(node, ids),
            }
        ]
    if kind == "blockquote":
        return [
            {"type": "blockquote", "content": _quotable(_blocks(node.children, ids))}
        ]
    if kind in ("fence", "code_block"):
        language = (node.info or "").strip().split(" ")[0] if kind == "fence" else ""
        code = node.content.rstrip("\n")
        block: Dict[str, Any] = {"type": "codeBlock"}
        if language:
            block["attrs"] = {"language": language}
        if code:
            block["content"] = [_text(code)]
        return [block]
    if kind == "hr":
        return [{"type": "rule"}]
    if kind == "html_block":
        return _html_block(node.content)
    if kind == "table":
        return [_table(node)]
    logger.debug("markdown block %r has no Jira form; kept as text", kind)
    text = node.content or ""
    return [_paragraph([_text(text)])] if text.strip() else []


def _quotable(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """ADF's blockquote takes no heading: one becomes a bold paragraph."""
    out = []
    for block in blocks:
        if block.get("type") == "heading":
            block = _paragraph(
                [
                    _text(n["text"], [*n.get("marks", []), {"type": "strong"}])
                    if n.get("type") == "text"
                    else n
                    for n in block.get("content", [])
                ]
            )
        out.append(block)
    return out


def _items(node: Any, ids: _Ids) -> List[Dict[str, Any]]:
    items = []
    for item in node.children:
        content = _blocks(item.children, ids)
        if not content or content[0].get("type") != "paragraph":
            content.insert(0, _paragraph([]))
        items.append({"type": "listItem", "content": content})
    return items


def _task_list(node: Any, ids: _Ids) -> Optional[Dict[str, Any]]:
    """A bullet list whose every item opens with ``[ ]``/``[x]`` — or ``None``.

    An item holding anything beyond its one line (a nested list, a second
    paragraph) keeps the list an ordinary bullet list: a Jira task item holds
    inline content only, and dropping the rest would lose words.
    """
    rows = []
    for item in node.children:
        if len(item.children) != 1 or item.children[0].type != "paragraph":
            return None
        inline = _inline_of(item.children[0])
        if not inline or inline[0].type != "text":
            return None
        match = _TASK_PREFIX.match(inline[0].content)
        if not match:
            return None
        rows.append((match, inline))
    if not rows:
        return None
    list_id = ids.task_list()
    items = []
    for match, inline in rows:
        first = inline[0]
        rest = first.content[match.end() :]
        content = ([_text(rest)] if rest else []) + _inline(inline[1:], ())
        items.append(
            {
                "type": "taskItem",
                "attrs": {
                    "localId": ids.task_item(),
                    "state": "TODO" if match.group(1) == " " else "DONE",
                },
                "content": _merge(content),
            }
        )
    return {"type": "taskList", "attrs": {"localId": list_id}, "content": items}


def _html_block(html: str) -> List[Dict[str, Any]]:
    """Raw HTML is dropped, except a ``<summary>`` (bold) and a bare marker."""
    found = []
    for match in _SUMMARY.finditer(html):
        text = _TAG.sub("", match.group(1)).strip()
        if text:
            found.append(
                (match.start(), _paragraph([_text(text, [{"type": "strong"}])]))
            )
    for match in _MARKER_IN_HTML.finditer(html):
        found.append(
            (match.start(), _paragraph([_text(f"[the-loop:{match.group(1)}]")]))
        )
    return [block for _, block in sorted(found, key=lambda pair: pair[0])]


def _table(node: Any) -> Dict[str, Any]:
    rows = []
    for section in node.children:  # thead, tbody
        for row in section.children:
            cells = []
            for cell in row.children:
                content = _inline(_inline_of(cell), ())
                cells.append(
                    {
                        "type": "tableHeader" if cell.type == "th" else "tableCell",
                        "attrs": {},
                        "content": [_paragraph(content)],
                    }
                )
            rows.append({"type": "tableRow", "content": cells})
    return {
        "type": "table",
        "attrs": {"isNumberColumnEnabled": False, "layout": "default"},
        "content": rows,
    }


def _inline(
    nodes: Iterable[Any], marks: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node in nodes:
        kind = node.type
        if kind == "text":
            if node.content:
                out.append(_text(node.content, marks))
        elif kind in ("softbreak", "hardbreak"):
            # GitHub renders a comment's single newline as a break; so does this.
            out.append({"type": "hardBreak"})
        elif kind == "code_inline":
            # ADF's code mark combines with a link mark only.
            kept = [m for m in marks if m.get("type") == "link"]
            out.append(_text(node.content, [*kept, {"type": "code"}]))
        elif kind == "em":
            out.extend(_inline(node.children, [*marks, {"type": "em"}]))
        elif kind == "strong":
            out.extend(_inline(node.children, [*marks, {"type": "strong"}]))
        elif kind == "s":
            out.extend(_inline(node.children, [*marks, {"type": "strike"}]))
        elif kind == "link":
            href = str((node.attrs or {}).get("href") or "")
            link = {"type": "link", "attrs": {"href": href}}
            out.extend(_inline(node.children, [*marks, link]))
        elif kind == "image":
            src = str((node.attrs or {}).get("src") or "")
            alt = "".join(c.content for c in node.children if c.type == "text") or src
            out.append(_text(alt, [*marks, {"type": "link", "attrs": {"href": src}}]))
        elif kind == "html_inline":
            html = node.content.strip()
            marker = _MARKER_IN_HTML.fullmatch(html)
            if marker:
                out.append(_text(f"[the-loop:{marker.group(1)}]", marks))
            elif _BREAK_TAG.match(html):
                out.append({"type": "hardBreak"})
            elif not _is_html_element(html):
                # `<PR title>` is a placeholder, not markup: its words are kept.
                out.append(_text(node.content, marks))
            # any other inline HTML is dropped; its text children are kept
        else:
            logger.debug("markdown inline %r has no Jira form; kept as text", kind)
            if node.content:
                out.append(_text(node.content, marks))
    return _merge(out)


def _is_html_element(html: str) -> bool:
    """Whether inline ``html`` is a tag a renderer would treat as markup."""
    if html.startswith("<!--"):
        return True
    match = _TAG_NAME.match(html)
    return bool(match) and match.group(1).lower() in _HTML_ELEMENTS


def _merge(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Adjacent text nodes with the same marks become one."""
    merged: List[Dict[str, Any]] = []
    for node in nodes:
        if (
            merged
            and node.get("type") == "text"
            and merged[-1].get("type") == "text"
            and merged[-1].get("marks") == node.get("marks")
        ):
            merged[-1] = {**merged[-1], "text": merged[-1]["text"] + node["text"]}
        else:
            merged.append(node)
    return merged


# ============================================================ ADF → Markdown


def adf_to_markdown(doc: Any) -> str:
    """An ADF document (or node) as Markdown — what a gate reads."""
    if not isinstance(doc, Mapping):
        return ""
    nodes = doc.get("content") if doc.get("type") == "doc" else [doc]
    return _md_blocks(nodes or []).strip("\n")


def _md_blocks(nodes: Iterable[Any]) -> str:
    parts = [_md_block(node) for node in nodes if isinstance(node, Mapping)]
    return "\n\n".join(part for part in parts if part != "")


def _indent(text: str, prefix: str, width: int) -> str:
    """``prefix`` on the first line, ``width`` spaces on the rest."""
    lines = text.split("\n")
    pad = " " * width
    return "\n".join(
        [prefix + lines[0]] + [(pad + line) if line else "" for line in lines[1:]]
    )


def _md_block(node: Mapping[str, Any]) -> str:
    kind = node.get("type")
    content = node.get("content") or []
    attrs = node.get("attrs") or {}
    if kind == "paragraph":
        text = _md_inline(content)
        sentinel = _SENTINEL_LINE.match(text.strip())
        if sentinel and sentinel.group(1) != SELF_SENTINEL_NAME:
            return f"<!-- the-loop:{sentinel.group(1)} -->"
        return text
    if kind == "heading":
        level = min(max(int(attrs.get("level") or 1), 1), 6)
        return "#" * level + " " + _md_inline(content)
    if kind == "bulletList":
        return "\n".join(_md_item(item, "- ") for item in content)
    if kind == "orderedList":
        start = int(attrs.get("order") or 1)
        return "\n".join(
            _md_item(item, f"{start + n}. ") for n, item in enumerate(content)
        )
    if kind == "taskList":
        lines = []
        for item in content:
            if item.get("type") == "taskList":
                lines.append(_indent(_md_block(item), "  ", 2))
                continue
            state = (item.get("attrs") or {}).get("state")
            box = "[x]" if state == "DONE" else "[ ]"
            lines.append(_indent(_md_inline(item.get("content") or []), f"- {box} ", 2))
        return "\n".join(lines)
    if kind == "codeBlock":
        language = str(attrs.get("language") or "")
        code = "".join(str(n.get("text") or "") for n in content)
        fence = "````" if "```" in code else "```"
        return f"{fence}{language}\n{code}\n{fence}"
    if kind == "blockquote":
        inner = _md_blocks(content)
        return "\n".join(f"> {line}" if line else ">" for line in inner.split("\n"))
    if kind == "rule":
        return "---"
    if kind == "table":
        return _md_table(content)
    if kind in ("panel", "layoutSection", "layoutColumn", "bodiedExtension"):
        return _md_blocks(content)
    if kind in ("expand", "nestedExpand"):
        title = str(attrs.get("title") or "")
        body = _md_blocks(content)
        return f"**{title}**\n\n{body}" if title else body
    if kind in ("mediaSingle", "mediaGroup", "media", "extension"):
        logger.debug("ADF %s node has no Markdown form; skipped", kind)
        return ""
    logger.debug("ADF block %r is not known; read as its text", kind)
    if content and all(
        isinstance(c, Mapping) and c.get("type") in _BLOCK_TYPES for c in content
    ):
        return _md_blocks(content)
    return _md_inline(content) if content else str(node.get("text") or "")


_BLOCK_TYPES = frozenset(
    {
        "paragraph",
        "heading",
        "bulletList",
        "orderedList",
        "taskList",
        "codeBlock",
        "blockquote",
        "rule",
        "table",
        "panel",
        "expand",
        "nestedExpand",
        "mediaSingle",
        "mediaGroup",
    }
)


def _md_item(item: Mapping[str, Any], marker: str) -> str:
    children = [c for c in item.get("content") or [] if isinstance(c, Mapping)]
    text = "\n".join(_md_block(child) for child in children)
    return _indent(text, marker, len(marker))


def _md_table(rows: Sequence[Any]) -> str:
    lines = []
    for index, row in enumerate(rows):
        cells = [
            " ".join(_md_block(block) for block in (cell.get("content") or []))
            .replace("\n", " ")
            .replace("|", "\\|")
            for cell in (row.get("content") or [])
            if isinstance(cell, Mapping)
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join("---" for _ in cells) + " |")
    return "\n".join(lines)


def _md_inline(nodes: Sequence[Any]) -> str:
    return "".join(_md_inline_node(n) for n in nodes if isinstance(n, Mapping))


def _md_inline_node(node: Mapping[str, Any]) -> str:
    kind = node.get("type")
    attrs = node.get("attrs") or {}
    if kind == "text":
        return _md_marked(str(node.get("text") or ""), node.get("marks") or [])
    if kind == "hardBreak":
        return "\n"
    if kind == "mention":
        return str(attrs.get("text") or f"@{attrs.get('id') or ''}")
    if kind == "emoji":
        return str(attrs.get("text") or attrs.get("shortName") or "")
    if kind == "inlineCard":
        return str(attrs.get("url") or "")
    if kind == "status":
        return str(attrs.get("text") or "")
    if kind == "date":
        return str(attrs.get("timestamp") or "")
    logger.debug("ADF inline %r is not known; read as its text", kind)
    return _md_inline(node.get("content") or []) or str(node.get("text") or "")


def _md_marked(text: str, marks: Sequence[Any]) -> str:
    kinds = {str(m.get("type")): m for m in marks if isinstance(m, Mapping)}
    if "code" in kinds:
        tick = "``" if "`" in text else "`"
        text = f"{tick}{text}{tick}"
    if "em" in kinds:
        text = f"_{text}_"
    if "strong" in kinds:
        text = f"**{text}**"
    if "strike" in kinds:
        text = f"~~{text}~~"
    if "link" in kinds:
        href = str((kinds["link"].get("attrs") or {}).get("href") or "")
        text = f"[{text}]({href})"
    return text


# ================================================================ ADF → wiki


def markdown_to_wiki(markdown: str) -> str:
    """``markdown`` as Jira wiki markup (Data Center, REST v2)."""
    return adf_to_wiki(markdown_to_adf(markdown))


def adf_to_wiki(doc: Mapping[str, Any]) -> str:
    nodes = doc.get("content") if doc.get("type") == "doc" else [doc]
    return _wiki_blocks(nodes or [])


def _wiki_blocks(nodes: Iterable[Any]) -> str:
    parts = [_wiki_block(node) for node in nodes if isinstance(node, Mapping)]
    return "\n\n".join(part for part in parts if part != "")


def _wiki_block(node: Mapping[str, Any]) -> str:
    kind = node.get("type")
    content = node.get("content") or []
    attrs = node.get("attrs") or {}
    if kind == "paragraph":
        return _wiki_inline(content)
    if kind == "heading":
        return f"h{int(attrs.get('level') or 1)}. " + _wiki_inline(content)
    if kind in ("bulletList", "orderedList", "taskList"):
        return "\n".join(_wiki_list(node, ""))
    if kind == "codeBlock":
        language = str(attrs.get("language") or "").lower()
        code = "".join(str(n.get("text") or "") for n in content)
        opener = "{code:" + language + "}" if language in _WIKI_LANGUAGES else "{code}"
        return f"{opener}\n{code}\n{{code}}"
    if kind == "blockquote":
        return "{quote}\n" + _wiki_blocks(content) + "\n{quote}"
    if kind == "rule":
        return "----"
    if kind == "table":
        lines = []
        for row in content:
            cells = [c for c in row.get("content") or [] if isinstance(c, Mapping)]
            texts = [
                " ".join(
                    _wiki_inline(b.get("content") or [], in_cell=True)
                    for b in cell.get("content") or []
                )
                for cell in cells
            ]
            if cells and all(c.get("type") == "tableHeader" for c in cells):
                lines.append("||" + "||".join(texts) + "||")
            else:
                lines.append("|" + "|".join(texts) + "|")
        return "\n".join(lines)
    return _wiki_blocks(content) if content else ""


def _wiki_list(node: Mapping[str, Any], prefix: str) -> List[str]:
    kind = node.get("type")
    char = "#" if kind == "orderedList" else "*"
    lines: List[str] = []
    for item in node.get("content") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("type") in ("bulletList", "orderedList", "taskList"):
            lines.extend(_wiki_list(item, prefix + char))
            continue
        if item.get("type") == "taskItem":
            icon = "(/)" if (item.get("attrs") or {}).get("state") == "DONE" else "(x)"
            text = _wiki_inline(item.get("content") or [], in_cell=True)
            lines.append(f"{prefix}{char} {icon} {text}")
            continue
        first = True
        for child in item.get("content") or []:
            if not isinstance(child, Mapping):
                continue
            if child.get("type") in ("bulletList", "orderedList", "taskList"):
                lines.extend(_wiki_list(child, prefix + char))
            elif first:
                text = _wiki_inline(child.get("content") or [], in_cell=True)
                lines.append(f"{prefix}{char} {text}")
                first = False
            else:
                lines.append(_wiki_block(child))
        if first:
            lines.append(f"{prefix}{char} ")
    return lines


def _wiki_inline(nodes: Sequence[Any], in_cell: bool = False) -> str:
    out = []
    for node in nodes:
        if not isinstance(node, Mapping):
            continue
        kind = node.get("type")
        if kind == "text":
            out.append(
                _wiki_marked(str(node.get("text") or ""), node.get("marks") or [])
            )
        elif kind == "hardBreak":
            # Inside a list item or a table cell a newline would end the row.
            out.append(" \\\\ " if in_cell else "\n")
        else:
            out.append(_wiki_escape(_md_inline_node(node)))
    return "".join(out)


_WIKI_SPECIAL = re.compile(r"([{}\[\]|*_^~])")
_URL = re.compile(r"https?://[^\s<>\[\]{}|]+")


def _wiki_escape(text: str) -> str:
    """Escape what wiki markup would read as markup — outside bare URLs."""

    def escape(part: str) -> str:
        return _WIKI_SPECIAL.sub(r"\\\1", part.replace("\\", "&#92;"))

    out, position = [], 0
    for match in _URL.finditer(text):
        out.append(escape(text[position : match.start()]))
        out.append(match.group(0))
        position = match.end()
    out.append(escape(text[position:]))
    return "".join(out)


def _wiki_marked(text: str, marks: Sequence[Any]) -> str:
    kinds = {str(m.get("type")): m for m in marks if isinstance(m, Mapping)}
    if "code" in kinds:
        text = "{{" + text + "}}"
    else:
        text = _wiki_escape(text)
    if "em" in kinds:
        text = f"_{text}_"
    if "strong" in kinds:
        text = f"*{text}*"
    if "strike" in kinds:
        text = f"-{text}-"
    if "link" in kinds:
        href = str((kinds["link"].get("attrs") or {}).get("href") or "")
        text = f"[{text}|{href}]"
    return text


# =========================================================== wiki → Markdown

_WIKI_HEADING = re.compile(r"^h([1-6])\.\s*(.*)$")
_WIKI_CODE_OPEN = re.compile(r"^\{(code|noformat)(?::([^}]*))?\}\s*$")
_WIKI_LIST = re.compile(r"^([*#-]+)\s+(.*)$")
_WIKI_TASK = re.compile(r"^\((/|x)\)\s+(.*)$")


def wiki_to_markdown(text: str) -> str:
    """Jira wiki markup as Markdown — what a gate reads on Data Center."""
    lines = str(text or "").replace("\r\n", "\n").split("\n")
    blocks: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        code = _WIKI_CODE_OPEN.match(stripped)
        if code:
            closer = "{" + code.group(1) + "}"
            body, i = [], i + 1
            while i < len(lines) and lines[i].strip() != closer:
                body.append(lines[i])
                i += 1
            i += 1
            language = (code.group(2) or "").split("|")[0].strip()
            language = "" if "=" in language else language
            blocks.append(f"```{language}\n" + "\n".join(body) + "\n```")
            continue
        if stripped == "{quote}":
            body, i = [], i + 1
            while i < len(lines) and lines[i].strip() != "{quote}":
                body.append(lines[i])
                i += 1
            i += 1
            inner = wiki_to_markdown("\n".join(body))
            blocks.append(
                "\n".join(f"> {ln}" if ln else ">" for ln in inner.split("\n"))
            )
            continue
        heading = _WIKI_HEADING.match(stripped)
        if heading:
            blocks.append(
                "#" * int(heading.group(1)) + " " + _wiki_inline_md(heading.group(2))
            )
            i += 1
            continue
        if re.fullmatch(r"-{4,}", stripped):
            blocks.append("---")
            i += 1
            continue
        if _WIKI_LIST.match(stripped) and not stripped.startswith("----"):
            rows = []
            while i < len(lines) and _WIKI_LIST.match(lines[i].strip()):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(_wiki_list_md(rows))
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(_wiki_table_md(rows))
            continue
        paragraph = []
        while i < len(lines) and lines[i].strip() and not _wiki_block_start(lines[i]):
            paragraph.append(lines[i].strip())
            i += 1
        if not paragraph:  # a block opener the loop above did not take
            paragraph.append(stripped)
            i += 1
        md = _wiki_inline_md("\n".join(paragraph))
        sentinel = _SENTINEL_LINE.match(md.strip())
        if sentinel and sentinel.group(1) != SELF_SENTINEL_NAME:
            md = f"<!-- the-loop:{sentinel.group(1)} -->"
        blocks.append(md)
    return "\n\n".join(blocks)


def _wiki_block_start(line: str) -> bool:
    stripped = line.strip()
    return bool(
        _WIKI_CODE_OPEN.match(stripped)
        or stripped == "{quote}"
        or _WIKI_HEADING.match(stripped)
        or re.fullmatch(r"-{4,}", stripped)
        or _WIKI_LIST.match(stripped)
        or stripped.startswith("|")
    )


def _wiki_list_md(rows: Sequence[str]) -> str:
    out = []
    counters: Dict[int, int] = {}
    for row in rows:
        match = _WIKI_LIST.match(row)
        if not match:
            continue
        markers, text = match.group(1), match.group(2)
        depth = len(markers)
        pad = "  " * (depth - 1)
        for deeper in [d for d in counters if d > depth]:
            del counters[deeper]
        if markers[-1] == "#":
            counters[depth] = counters.get(depth, 0) + 1
            out.append(f"{pad}{counters[depth]}. {_wiki_inline_md(text)}")
            continue
        counters.pop(depth, None)
        task = _WIKI_TASK.match(text)
        if task:
            box = "[x]" if task.group(1) == "/" else "[ ]"
            out.append(f"{pad}- {box} {_wiki_inline_md(task.group(2))}")
        else:
            out.append(f"{pad}- {_wiki_inline_md(text)}")
    return "\n".join(out)


def _split_cells(row: str, separator: str) -> List[str]:
    body = row.strip()
    if body.startswith(separator):
        body = body[len(separator) :]
    if body.endswith(separator) and not body.endswith("\\" + separator):
        body = body[: -len(separator)]
    cells, current, i = [], "", 0
    while i < len(body):
        if body[i] == "\\" and i + 1 < len(body):
            current += body[i : i + 2]
            i += 2
            continue
        if body.startswith(separator, i):
            cells.append(current)
            current = ""
            i += len(separator)
            continue
        current += body[i]
        i += 1
    cells.append(current)
    return [cell.strip() for cell in cells]


def _wiki_table_md(rows: Sequence[str]) -> str:
    lines = []
    for index, row in enumerate(rows):
        separator = "||" if row.startswith("||") else "|"
        cells = [
            _wiki_inline_md(c).replace("|", "\\|") for c in _split_cells(row, separator)
        ]
        lines.append("| " + " | ".join(cells) + " |")
        if index == 0:
            lines.append("| " + " | ".join("---" for _ in cells) + " |")
    return "\n".join(lines)


_WIKI_ESCAPED = re.compile(r"\\(.)")
_WIKI_CODE = re.compile(r"\{\{(.+?)\}\}")
_WIKI_LINK = re.compile(r"\[([^\[\]|]*)\|([^\[\]]+)\]")
_WIKI_BARE_LINK = re.compile(r"\[((?:https?://|mailto:)[^\[\]|]+)\]")
_WIKI_MENTION = re.compile(r"\[~([^\[\]]+)\]")
_WIKI_STRONG = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_WIKI_STRIKE = re.compile(r"(?<![\w-])-(?=\S)([^-\n]+?)(?<=\S)-(?![\w-])")


def _wiki_inline_md(text: str) -> str:
    """Wiki inline markup as Markdown. Escapes and code are protected first."""
    held: List[str] = []

    def hold(value: str) -> str:
        held.append(value)
        return f"\x00{len(held) - 1}\x00"

    out = text.replace("&#92;", hold("\\"))
    # A forced line break (`\\`) before single-character escapes.
    out = out.replace(" \\\\ ", "\n").replace("\\\\", "\n")
    out = _WIKI_ESCAPED.sub(lambda m: hold(m.group(1)), out)
    out = _WIKI_CODE.sub(lambda m: hold(f"`{m.group(1)}`"), out)
    out = _WIKI_MENTION.sub(lambda m: hold(f"@{m.group(1)}"), out)
    out = _WIKI_LINK.sub(
        lambda m: hold(f"[{_restore(m.group(1), held)}]({m.group(2)})"), out
    )
    out = _WIKI_BARE_LINK.sub(lambda m: hold(f"<{m.group(1)}>"), out)
    out = _WIKI_STRONG.sub(lambda m: f"**{m.group(1)}**", out)
    out = _WIKI_STRIKE.sub(lambda m: f"~~{m.group(1)}~~", out)
    return _restore(out, held)


def _restore(text: str, held: Sequence[str]) -> str:
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], text)
    return text
