"""Minimal YAML front-matter reader for markdown artifacts.

Uses PyYAML (already a required dependency, decision-038) but tolerates every
way a hand-edited artifact can be malformed: a missing block, an unterminated
one, a non-mapping body. Any of those yields ``{}`` rather than raising, because
a gate must report **unmet**, never crash the chain.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml

__all__ = ["mermaid_blocks", "read_front_matter", "sections", "split_front_matter"]


def split_front_matter(text: str) -> Tuple[Dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.split("\n")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            block = "\n".join(lines[1:i])
            try:
                data = yaml.safe_load(block) or {}
            except yaml.YAMLError:
                return {}, text
            return (data if isinstance(data, dict) else {}), "\n".join(lines[i + 1 :])
    return {}, text  # unterminated block


def read_front_matter(path: Path) -> Dict[str, Any]:
    try:
        return split_front_matter(path.read_text(encoding="utf-8"))[0]
    except (OSError, UnicodeDecodeError):
        return {}


def sections(text: str) -> Dict[str, str]:
    """Map every markdown heading to its content, ignoring headings inside fences.

    Two details that matter, both learned from running this against real specs:

    * **Fence-awareness.** This work item's own design doc contains an *example*
      ``## Review comments`` block inside a fenced snippet. Counting that as a
      real section would let the gate pass on a document that has none.
    * **A section owns its subsections.** ``## Requirements`` followed straight
      by ``### Requirement 1`` has no prose of its own, but it is obviously not
      empty. Content therefore runs to the next heading *of the same or higher
      level*, not merely to the next heading — otherwise the gate cries wolf on
      every well-structured document, which trains people to ignore gates.
    """
    out: Dict[str, str] = {}
    heads: List[Tuple[str, int, int]] = []  # (title, level, start line)
    lines = text.split("\n")
    fenced = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            heads.append((line.lstrip("#").strip(), level, i))
    for idx, (title, level, start) in enumerate(heads):
        end = len(lines)
        for title2, level2, start2 in heads[idx + 1 :]:
            if level2 <= level:
                end = start2
                break
        out[title] = "\n".join(lines[start + 1 : end]).strip()
    return out


def mermaid_blocks(text: str) -> List[str]:
    """Every ```mermaid fenced block's body, in document order."""
    blocks: List[str] = []
    buf: List[str] | None = None
    for line in text.split("\n"):
        stripped = line.strip()
        if buf is None and stripped.startswith("```mermaid"):
            buf = []
            continue
        if buf is not None:
            if stripped.startswith("```"):
                blocks.append("\n".join(buf))
                buf = None
            else:
                buf.append(line)
    return blocks
