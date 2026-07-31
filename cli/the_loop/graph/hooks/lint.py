"""``lint-artifacts`` — markdown lints, and the diagrams actually render.

``diagramsRender`` exists because of a real incident, recorded in
docs/specs/issue-109/design.md: a reviewer caught a mermaid block in this very
work item that would not render, and checking the whole repository then found
three more **already merged**. ``userInteraction.diagramFormat: mermaid`` is
written as a RULE and was enforced by nothing.

A rule with no hook drifts. That is issue-109's thesis, demonstrated on a rule
nobody thought to check — so it is a hook now.
"""

from __future__ import annotations

import re
from typing import List

from ..contract import HookContext, HookResult, Message
from ..frontmatter import mermaid_blocks
from ..model import resolve_produces
from ..registry import hook

NAME = "lint-artifacts"

# A backtick inside a mermaid node label is the exact defect a reviewer hit on
# PR #110: GitHub's renderer reports "Lexical error … Unrecognized text".
_LABEL_WITH_BACKTICK = re.compile(r'\[\s*"[^"\n]*`')

# Structural sanity: a fenced block that declares no diagram type at all.
_KNOWN_TYPES = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "classDiagram",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "gitGraph",
    "quadrantChart",
    "C4Context",
    "block-beta",
)


def check_mermaid(text: str, rel: str) -> List[Message]:
    """Structural checks over every mermaid block in ``text``.

    Deliberately *not* a full mermaid parser — that would need a browser. These
    are the failure modes that actually reach a reviewer, and they are cheap
    enough to run on every turn.
    """
    findings: List[Message] = []
    for i, block in enumerate(mermaid_blocks(text), start=1):
        stripped = block.strip()
        if not stripped:
            findings.append(Message(text=f"mermaid block {i} is empty", path=rel))
            continue
        first = stripped.split("\n", 1)[0].strip()
        if not first.startswith(_KNOWN_TYPES):
            findings.append(
                Message(
                    text=(
                        f"mermaid block {i} does not start with a diagram type "
                        f"(found {first[:40]!r})"
                    ),
                    path=rel,
                )
            )
        for line_no, line in enumerate(stripped.split("\n"), start=1):
            if _LABEL_WITH_BACKTICK.search(line):
                findings.append(
                    Message(
                        text=(
                            f"mermaid block {i} line {line_no}: a backtick inside a "
                            "node label breaks rendering — use plain text"
                        ),
                        path=rel,
                    )
                )
    return findings


@hook(NAME)
def lint_artifacts(ctx: HookContext) -> HookResult:
    findings: List[Message] = []
    # Every artifact that is actually there, whichever accepted name it goes by.
    # This hook used to carry its own byte-identical copy of the resolver — the
    # same defect as issue-124 one level down, and a quieter one, since a file
    # this hook never resolves is a file it never lints.
    paths = [
        p
        for slot in resolve_produces(ctx.node.get("produces"), ctx.work_item.spec_dir)
        for p in slot.present
    ]
    if not paths:
        return HookResult.skipped(NAME, "no artifacts to lint")

    for path in paths:
        rel = (
            str(path.relative_to(ctx.repo))
            if path.is_relative_to(ctx.repo)
            else str(path)
        )
        text = path.read_text(encoding="utf-8")
        if ctx.params.get("diagrams", True):
            findings.extend(check_mermaid(text, rel))
        if ctx.params.get("maxLineLength"):
            limit = int(ctx.params["maxLineLength"])
            fenced = False
            for n, line in enumerate(text.split("\n"), start=1):
                if line.lstrip().startswith("```"):
                    fenced = not fenced
                if not fenced and len(line) > limit and " " in line.strip():
                    findings.append(
                        Message(text=f"line {n} exceeds {limit} characters", path=rel)
                    )

    if findings:
        return HookResult.blocked(NAME, findings)
    return HookResult.ok(NAME)
