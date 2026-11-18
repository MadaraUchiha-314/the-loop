"""The outer gate is re-evaluated when an inner loop finishes (issue-538, R2).

Walks the **shipped** outer graph in a throwaway checkout: a work item parked at
`implementation` because `await-inner-loops` answered `wait`, one pull request's
inner loop, and the daemon-side re-evaluation `GraphLink.on_inner_loop_finished`.
"""

from __future__ import annotations

import subprocess

import pytest

from the_loop import eventlog
from the_loop.control import ControlConfig
from the_loop.graph.state import STATE_FILENAME, WorkItemState
from the_loop.graphlink import GraphLink, GraphLinkConfig
from the_loop.sessions import WorkItemRef

WI = WorkItemRef.parse("github:octo/app#15")
PR = WorkItemRef.parse("github:octo/app#16")
OTHER_PR = WorkItemRef.parse("github:octo/app#17")

TASKS = """---
type: tasks
phase: tasks-breakdown
status: in-review
---

# Tasks: x

## Task list

- [x] 1. the one task
"""


@pytest.fixture()
def origin(tmp_path):
    """A checkout of the origin repository, its work item parked at implementation."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/app.git",
        ],
        check=True,
    )
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True)
    (spec / "tasks.md").write_text(TASKS, encoding="utf-8")
    state = WorkItemState.load(spec, "issue-15")
    state.current_node = "implementation"
    state.phase = "implementation"
    state.save(spec)
    return tmp_path


def _spec(origin):
    return origin / "docs" / "specs" / "issue-15"


def _link(assignments=None):
    def sink(work_item, pr_number, text):
        if assignments is not None:
            assignments.append((work_item.ref, pr_number, text))
        return True

    return GraphLink(
        GraphLinkConfig(enabled=True),
        control=ControlConfig(enabled=False),
        assignment_sink=sink,
    )


def _park(origin, node="implementation"):
    """What a session's claim leaves when `await-inner-loops` answers wait."""
    spec = _spec(origin)
    state = WorkItemState.load(spec, "issue-15")
    state.current_node = node
    state.park(node, "waiting for 1 inner loop(s) to finish: pr-16")
    state.save(spec)


def _current(origin):
    return WorkItemState.load(_spec(origin), "issue-15").current_node


@pytest.fixture()
def events(monkeypatch):
    seen = []
    monkeypatch.setattr(
        eventlog, "emit", lambda event, level="info", **f: seen.append((event, f))
    )
    return seen


def test_a_merge_releases_a_work_item_parked_on_its_inner_loops(origin, events):
    """
    Feature: pull-request session notices
      Scenario: the outer gate is re-evaluated when the last inner loop finishes
        Given a work item parked at implementation because await-inner-loops waited
        And one pull request walking its inner loop
        When that pull request merges and its inner loop is driven to complete
        Then the outer exit chain is re-run with no claim and no further event
        And the work item advances to verification
        And verification's assignment is delivered into the work item's session

    Requirement: docs/specs/issue-538/requirements.md R2.1, R2.4
    """
    assignments = []
    link = _link(assignments)
    link.on_pr_spawn(WI, PR, str(origin), session_id="s-1", runner="tmux")
    _park(origin)

    link.on_pr_close(WI, PR, str(origin), merged=True)
    report = link.on_inner_loop_finished(WI, str(origin))

    assert report is not None and report.status == "pass"
    assert _current(origin) == "verification"
    assert any(ref == WI.ref and prn is None for ref, prn, _ in assignments)
    (record,) = [f for e, f in events if e == "graph.outer_reevaluated"]
    assert record["node"] == "implementation" and record["status"] == "pass"


def test_a_second_pending_inner_loop_keeps_the_work_item_waiting(origin, events):
    """
    Feature: pull-request session notices
      Scenario: the re-evaluation waits again while another inner loop runs
        Given a work item parked at implementation with two inner loops
        When only one of them merges
        Then the re-evaluation waits, naming the other, and is not retried

    Requirement: docs/specs/issue-538/requirements.md R2.5
    """
    link = _link()
    link.on_pr_spawn(WI, PR, str(origin), session_id="s-1", runner="tmux")
    link.on_pr_spawn(WI, OTHER_PR, str(origin), session_id="s-2", runner="tmux")
    _park(origin)

    link.on_pr_close(WI, PR, str(origin), merged=True)
    report = link.on_inner_loop_finished(WI, str(origin))

    assert report is not None and report.status == "wait"
    assert _current(origin) == "implementation"
    assert [e for e, _ in events].count("graph.outer_reevaluated") == 1


def test_an_unparked_work_item_is_left_untouched(origin, events):
    """
    Feature: pull-request session notices
      Scenario: no previous evaluation waited, so nothing is re-run
        Given a work item at implementation that was never parked
        When its pull request merges
        Then the outer state file is byte-identical and nothing advanced

    Requirement: docs/specs/issue-538/requirements.md R2.3, R4.1
    """
    link = _link()
    link.on_pr_spawn(WI, PR, str(origin), session_id="s-1", runner="tmux")
    link.on_pr_close(WI, PR, str(origin), merged=True)
    before = (_spec(origin) / STATE_FILENAME).read_bytes()

    assert link.on_inner_loop_finished(WI, str(origin)) is None
    assert (_spec(origin) / STATE_FILENAME).read_bytes() == before
    (record,) = [f for e, f in events if e == "graph.outer_reevaluated"]
    assert record["outcome"] == "not-parked"


def test_a_node_without_the_inner_loop_gate_is_left_untouched(origin, events):
    """
    Feature: pull-request session notices
      Scenario: parked on a node that does not wait on inner loops
        Given a work item parked at verification
        When a pull request's inner loop finishes
        Then nothing is re-run

    Requirement: docs/specs/issue-538/requirements.md R2.3
    """
    _park(origin, node="verification")
    before = (_spec(origin) / STATE_FILENAME).read_bytes()

    assert _link().on_inner_loop_finished(WI, str(origin)) is None
    assert (_spec(origin) / STATE_FILENAME).read_bytes() == before
    (record,) = [f for e, f in events if e == "graph.outer_reevaluated"]
    assert record["outcome"] == "no-inner-gate"


def test_a_raising_runtime_is_contained(origin, events):
    """
    Feature: pull-request session notices
      Scenario: a fault in the re-evaluation does not escape
        Given a runtime that cannot be built
        When the re-evaluation runs
        Then it returns nothing and records a graph link failure

    Requirement: docs/specs/issue-538/requirements.md R3.5
    """
    link = _link()
    _park(origin)

    def boom(*args, **kwargs):
        raise RuntimeError("no runtime")

    link._build_runtime = boom  # type: ignore[method-assign]
    assert link.on_inner_loop_finished(WI, str(origin)) is None
    assert "graph.link_failed" in [e for e, _ in events]


def test_inner_loop_gate_reports_the_outer_node_and_whether_it_waits(origin):
    _park(origin)
    assert _link().inner_loop_gate(WI, str(origin)) == ("implementation", True)
    _park(origin, node="verification")
    assert _link().inner_loop_gate(WI, str(origin)) == ("verification", False)
