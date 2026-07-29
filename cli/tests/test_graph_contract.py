"""Unit tests for the hook contract (issue-109, R2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from the_loop.graph.contract import (
    BLOCK,
    PASS,
    SKIP,
    WAIT,
    HookContext,
    HookResult,
    Message,
    WorkItem,
)


def _item(tmp_path: Path) -> WorkItem:
    return WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=tmp_path)


def test_result_rejects_an_unknown_status():
    with pytest.raises(ValueError, match="unknown status"):
        HookResult(status="maybe", hook="x")


def test_constructors_produce_the_expected_statuses():
    assert HookResult.ok("h").status == PASS
    assert HookResult.blocked("h", [Message("no")]).status == BLOCK
    assert HookResult.waiting("h", "later").status == WAIT
    assert HookResult.skipped("h").status == SKIP


def test_blocked_carries_every_message_in_one_result():
    """Aggregation is the hook's job — R3.5. One result, many messages."""
    result = HookResult.blocked("h", [Message("a"), Message("b"), Message("c")])
    assert len(result.messages) == 3
    assert "a" in result.render() and "c" in result.render()


def test_outcome_prefers_an_explicit_data_outcome():
    plain = HookResult.ok("h")
    assert plain.outcome == PASS
    classified = HookResult(status=PASS, hook="h", data={"outcome": "approved"})
    assert classified.outcome == "approved"


def test_message_renders_its_path_when_present():
    assert Message("bad", path="a/b.md").render() == "bad (a/b.md)"
    assert Message("bad").render() == "bad"


def test_context_carries_no_secret_values(tmp_path):
    """R2.7 — a hook receives handles (env var names), never credentials."""
    ctx = HookContext(
        work_item=_item(tmp_path),
        node={"id": "n"},
        boundary="exit",
        repo=tmp_path,
        config={"integrations": {"github": {"api": {"tokenEnv": ["GH_TOKEN"]}}}},
    )
    rendered = repr(ctx.config)
    assert "GH_TOKEN" in rendered  # the handle
    assert "ghp_" not in rendered  # never a value
