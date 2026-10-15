"""The quiz comment's vocabulary — markers and the attestation line (issue-488).

Kept apart from the graph hooks that post and judge the comment
(``graph/hooks/quiz.py``) because the router and the poller need the same two
questions — *is this a quiz comment?* and *is its box ticked?* — and must not
import the hook registry to ask them.
"""

from __future__ import annotations

import re
from typing import Dict, Mapping, Optional

__all__ = [
    "ATTESTATIONS",
    "READ_ONLY",
    "QUIZ_MARKER_PREFIX",
    "UNVERIFIED",
    "attestation_ticked",
    "is_quiz_comment",
    "quiz_marker",
]

#: Every quiz comment carries this — the poller's cheap first test.
QUIZ_MARKER_PREFIX = "<!-- the-loop:quiz "

_MARKER = re.compile(
    r"<!-- the-loop:quiz (?P<node>[a-z0-9-]+) round=(?P<round>\d+) "
    r"digest=(?P<digest>[0-9a-f]{12}|-) -->"
)

#: What a quiz gate says when it could not ask GitHub who ticked — a transient
#: failure, so the dispatcher releases the doorbell for the next poll to retry.
UNVERIFIED = "could not verify who ticked the quiz box"

#: The one line each quiz asks the author to tick, verbatim.
ATTESTATIONS: Dict[str, str] = {
    "spec-quiz": "I have read the spec explainer and taken the spec quiz.",
    "code-quiz": "I have read the explainer and taken the code quiz.",
}

#: The line at ``micro`` depth, where the page carries no quiz (R2.7): the box
#: then attests reading only.
READ_ONLY: Dict[str, str] = {
    "spec-quiz": "I have read the spec explainer.",
    "code-quiz": "I have read the explainer.",
}

_BOX = re.compile(
    r"^[ \t]*[-*][ \t]+\[(?P<mark>[ xX])\][ \t]+(?P<text>.+?)[ \t]*$", re.M
)


def is_quiz_comment(body: str) -> bool:
    """Does this body carry a quiz marker?"""
    return QUIZ_MARKER_PREFIX in str(body or "")


def quiz_marker(body: str) -> Optional[Mapping[str, str]]:
    """``{node, round, digest}`` from a quiz comment's marker, or ``None``."""
    found = _MARKER.search(str(body or ""))
    return found.groupdict() if found else None


def attestation_ticked(body: str, node: str = "") -> bool:
    """Is a node's attestation line present AND ticked in ``body``?

    Without ``node`` any quiz's line counts — the poller and the router do not
    know which gate is waiting, only that a quiz box changed.
    """
    nodes = [node] if node in ATTESTATIONS else list(ATTESTATIONS)
    lines = [table[n] for n in nodes for table in (ATTESTATIONS, READ_ONLY)]
    for match in _BOX.finditer(str(body or "")):
        if match.group("mark") in "xX" and match.group("text").strip() in lines:
            return True
    return False
