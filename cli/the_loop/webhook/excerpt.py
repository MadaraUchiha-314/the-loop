"""The event excerpt: what a session is told about the event it just received.

Moved here from :mod:`the_loop.webhook.dispatcher` (issue-243) — a pure
``(event, payload) -> str`` of the same family as :mod:`the_loop.webhook.router`'s
extractors, so it is unit-testable per event type without a dispatcher.

This is the pre-change behaviour, kept verbatim for one commit so the tests that
motivate the change fail against the code they are about to replace rather than
against an ``ImportError``.
"""

from __future__ import annotations

import json

TEXT_MAX_CHARS = 3_500
EXCERPT_MAX_CHARS = 4_000

_PAYLOAD_EXCERPT_KEYS = (
    "action",
    "sender",
    "comment",
    "review",
    "issue",
    "pull_request",
    "workflow_run",
    "check_run",
    "check_suite",
)


def event_excerpt(event: str, payload: dict) -> str:
    """The routable subset of the payload, JSON-formatted and size-capped."""
    subset = {k: payload[k] for k in _PAYLOAD_EXCERPT_KEYS if k in payload}
    text = json.dumps(subset, indent=2, default=str)
    if len(text) > EXCERPT_MAX_CHARS:
        text = text[:EXCERPT_MAX_CHARS] + "\n… (truncated)"
    return text


def payload_excerpt(payload: dict) -> str:
    """Distil without an event name — the shape callers outside the-loop import."""
    return event_excerpt("", payload)
