"""Every prompt the CLI sends to an agent, as Markdown files (issue-540).

A prompt — or a fragment of one — lives in ``the_loop/prompts/<area>/<name>.md`` and
is read through this module. The Python call sites keep their *logic* (which fragment,
in which order, under which condition); the *prose* is here, where it reads and
reviews as a document instead of a string literal.

Two substitution styles are in use, each kept from the call site it replaced:

* the webhook templates are :class:`string.Template` text (``$work_item``) — the
  syntax an operator's own ``routing.promptTemplate`` uses — and the dispatcher
  substitutes them itself;
* everything else is ``str.format`` text (``{name}``), filled by :func:`render`.

Both are single-pass: a ``$x`` or ``{x}`` inside a substituted value is inserted
literally and never read as a further placeholder. That is what keeps untrusted
payload text from steering a prompt.

Spec: docs/specs/issue-540/design.md.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib import resources
from typing import List

__all__ = ["load", "names", "render"]

#: Slash-separated lowercase segments — never ``..``, never absolute, never empty.
_NAME = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$")


def _check(name: str) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError(f"not a prompt name: {name!r}")
    return name


@lru_cache(maxsize=None)
def _read(name: str) -> str:
    path = resources.files(__name__).joinpath(*f"{name}.md".split("/"))
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise FileNotFoundError(
            f"the-loop prompt is missing: prompts/{name}.md"
        ) from None


def load(name: str, *, inline: bool = False) -> str:
    """The text of ``prompts/<name>.md``, verbatim.

    ``inline=True`` drops the file's one trailing newline, for a fragment that is
    joined into a line or used where the literal it replaced had none.
    """
    text = _read(_check(name))
    if inline and text.endswith("\n"):
        return text[:-1]
    return text


def render(name: str, /, *, inline: bool = False, **slots: object) -> str:
    """``load(name)`` with its ``{slot}`` fields filled by ``str.format``."""
    return load(name, inline=inline).format(**slots)


def names() -> List[str]:
    """Every prompt this package ships, as names :func:`load` accepts."""
    root = resources.files(__name__)
    found: List[str] = []

    def walk(node, prefix: str) -> None:
        for child in node.iterdir():
            if child.is_dir():
                walk(child, f"{prefix}{child.name}/")
            elif child.name.endswith(".md"):
                found.append(f"{prefix}{child.name[:-3]}")

    walk(root, "")
    return sorted(found)
