"""The chain runner and the process-wide seam (issue-344, R2.3, R3.6, R5.3, R6)."""

from __future__ import annotations

import json

import pytest

from the_loop import cli_config, eventlog, lifecycle
from the_loop.lifecycle.contract import (
    PhaseChanged,
    SessionSpawn,
    WorkItem,
    WorkItemStart,
    LifecycleHooks,
)
from the_loop.lifecycle.executors import Executor, LocalExecutor
from the_loop.lifecycle.runner import Runner


@pytest.fixture(autouse=True)
def _fresh_seam():
    lifecycle.reset()
    yield
    lifecycle.reset()


@pytest.fixture
def events(tmp_path):
    path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=path)
    yield lambda: list(eventlog.read_events(path))
    eventlog.reset()


class _Stub(Executor):
    """An executor whose answer the test scripts."""

    def __init__(self, name, answer=None, points=("work_item_start",), required=False):
        super().__init__(name=name, on=tuple(points), required=required)
        self.answer = answer
        self.seen = []

    def handles(self, point):
        return point in self.on

    def call(self, point, ctx):  # type: ignore[override] — a scripted double
        self.seen.append((point, ctx.to_params()))
        if isinstance(self.answer, BaseException):
            raise self.answer
        if callable(self.answer):
            return self.answer(ctx)
        return self.answer


def _start(**kw):
    return WorkItemStart(
        work_item=WorkItem.from_ref("github:o/r#1"), loop="pdlc-work-item-loop", **kw
    )


def test_executors_run_in_order_and_see_earlier_decisions():
    first = _Stub("first", answer=lambda ctx: {"reason": "first said"})
    second = _Stub("second", answer=lambda ctx: {"reason": ctx.reason + " and second"})
    out = Runner([first, second]).run(_start())
    assert out.reason == "first said and second"
    assert first.seen[0][1]["reason"] == ""
    assert second.seen[0][1]["reason"] == "first said"


def test_none_passes_through_a_returned_context_replaces_a_mapping_applies():
    ctx = _start()
    passthrough = _Stub("a", answer=None)
    returned = _Stub(
        "b",
        answer=lambda c: WorkItemStart(
            work_item=WorkItem.from_ref("github:x/y#9"), proceed=False
        ),
    )
    mapping = _Stub("c", answer={"reason": "mapped"})
    out = Runner([passthrough, returned, mapping]).run(ctx)
    assert out is ctx
    assert out.proceed is False
    assert out.reason == "mapped"
    assert out.work_item.ref == "github:o/r#1", (
        "a returned context changes decisions only"
    )


def test_an_executor_that_does_not_handle_the_point_is_skipped():
    other = _Stub("other", answer={"proceed": False}, points=("phase_changed",))
    out = Runner([other]).run(_start())
    assert out.proceed is True
    assert other.seen == []


def test_a_changed_decision_is_recorded(events):
    Runner([_Stub("pol", answer={"proceed": False, "reason": "no"})]).run(_start())
    decided = [e for e in events() if e["event"] == "hooks.decided"]
    assert len(decided) == 1
    assert decided[0]["hook"] == "pol"
    assert decided[0]["point"] == "work_item_start"
    assert decided[0]["changed"] == ["proceed", "reason"]
    assert decided[0]["work_item"] == "github:o/r#1"


def test_an_unchanged_decision_is_not_recorded(events):
    Runner([_Stub("pol", answer={"proceed": True})]).run(_start())
    assert [e for e in events() if e["event"] == "hooks.decided"] == []


def test_a_raising_hook_never_reaches_the_caller(events):
    """Abuse case 7 / R6.1, R6.2: recorded, skipped, the chain finishes."""
    boom = _Stub("boom", answer=RuntimeError("kaboom"))
    after = _Stub("after", answer={"reason": "still ran"})
    out = Runner([boom, after]).run(_start())
    assert out.proceed is True
    assert out.reason == "still ran"
    failed = [e for e in events() if e["event"] == "hooks.failed"]
    assert len(failed) == 1
    assert failed[0]["hook"] == "boom"
    assert "kaboom" in failed[0]["error"]
    assert failed[0]["level"] == "warning"
    assert failed[0]["required"] is False


def test_a_wrong_typed_decision_is_that_hooks_failure(events):
    """Abuse case 2: nothing of a malformed answer is applied."""
    bad = _Stub("bad", answer={"proceed": False, "reason": 7})
    out = Runner([bad]).run(_start())
    assert out.proceed is True and out.reason == ""
    (failed,) = [e for e in events() if e["event"] == "hooks.failed"]
    assert "reason" in failed["error"]


def test_a_non_context_non_mapping_answer_is_a_failure(events):
    out = Runner([_Stub("odd", answer=lambda c: 42)]).run(_start())
    assert out.proceed is True
    (failed,) = [e for e in events() if e["event"] == "hooks.failed"]
    assert "int" in failed["error"]


def test_a_required_hook_that_fails_refuses_a_proceed_point(events):
    """R6.3 / abuse case 3."""
    out = Runner([_Stub("gate", answer=RuntimeError("down"), required=True)]).run(
        _start()
    )
    assert out.proceed is False
    assert "gate" in out.reason and "down" in out.reason
    decided = [e for e in events() if e["event"] == "hooks.decided"]
    assert decided and decided[0]["changed"] == ["proceed", "reason"]
    (failed,) = [e for e in events() if e["event"] == "hooks.failed"]
    assert failed["required"] is True


def test_a_required_hook_that_fails_at_a_point_without_proceed_only_records(events):
    ctx = PhaseChanged(work_item=WorkItem.from_ref("github:o/r#1"), to_phase="design")
    out = Runner(
        [
            _Stub(
                "gate",
                answer=RuntimeError("down"),
                points=("phase_changed",),
                required=True,
            )
        ]
    ).run(ctx)
    assert out.notify is True
    assert [e["event"] for e in events()] == ["hooks.failed"]


def test_a_later_hook_may_undo_an_earlier_refusal_and_it_is_recorded(events):
    refuse = _Stub("a", answer={"proceed": False, "reason": "no"})
    allow = _Stub("b", answer={"proceed": True})
    out = Runner([refuse, allow]).run(_start())
    assert out.proceed is True
    assert [e["hook"] for e in events() if e["event"] == "hooks.decided"] == ["a", "b"]


def test_a_local_executor_calls_the_subclass_method():
    class Reword(LifecycleHooks):
        def session_spawn(self, ctx):
            ctx.prompt = "PREFIX\n" + ctx.prompt
            return ctx

    ex = LocalExecutor("reword", Reword(), on=())
    ctx = SessionSpawn(work_item=WorkItem.from_ref("github:o/r#1"), prompt="hello")
    out = Runner([ex]).run(ctx)
    assert out.prompt == "PREFIX\nhello"


def test_the_runner_never_raises_even_when_the_context_is_odd(events):
    class Weird(Executor):
        def handles(self, point):
            raise RuntimeError("handles exploded")

        def call(self, point, ctx):
            return None

    ctx = _start()
    assert Runner([Weird(name="w", on=(), required=False)]).run(ctx) is ctx


def test_describe_lists_each_executor():
    rows = Runner([_Stub("a"), _Stub("b", points=("phase_changed",))]).describe()
    assert [r["name"] for r in rows] == ["a", "b"]
    assert rows[1]["on"] == ["phase_changed"]


# ------------------------------------------------------------- process seam


def _config_file(tmp_path, hooks_block, module_body=None):
    root = tmp_path / "operator"
    root.mkdir(exist_ok=True)
    if module_body is not None:
        (root / "policy.py").write_text(module_body)
    path = root / "cli-config.yaml"
    path.write_text(json.dumps({"hooks": hooks_block}))
    return path


POLICY = """
from the_loop.sdk.hooks import LifecycleHooks


class Policy(LifecycleHooks):
    def work_item_start(self, ctx):
        ctx.reason = "policy saw it"
        return ctx
"""


def test_run_is_a_pass_through_when_nothing_is_declared(tmp_path, monkeypatch):
    path = _config_file(tmp_path, [])
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    cli_config.set_override(None)
    ctx = _start()
    assert lifecycle.run(ctx) is ctx
    assert ctx.reason == ""


def test_run_configures_lazily_from_the_resolved_config(tmp_path, monkeypatch, events):
    path = _config_file(tmp_path, [{"name": "pol", "path": "policy.py"}], POLICY)
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    cli_config.set_override(None)
    out = lifecycle.run(_start())
    assert out.reason == "policy saw it"
    loaded = [e for e in events() if e["event"] == "hooks.loaded"]
    assert loaded and loaded[0]["hooks"] == ["pol"]


def test_a_lazy_load_failure_installs_no_hooks_and_records_it(
    tmp_path, monkeypatch, events
):
    """Abuse case 6 / R3.6: a one-shot command proceeds hookless, loudly."""
    path = _config_file(tmp_path, [{"name": "pol", "path": "missing.py"}])
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    cli_config.set_override(None)
    out = lifecycle.run(_start())
    assert out.proceed is True
    failed = [e for e in events() if e["event"] == "hooks.load_failed"]
    assert len(failed) == 1 and "missing.py" in failed[0]["error"]
    # …and does not retry the load on the next point.
    lifecycle.run(_start())
    assert len([e for e in events() if e["event"] == "hooks.load_failed"]) == 1


def test_configure_from_file_strict_raises_for_a_daemon(tmp_path, monkeypatch):
    path = _config_file(tmp_path, [{"name": "pol", "path": "missing.py"}])
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    cli_config.set_override(None)
    with pytest.raises(lifecycle.HooksConfigError) as exc:
        lifecycle.configure_from_file()
    assert "pol" in str(exc.value)


def test_configure_from_file_with_no_config_file_installs_an_empty_runner(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(tmp_path / "absent.yaml"))
    cli_config.set_override(None)
    runner = lifecycle.configure_from_file()
    assert runner.describe() == []


def test_configure_from_config_resolves_paths_against_the_config_file(tmp_path):
    path = _config_file(tmp_path, [{"name": "pol", "path": "policy.py"}], POLICY)
    runner = lifecycle.configure_from_config(json.loads(path.read_text()), path)
    assert [r["name"] for r in runner.describe()] == ["pol"]
    assert lifecycle.run(_start()).reason == "policy saw it"


def test_reset_forgets_the_installed_runner(tmp_path):
    path = _config_file(tmp_path, [{"name": "pol", "path": "policy.py"}], POLICY)
    lifecycle.configure_from_config(json.loads(path.read_text()), path)
    lifecycle.reset()
    assert lifecycle.current() is None


def test_every_hooks_event_type_is_catalogued():
    for name in (
        "hooks.loaded",
        "hooks.load_failed",
        "hooks.decided",
        "hooks.failed",
        "hooks.refused",
    ):
        assert name in eventlog.EVENT_TYPES
