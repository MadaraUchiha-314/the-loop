"""Unit tests for issue-389 task 9: the decision modal, the metadata guard and
the listener's routing. Spec: docs/specs/issue-389/testing-plan.md T6."""

from __future__ import annotations

import json

from the_loop.channels.slack import (
    DECISION_VIEW_CALLBACK,
    MENTION_SHORTCUTS,
    decision_view,
)
from the_loop.channels.verbs import KINDS


def test_the_decision_view_is_the_fixed_form():
    """R6.3 (T6, a snapshot): three inputs, the decision pre-filled, the kinds as
    the select's options, the metadata carried as given, the callback id the
    shortcut's."""
    metadata = json.dumps({"channel": "C1", "ts": "1.2", "thread_ts": "1.1"})
    view = decision_view("  we   ship\non Friday ", metadata)
    assert view["type"] == "modal" and view["callback_id"] == DECISION_VIEW_CALLBACK
    assert view["private_metadata"] == metadata
    blocks = {b["block_id"]: b for b in view["blocks"]}
    assert list(blocks) == ["decision", "kind", "rationale"]
    assert blocks["decision"]["element"]["initial_value"] == "we ship on Friday"
    assert [o["value"] for o in blocks["kind"]["element"]["options"]] == list(KINDS)
    assert blocks["kind"]["optional"] and blocks["rationale"]["optional"]
    assert not blocks["decision"].get("optional")
    assert DECISION_VIEW_CALLBACK in MENTION_SHORTCUTS


def test_the_decision_view_caps_the_prefilled_text():
    view = decision_view("x" * 5000, "{}")
    assert len(view["blocks"][0]["element"]["initial_value"]) == 3000
