"""``the-loop instructions`` — which of this repository's registered instruction docs
actually resolve (issue-132).

``customInstructions.docs`` tells the-loop which of the operator's own convention docs to
read before working an item. This command reports whether each one is really there, and
turns ``onMissing`` into an exit code — so ``onMissing: error`` errors, CI can gate on a
broken registration, and "which docs did you read?" has an answer that is not a promise.

Deliberately the same shape as ``the-loop scenarios``: pure filesystem reads, no network,
no subprocess, no mutation, three renderers. Both commands exist for the same reason —
to make an obligation the loop places on the agent *observable*.

The report carries facts about each doc (path, resolved path, state, size) and never its
contents; see :mod:`the_loop.instructions` for why that is the enforced boundary.

Spec: docs/specs/issue-132/  ·  Decision: 049
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List, Sequence

from .base import Command, register
from ..harness_config import load as load_harness_config
from ..instructions import InstructionDoc, collect_docs, on_missing, unresolved

logger = logging.getLogger("the-loop.instructions")

_HEADERS = ["#", "State", "Path", "Resolved", "Notes"]


def _rows(docs: Sequence[InstructionDoc]) -> List[List[str]]:
    rows: List[List[str]] = []
    for i, doc in enumerate(docs, start=1):
        # `detail` rides along with the state so the one-line reason an entry failed is
        # visible without a second command.
        state = f"{doc.state} ({doc.detail})" if doc.detail else doc.state
        rows.append(
            [str(i), state, doc.path or "—", doc.resolved or "—", doc.notes or "—"]
        )
    return rows


def render_json(docs: Sequence[InstructionDoc]) -> str:
    return json.dumps([doc.as_dict() for doc in docs], indent=2)


def render_table(docs: Sequence[InstructionDoc]) -> str:
    """A plain, aligned ASCII table (no third-party dependency)."""
    rows = _rows(docs)
    widths = [len(h) for h in _HEADERS]
    for row in rows:
        for c, cell in enumerate(row):
            widths[c] = max(widths[c], len(cell))

    def fmt(cells: Sequence[str]) -> str:
        return "  ".join(cell.ljust(widths[c]) for c, cell in enumerate(cells))

    lines = [fmt(_HEADERS), "  ".join("-" * w for w in widths)]
    lines.extend(fmt(row) for row in rows)
    return "\n".join(lines)


def render_markdown(docs: Sequence[InstructionDoc]) -> str:
    """A GitHub-flavoured Markdown table.

    Pipes are escaped: `notes` is operator-authored free text, and a crafted value must
    not be able to forge table structure in a PR comment.
    """

    def esc(text: str) -> str:
        return text.replace("|", "\\|")

    lines = [
        "| " + " | ".join(_HEADERS) + " |",
        "|" + "|".join("---" for _ in _HEADERS) + "|",
    ]
    for row in _rows(docs):
        lines.append("| " + " | ".join(esc(cell) for cell in row) + " |")
    return "\n".join(lines)


_RENDERERS = {
    "table": render_table,
    "markdown": render_markdown,
    "json": render_json,
}


@register
class InstructionsCommand(Command):
    name = "instructions"
    help = "Report the custom instruction docs this repo registers, and whether they resolve"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--root",
            default=".",
            help="Repository root to read the harness config from (default: current directory).",
        )
        parser.add_argument(
            "--format",
            choices=sorted(_RENDERERS),
            default="table",
            help="Output format (default: table).",
        )

    def run(self, args: argparse.Namespace) -> int:
        root = Path(args.root)
        config = load_harness_config(root)
        docs = collect_docs(root, config)
        print(_RENDERERS[args.format](docs))

        gaps = unresolved(docs)
        if not gaps:
            return 0

        policy = on_missing(config)
        if policy == "ignore":
            return 0

        # Composed from the-loop's own vocabulary plus configured paths — never from a
        # doc's contents.
        summary = ", ".join(f"{doc.path or '(no path)'} [{doc.state}]" for doc in gaps)
        if policy == "error":
            logger.error(
                "%d of %d registered instruction doc(s) did not resolve: %s "
                "(customInstructions.onMissing is 'error')",
                len(gaps),
                len(docs),
                summary,
            )
            return 1
        logger.warning(
            "%d of %d registered instruction doc(s) did not resolve: %s",
            len(gaps),
            len(docs),
            summary,
        )
        return 0
