"""Change a value in a YAML file without disturbing the rest of it (issue-222).

the-loop's CLI config is ~270 lines of which about half are **comments** — the prose that
explains why a knob exists and what its fail-closed default protects. Round-tripping that
file through ``yaml.safe_load`` → ``yaml.safe_dump`` to change one boolean deletes every
one of them, silently and irreversibly. So the Control Plane's config editor does not
round-trip: it **splices**, editing the original text in place.

The mechanism is PyYAML's own composer. ``yaml.compose`` returns a node tree in which
every node carries ``start_mark``/``end_mark`` with absolute character offsets into the
source, which is enough to locate one value's bytes and rewrite exactly those. Comments,
blank lines, key order, quoting and indentation are never parsed, never re-emitted, and
therefore never lost.

Two edges need care, and one property makes the whole thing safe to rely on:

* **A container's ``end_mark`` overshoots.** For a block sequence or mapping it lands
  after any trailing comments that follow the block, so replacing ``node.start_mark ..
  node.end_mark`` eats an operator's comment. Every container is therefore spliced from
  its **first child's start** to its **last leaf's end** (:func:`_content_span`).
* **A key that is not in the file yet** has no marks at all, so it is *inserted*: a new
  line under the deepest parent block that does exist, at that block's own indentation,
  with any missing intermediate blocks created in one dump.

The property: :func:`apply` **re-parses the text it produced and compares it to the
document it was asked to produce**. A splice that cannot prove it landed the intended data
raises :class:`SpliceError` and the caller writes nothing. That is what makes a
hand-written text editor an acceptable thing to point at somebody's config file — every
edge case not thought of here fails closed instead of corrupting the file.

Patch semantics
---------------

A patch is a **sparse** nested mapping: mappings merge, everything else (scalars,
sequences) replaces, and a leaf of ``None`` **removes** the key so the built-in default
applies again. ``None`` is free to mean that because no key in the-loop's config schemas
is typed to accept ``null`` — a key whose value is nothing is a key that is not there.
"""

from __future__ import annotations

from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple

import yaml

__all__ = [
    "SpliceError",
    "apply",
    "changed_paths",
    "deep_merge",
]

KeyPath = Tuple[str, ...]


class SpliceError(RuntimeError):
    """The edited text did not re-parse to the intended document — nothing is written."""


def deep_merge(base: Mapping[str, Any], patch: Mapping[str, Any]) -> Dict[str, Any]:
    """``base`` with ``patch`` applied: mappings merge, other values replace, ``None``
    removes. Neither argument is mutated."""
    out: Dict[str, Any] = {k: v for k, v in base.items()}
    for key, value in patch.items():
        if value is None:
            out.pop(key, None)
        elif isinstance(value, Mapping) and isinstance(out.get(key), Mapping):
            out[key] = deep_merge(out[key], value)
        elif isinstance(value, Mapping):
            out[key] = deep_merge({}, value)
        else:
            out[key] = value
    return out


def changed_paths(current: Mapping[str, Any], patch: Mapping[str, Any]) -> List[str]:
    """The dotted key paths ``patch`` would actually change in ``current``.

    A patch that re-sends a value the file already carries changes nothing and reports
    nothing — which is what makes "an empty patch writes nothing" the same code path as
    "a save that changed nothing writes nothing", rather than a special case.
    """
    return [
        ".".join(path)
        for path, value in _leaves(patch)
        if _differs(current, path, value)
    ]


def apply(text: str, patch: Mapping[str, Any], header: str = "") -> str:
    """``text`` with ``patch`` applied, everything else byte-identical.

    ``header`` is used only when ``text`` is empty (a config file that does not exist yet):
    it is written above the dumped document, and is where the caller puts the
    ``# yaml-language-server: $schema=…`` modeline.

    Raises :class:`ValueError` when the document is not a mapping, and
    :class:`SpliceError` when the result does not re-parse to the intended document.
    """
    current = _parse(text)
    merged = deep_merge(current, patch)
    if not text.strip():
        body = _dump(merged) if merged else "{}\n"
        result = f"{header}{body}" if header else body
    else:
        result = text
        for path, value in _leaves(patch):
            if not _differs(current, path, value):
                continue
            result = _splice(result, path, value)
    if _parse(result) != merged:
        raise SpliceError(
            "the edited config did not re-parse to the intended document "
            f"(first difference at {_first_difference(_parse(result), merged) or '(root)'}); "
            "nothing was written"
        )
    return result


# -- reading the patch -------------------------------------------------------------


def _leaves(
    patch: Mapping[str, Any], prefix: KeyPath = ()
) -> Iterator[Tuple[KeyPath, Any]]:
    """Every ``(path, value)`` the patch sets. A non-empty mapping recurses; an empty one
    is a value in its own right (``{}`` means "this block, empty")."""
    for key, value in patch.items():
        path = prefix + (str(key),)
        if isinstance(value, Mapping) and value:
            yield from _leaves(value, path)
        else:
            yield path, value


def _differs(current: Mapping[str, Any], path: KeyPath, value: Any) -> bool:
    node: Any = current
    for token in path[:-1]:
        if not isinstance(node, Mapping) or token not in node:
            return value is not None  # a delete of something absent changes nothing
        node = node[token]
    if not isinstance(node, Mapping) or path[-1] not in node:
        return value is not None
    return node[path[-1]] != value


def _parse(text: str) -> Dict[str, Any]:
    data = yaml.safe_load(text) if text.strip() else {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("a the-loop config must be a mapping at the top level")
    return data


def _first_difference(got: Any, want: Any, prefix: str = "") -> Optional[str]:
    if isinstance(got, Mapping) and isinstance(want, Mapping):
        for key in sorted(set(got) | set(want), key=str):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in got or key not in want:
                return child
            found = _first_difference(got[key], want[key], child)
            if found:
                return found
        return None
    return None if got == want else (prefix or "(root)")


# -- splicing ----------------------------------------------------------------------


def _splice(text: str, path: KeyPath, value: Any) -> str:
    root = yaml.compose(text)
    if root is None or not isinstance(root, yaml.MappingNode):
        raise SpliceError("the config is not a mapping; refusing to edit it as one")
    key_node, value_node, parent, depth = _locate(root, path)
    if depth == len(path) and value_node is not None and key_node is not None:
        if value is None:
            return _remove(text, key_node, value_node, parent, is_root=parent is root)
        return _replace(text, key_node, value_node, value)
    if value is None:
        return text  # nothing to remove
    return _insert(text, parent, path[depth:], value, key_node)


def _locate(
    root: yaml.MappingNode, path: KeyPath
) -> Tuple[Optional[yaml.Node], Optional[yaml.Node], yaml.MappingNode, int]:
    """Walk ``path`` as far as the document goes.

    Returns the key node and value node of the deepest **matched** step, the mapping that
    contains it (the insertion point for what is missing), and how many steps matched.
    """
    parent: yaml.MappingNode = root
    key_node: Optional[yaml.Node] = None
    value_node: Optional[yaml.Node] = None
    for depth, token in enumerate(path):
        found = _child(parent, token)
        if found is None:
            return key_node, value_node, parent, depth
        key_node, value_node = found
        if depth + 1 == len(path):
            return key_node, value_node, parent, len(path)
        if not isinstance(value_node, yaml.MappingNode):
            # e.g. patching `a.b` where `a` is a scalar. The schema check upstream refuses
            # this shape, so reaching here means the two disagree — fail, never guess.
            raise SpliceError(
                f"{'.'.join(path[: depth + 1])} is not a block in the config; "
                "refusing to write a key beneath it"
            )
        parent = value_node
    return key_node, value_node, parent, len(path)


def _child(
    mapping: yaml.MappingNode, name: str
) -> Optional[Tuple[yaml.Node, yaml.Node]]:
    for key_node, value_node in mapping.value:
        if getattr(key_node, "value", None) == name:
            return key_node, value_node
    return None


def _is_block_container(node: yaml.Node) -> bool:
    """A sequence or mapping the operator wrote across lines, rather than in ``[]``/``{}``."""
    return bool(_children(node)) and not getattr(node, "flow_style", False)


def _span(node: yaml.Node) -> Tuple[int, int]:
    """The offsets to rewrite when this node's value is replaced.

    A **block** container's ``end_mark`` overshoots — it sits after any comments that
    trail the block (measured: it swallows a `# comment` line following a block
    sequence) — so it is measured to its last leaf instead. A flow container is
    delimited by its brackets and a scalar by itself, so both use their own marks.
    """
    if not _is_block_container(node):
        return node.start_mark.index, node.end_mark.index
    return _content_span(node)


def _content_span(node: yaml.Node) -> Tuple[int, int]:
    """From a container's own start to the end of its **last leaf**."""
    children = _children(node)
    if not children:
        return node.start_mark.index, node.end_mark.index
    start = min(node.start_mark.index, children[0].start_mark.index)
    return start, _span(children[-1])[1]


def _children(node: yaml.Node) -> List[yaml.Node]:
    if isinstance(node, yaml.SequenceNode):
        return list(node.value)
    if isinstance(node, yaml.MappingNode):
        return [child for pair in node.value for child in pair]
    return []


def _replace(text: str, key_node: yaml.Node, value_node: yaml.Node, value: Any) -> str:
    """Rewrite one value, keeping the style the operator wrote it in.

    A block list stays a block list at its own indentation; a flow list stays on its line;
    a scalar slot that has to hold a structure gets an indented block beneath its key,
    which is the readable shape and is legal wherever ``key:`` is.
    """
    start, end = _span(value_node)
    if _is_inline(value):
        rendered = _dump_inline(value)
    elif _is_block_container(value_node):
        # The node's own column, not its first child's: a block sequence starts at its
        # `-`, which sits two columns left of the item it introduces.
        rendered = (
            _indent(_dump(value), value_node.start_mark.column).lstrip().rstrip("\n")
        )
    elif _children(value_node):
        rendered = _dump_inline(value)  # a flow container stays a flow container
    else:
        rendered = "\n" + _indent(_dump(value), key_node.start_mark.column + 2).rstrip(
            "\n"
        )
        start = _back_over_spaces(text, start)
    return text[:start] + rendered + text[end:]


def _back_over_spaces(text: str, start: int) -> int:
    """Move ``start`` left over the space after ``key:``, which a block written on the
    next line would otherwise leave behind as trailing whitespace."""
    while start > 0 and text[start - 1] == " ":
        start -= 1
    return start


def _remove(
    text: str,
    key_node: yaml.Node,
    value_node: yaml.Node,
    parent: yaml.MappingNode,
    is_root: bool,
) -> str:
    """Delete a key's whole line (or block). The comments *above* it are somebody's note
    about a setting that is now gone; they are left alone rather than guessed at."""
    if len(parent.value) == 1 and not is_root:
        # The last key of a nested block: leaving `parent:` bare would parse as null, not
        # as an empty block, so the block is written out explicitly.
        pstart, pend = _content_span(parent)
        return text[:pstart] + "{}" + text[pend:]
    start = text.rfind("\n", 0, key_node.start_mark.index) + 1
    end = text.find("\n", _span(value_node)[1])
    end = len(text) if end == -1 else end + 1
    return text[:start] + text[end:]


def _insert(
    text: str,
    parent: yaml.MappingNode,
    remainder: KeyPath,
    value: Any,
    key_node: Optional[yaml.Node],
) -> str:
    """Add ``remainder`` (a chain of one or more missing keys) under ``parent``."""
    nested: Any = value
    for token in reversed(remainder[1:]):
        nested = {token: nested}
    addition = {remainder[0]: nested}
    block = _dump(addition)

    if not parent.value:
        # An empty block (`{}`) or an empty document: give it a body.
        column = (key_node.start_mark.column + 2) if key_node is not None else 0
        start, end = _span(parent)
        start = _back_over_spaces(text, start)
        return text[:start] + "\n" + _indent(block, column).rstrip("\n") + text[end:]

    if getattr(parent, "flow_style", False):
        # `key: {a: 1}` — a block line appended under it would not belong to it. The
        # whole flow mapping is re-rendered inline, which is the style it is written in.
        start, end = _span(parent)
        existing = yaml.safe_load(text[start:end]) or {}
        return text[:start] + _dump_inline({**existing, **addition}) + text[end:]

    column = parent.value[0][0].start_mark.column
    at = _content_span(parent)[1]
    line_end = text.find("\n", at)
    line_end = len(text) if line_end == -1 else line_end
    return (
        text[:line_end] + "\n" + _indent(block, column).rstrip("\n") + text[line_end:]
    )


# -- rendering ---------------------------------------------------------------------


def _is_inline(value: Any) -> bool:
    """True for values that belong on the same line as their key: scalars, and the empty
    containers whose whole meaning is "nothing here"."""
    if isinstance(value, (Mapping, list, tuple)):
        return not value
    return True


def _dump(value: Any) -> str:
    """Block-style YAML for a value, as PyYAML would write it (quoting included)."""
    return yaml.safe_dump(
        value,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=10**6,
    )


def _dump_inline(value: Any) -> str:
    text = yaml.safe_dump(
        value, default_flow_style=True, sort_keys=False, allow_unicode=True, width=10**6
    ).strip()
    return text[:-4].strip() if text.endswith("\n...") else text


def _indent(block: str, column: int) -> str:
    pad = " " * column
    return "".join(
        f"{pad}{line}" if line.strip() else line for line in block.splitlines(True)
    )
