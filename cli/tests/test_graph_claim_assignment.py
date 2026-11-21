"""A claim's answer carries the next assignment (issue-551, Requirement 1).

`the-loop graph complete` used to answer ``advanced to <node>`` and nothing
else: the entered node's `deliver-assignment` hook skips on the CLI path, so the
claiming session was told where it stood and not what to do there. The envelope
now carries ``assignment`` and ``next`` for the node the pointer ends on.
"""

from __future__ import annotations

import pytest

from the_loop import prompts
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.assignment import render_assignment
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState

ITEM = "issue-1"

GRAPH = {
    "start": "draft",
    "nodes": [
        {
            "id": "draft",
            "produces": ["design.md"],
            "exit": [{"hook": "validate-artifacts", "with": {"locked": True}}],
        },
        {"id": "extra", "skippable": True, "entry": ["deliver-assignment"]},
        {
            "id": "build",
            "phase": "implementation",
            "command": "execute-tasks",
            "entry": ["deliver-assignment"],
        },
        {"id": "gate", "actor": "human", "required": True},
        {"id": "last", "command": "finish-tasks"},
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "draft", "to": "extra", "on": "pass"},
        {"from": "extra", "to": "build", "on": "pass"},
        {"from": "extra", "to": "build", "on": "skipped"},
        {"from": "build", "to": "gate", "on": "pass"},
        {"from": "gate", "to": "last", "on": "approved"},
        {"from": "last", "to": "done", "on": "pass"},
    ],
}

CONTINUE = prompts.load("assignment/continue", inline=True)


@pytest.fixture()
def spec(tmp_path):
    path = tmp_path / "docs" / "specs" / ITEM
    path.mkdir(parents=True)
    return path


def _runtime(tmp_path, **config):
    return Runtime(tmp_path, graph=compile_graph(GRAPH), config=config)


def _stand_on(spec, node, skips=None):
    state = WorkItemState.load(spec, ITEM)
    state.enter(node)
    state.skips = dict(skips or {})
    state.save(spec)


def _write_design(spec):
    (spec / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")


def _rendered(tmp_path, spec, node_id):
    """What the daemon's delivery renders for ``node_id`` — the one renderer."""
    runtime = _runtime(tmp_path)
    return render_assignment(
        HookContext(
            work_item=WorkItem(ref="", id=ITEM, spec_dir=spec),
            node=runtime.graph.node(node_id).as_mapping(),
            boundary="entry",
            repo=tmp_path,
            config={},
        )
    )


def test_an_agent_node_is_assigned_and_the_session_is_told_to_continue(tmp_path, spec):
    _stand_on(spec, "extra")

    answer = _runtime(tmp_path).complete(ITEM, node="extra")

    assert answer["moved"] and answer["currentNode"] == "build"
    assert answer["next"] == {
        "node": "build",
        "actor": "agent",
        "command": "execute-tasks",
        "continue": True,
    }
    text = answer["assignment"]
    assert text.startswith(_rendered(tmp_path, spec, "build")), "the one renderer"
    assert "you are now at node: build" in text
    assert "/the-loop:execute-tasks issue-1" in text
    assert text.endswith(CONTINUE)


def test_a_human_node_says_the_session_waits_and_for_which_gate(tmp_path, spec):
    _stand_on(spec, "build")

    answer = _runtime(tmp_path).complete(ITEM, node="build")

    assert answer["currentNode"] == "gate"
    assert answer["next"] == {
        "node": "gate",
        "actor": "human",
        "command": "",
        "continue": False,
    }
    text = answer["assignment"]
    assert text.endswith(prompts.render("assignment/wait", inline=True, node_id="gate"))
    assert "gate" in text.splitlines()[-1]
    assert CONTINUE not in text


def test_a_claim_through_skips_describes_only_the_node_it_ends_on(tmp_path, spec):
    _write_design(spec)
    _stand_on(spec, "draft", skips={"extra": {"by": "octocat", "reason": "small"}})

    answer = _runtime(tmp_path).complete(ITEM, node="draft")

    assert answer["currentNode"] == "build"
    assert answer["next"]["node"] == "build"
    assert "node: build" in answer["assignment"]
    assert "extra" not in answer["assignment"]


def test_a_blocked_claim_carries_neither_field(tmp_path, spec):
    _stand_on(spec, "draft")  # design.md is not written

    answer = _runtime(tmp_path).complete(ITEM, node="draft")

    assert answer["status"] == "block" and not answer["moved"]
    assert "assignment" not in answer and "next" not in answer


def test_a_replayed_claim_carries_neither_field(tmp_path, spec):
    _stand_on(spec, "build")

    answer = _runtime(tmp_path).complete(ITEM, node="draft")

    assert answer["status"] == "noop"
    assert "assignment" not in answer and "next" not in answer


def test_a_refused_claim_carries_neither_field(tmp_path, spec):
    _stand_on(spec, "draft")

    answer = _runtime(tmp_path).complete(ITEM, node="gate")

    assert answer["status"] == "refused"
    assert "assignment" not in answer and "next" not in answer


def test_a_claim_that_has_not_started_carries_neither_field(tmp_path, spec):
    answer = _runtime(tmp_path).complete(ITEM)

    assert answer["status"] == "refused"
    assert "assignment" not in answer and "next" not in answer


def test_an_assignment_a_sink_delivered_is_not_repeated(tmp_path, spec):
    _stand_on(spec, "extra")
    delivered = []
    runtime = _runtime(
        tmp_path, assignmentDeliver=lambda text: delivered.append(text) or True
    )

    answer = runtime.complete(ITEM, node="extra")

    assert answer["moved"] and answer["currentNode"] == "build"
    assert len(delivered) == 1
    assert "assignment" not in answer and "next" not in answer


def test_a_sink_that_reached_no_session_leaves_the_envelope_to_carry_it(tmp_path, spec):
    _stand_on(spec, "extra")
    runtime = _runtime(tmp_path, assignmentDeliver=lambda text: False)

    answer = runtime.complete(ITEM, node="extra")

    assert answer["next"]["node"] == "build"
    assert answer["assignment"].endswith(CONTINUE)


def test_entering_a_terminal_node_assigns_nothing(tmp_path, spec):
    _stand_on(spec, "last")

    answer = _runtime(tmp_path).complete(ITEM, node="last")

    assert answer["moved"] and answer["currentNode"] == "done"
    assert "assignment" not in answer and "next" not in answer


def test_a_pull_requests_claim_names_its_own_loop(tmp_path, spec):
    _stand_on(spec, "extra")
    runtime = _runtime(tmp_path, assignmentPr=16)

    answer = runtime.complete(ITEM, node="extra")

    assert f"the-loop graph complete {ITEM} --pr 16" in answer["assignment"]
