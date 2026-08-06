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


def test_a_passing_hooks_explicit_outcome_is_what_edges_route_on(ctx):
    """issue-113 — a human gate's whole job is to emit `approved` /
    `changes-requested`, and it does so on a **passing** result. Reading the
    routing value only from a *blocking* result discards it, so every approval
    node in pdlc.yaml parks with `no_edge` on an approval."""

    @registry.hook("t-classify")
    def _classify(c):
        return HookResult(status=PASS, hook="t-classify", data={"outcome": "approved"})

    @registry.hook("t-record")
    def _record(c):
        return HookResult.ok("t-record")

    outcome = run_chain(["t-classify", "t-record"], ctx)

    assert outcome.status == PASS
    assert outcome.outcome == "approved", "the gate's verdict must reach the edges"


def test_a_chain_of_plain_passes_still_routes_on_pass(ctx):
    """The common case is unchanged: no hook declaring an outcome means `pass`."""

    @registry.hook("t-plain-a")
    def _a(c):
        return HookResult.ok("t-plain-a")

    @registry.hook("t-plain-b")
    def _b(c):
        return HookResult.ok("t-plain-b")

    assert run_chain(["t-plain-a", "t-plain-b"], ctx).outcome == PASS


class TestASkipIsNotADecision:
    """A hook that declines to run has said nothing about the node (issue-163).

    Short-circuiting on `skip` produced two failures with one cause. Hooks
    *after* a skipping one never ran — `design`'s chain is
    `validate-artifacts, enforces-boundaries-from, lint-artifacts`, and the
    middle one skips whenever the upstream artifact is absent, taking the lint
    gate down with it. And a chain *ending* in a skip routed on the outcome
    `"skip"`, for which no edge is declared, so `implementation` — whose chain
    ends in a `verify-tests` that is a no-op unless a command is bound — parked
    at `no_edge` and escalated instead of advancing to the next node.
    """

    def test_the_chain_runs_on_past_a_skipping_hook(self, ctx):
        calls = []

        @registry.hook("t-skips")
        def _skip(c):
            calls.append("skip")
            return HookResult.skipped("t-skips", "nothing to do")

        @registry.hook("t-gate")
        def _gate(c):
            calls.append("gate")
            return HookResult.blocked("t-gate", [Message("the real finding")])

        outcome = run_chain(["t-skips", "t-gate"], ctx)
        assert calls == ["skip", "gate"], "a skip must not hide the gates behind it"
        assert outcome.status == BLOCK
        assert "the real finding" in outcome.render()

    def test_a_chain_ending_in_a_skip_still_routes_on_pass(self, ctx):
        """The `implementation → verification` edge depends on this."""

        @registry.hook("t-ok")
        def _ok(c):
            return HookResult.ok("t-ok")

        @registry.hook("t-noop")
        def _noop(c):
            return HookResult.skipped("t-noop", "no command declared")

        outcome = run_chain(["t-ok", "t-noop"], ctx)
        assert outcome.status == PASS
        assert outcome.outcome == PASS
        assert outcome.blocking is None

    def test_a_skip_does_not_override_an_earlier_declared_outcome(self, ctx):
        """A human gate's verdict must survive a later no-op hook."""

        @registry.hook("t-verdict")
        def _verdict(c):
            return HookResult(
                status=PASS, hook="t-verdict", data={"outcome": "approved"}
            )

        @registry.hook("t-nothing")
        def _nothing(c):
            return HookResult.skipped("t-nothing")

        assert run_chain(["t-verdict", "t-nothing"], ctx).outcome == "approved"
