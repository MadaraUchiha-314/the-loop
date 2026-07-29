"""Chain semantics — short-circuit, aggregation, and never-pass-on-error (R3)."""

from __future__ import annotations

import pytest

from the_loop.graph import registry
from the_loop.graph.chain import run_chain
from the_loop.graph.contract import (
    BLOCK,
    PASS,
    WAIT,
    HookContext,
    HookResult,
    Message,
    WorkItem,
)


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(registry._REGISTRY)
    yield
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


@pytest.fixture()
def ctx(tmp_path):
    return HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=tmp_path),
        node={"id": "n"},
        boundary="exit",
        repo=tmp_path,
    )


def _passing(name):
    @registry.hook(name)
    def _fn(c):
        return HookResult.ok(name)

    return name


def test_all_passing_yields_pass(ctx):
    specs = [_passing("t-a"), _passing("t-b")]
    outcome = run_chain(specs, ctx)
    assert outcome.status == PASS
    assert outcome.satisfied
    assert len(outcome.results) == 2


def test_first_non_pass_short_circuits(ctx):
    calls = []

    @registry.hook("t-block")
    def _block(c):
        calls.append("block")
        return HookResult.blocked("t-block", [Message("nope")])

    @registry.hook("t-after")
    def _after(c):  # pragma: no cover - must not run
        calls.append("after")
        return HookResult.ok("t-after")

    outcome = run_chain(["t-block", "t-after"], ctx)
    assert outcome.status == BLOCK
    assert calls == ["block"], "the chain must stop at the first non-pass"
    assert outcome.blocking is not None
    assert outcome.blocking.hook == "t-block"


def test_a_raising_hook_blocks_and_is_not_retriable(ctx):
    """Negative test, abuse case 6: a broken check is never a pass."""

    @registry.hook("t-raises")
    def _raises(c):
        raise RuntimeError("boom")

    outcome = run_chain(["t-raises"], ctx)
    assert outcome.status == BLOCK
    assert outcome.blocking is not None
    assert outcome.blocking.retriable is False
    assert "boom" in outcome.render()


def test_wait_propagates(ctx):
    @registry.hook("t-wait")
    def _wait(c):
        return HookResult.waiting("t-wait", "a human has not replied")

    outcome = run_chain(["t-wait"], ctx)
    assert outcome.status == WAIT
    assert not outcome.satisfied


def test_params_reach_the_hook(ctx):
    seen = {}

    @registry.hook("t-params")
    def _params(c):
        seen.update(c.params)
        return HookResult.ok("t-params")

    run_chain([{"hook": "t-params", "with": {"locked": True}}], ctx)
    assert seen == {"locked": True}


def test_prior_results_are_visible_to_later_hooks(ctx):
    @registry.hook("t-first")
    def _first(c):
        return HookResult(status=PASS, hook="t-first", data={"outcome": "approved"})

    seen = {}

    @registry.hook("t-second")
    def _second(c):
        seen["prior"] = [r.hook for r in c.results]
        return HookResult.ok("t-second")

    run_chain(["t-first", "t-second"], ctx)
    assert seen["prior"] == ["t-first"]


def test_malformed_entry_is_rejected(ctx):
    with pytest.raises(ValueError, match="malformed hook entry"):
        run_chain([123], ctx)


def test_feedback_names_the_hook_and_its_findings(ctx):
    @registry.hook("t-two")
    def _two(c):
        return HookResult.blocked(
            "t-two", [Message("one"), Message("two", path="d.md")]
        )

    outcome = run_chain(["t-two"], ctx)
    rendered = outcome.render()
    assert "t-two" in rendered and "one" in rendered and "two (d.md)" in rendered
