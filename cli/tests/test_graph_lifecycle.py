"""The runtime publishes a work item's lifecycle on the bus (issue-378).

Every transition the runtime records — `start`, an edge taken by `advance`, a
terminal node, `cleanup` — publishes `phase.started` / `phase.completed` for the
**phase**, never the node: two nodes sharing a phase publish nothing between them,
a node without a phase inherits the phase before it, and a `force` publishes
nothing because it runs no entry chain and sets no label.

The subscriber is a fake provider registered in `CHANNEL_PROVIDERS`, which is
also the proof that delivery is nobody's channel in particular (R6.3): no Slack
section exists anywhere in these configs.

Spec: docs/specs/issue-378/testing-plan.md T3, T5, T18.
"""

from __future__ import annotations

import pytest

from the_loop.channels import base as channels_base
from the_loop.channels.base import PostResult
from the_loop.graph import hooks  # noqa: F401 — registers the built-in hooks
from the_loop.graph.model import PDLC_WORK_ITEM_LOOP, compile_graph, load_graph
from the_loop.graph.runtime import Runtime, force

GRAPH = {
    "name": "test-loop",
    "start": "select",
    "nodes": [
        {"id": "select", "phase": "phase-selection", "actor": "human"},
        {"id": "author", "phase": "requirements-definition"},
        {"id": "approve", "actor": "human"},  # no phase: inherits the author's
        {"id": "design", "phase": "design"},
        {"id": "done", "phase": "complete", "terminal": True},
        {"id": "cleanup", "phase": "cleanup", "actor": "code", "terminal": True},
    ],
    "edges": [
        {"from": "select", "to": "author", "on": "pass"},
        {"from": "author", "to": "approve", "on": "pass"},
        {"from": "approve", "to": "design", "on": "pass"},
        {"from": "design", "to": "done", "on": "pass"},
    ],
}

REF = "github:octo/repo#378"


class RecordingChannel:
    """A channel of a type the-loop does not ship, subscribed to the lifecycle."""

    name = "recorder"

    def __init__(self):
        self.posted = []

    def subscribes(self, event_type):
        return event_type.startswith("phase.") or event_type == "work-item.closed"

    def may_publish(self, event_type):
        return False

    def post(self, event):
        self.posted.append(event)
        return PostResult(channel=self.name, ok=True)


@pytest.fixture()
def recorder(monkeypatch):
    channel = RecordingChannel()
    providers = dict(channels_base.CHANNEL_PROVIDERS)
    providers["recorder"] = lambda config, factory: channel
    monkeypatch.setattr(channels_base, "CHANNEL_PROVIDERS", providers)
    return channel


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-378").mkdir(parents=True)
    return tmp_path


def runtime_for(repo, graph=GRAPH, **config):
    return Runtime(
        repo,
        graph=compile_graph(graph),
        config={"channels": {"recorder": {"enabled": True}}, **config},
    )


def kinds(recorder):
    return [
        (e.event_type, e.detail.get("phase"), e.detail.get("node"))
        for e in recorder.posted
    ]


# -- T3: the walk --------------------------------------------------------------------


def test_start_publishes_the_first_phase(repo, recorder):
    """R1.1: entering the graph starts its first phase, and a human node says so."""
    runtime_for(repo).start("issue-378", ref=REF)

    assert kinds(recorder) == [("phase.started", "phase-selection", "select")]
    (event,) = recorder.posted
    assert event.work_item == REF
    assert event.url == "https://github.com/octo/repo/issues/378"
    assert event.source == "loop"
    assert event.detail["actor"] == "human"
    assert event.detail["loop"] == "test-loop"
    assert "waiting on a person" in event.text
    assert "phase-selection" in event.text


def test_an_edge_into_another_phase_completes_one_and_starts_the_next(repo, recorder):
    """R1.1, R1.2: completed (outcome, to) then started, in that order."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    recorder.posted.clear()

    rt.advance("issue-378", ref=REF)

    assert kinds(recorder) == [
        ("phase.completed", "phase-selection", "select"),
        ("phase.started", "requirements-definition", "author"),
    ]
    completed, started = recorder.posted
    assert completed.detail["outcome"] == "pass"
    assert completed.detail["to"] == "author"
    assert "completed phase" in completed.text
    assert "waiting on a person" not in started.text


def test_two_nodes_sharing_a_phase_publish_nothing_between_them(repo, recorder):
    """R1.3: `author` → `approve` (no phase of its own) is one label; the approval
    node inherits it, and leaving it completes the inherited phase."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    rt.advance("issue-378", ref=REF)  # select → author
    recorder.posted.clear()

    rt.advance("issue-378", ref=REF)  # author → approve
    assert kinds(recorder) == []

    rt.advance("issue-378", ref=REF)  # approve → design
    assert kinds(recorder) == [
        ("phase.completed", "requirements-definition", "approve"),
        ("phase.started", "design", "design"),
    ]


def test_a_terminal_node_completes_its_phase(repo, recorder):
    """R1.2: the last node has no successor; advancing it completes the phase."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    for _ in range(4):
        rt.advance("issue-378", ref=REF)  # … → done
    recorder.posted.clear()

    rt.advance("issue-378", ref=REF)  # done is terminal

    assert kinds(recorder) == [("phase.completed", "complete", "done")]


def test_cleanup_starts_its_phase_and_completes_none(repo, recorder):
    """R1.4: a cleanup ends a walk; it satisfies no gate."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    rt.advance("issue-378", ref=REF)  # select → author
    recorder.posted.clear()

    rt.cleanup("issue-378", ref=REF, reason="issue-closed")

    assert kinds(recorder) == [("phase.started", "cleanup", "cleanup")]
    (event,) = recorder.posted
    assert event.detail["from"] == "author"
    assert rt.cleanup("issue-378", ref=REF) is None  # idempotent: nothing more
    assert len(recorder.posted) == 1


def test_a_force_publishes_nothing(repo, recorder):
    """R1.5: no entry chain, no label, no lifecycle."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    recorder.posted.clear()

    force(rt, "issue-378", "design", "unblocking", ref=REF)

    assert recorder.posted == []


def test_a_config_without_channels_publishes_nothing_and_still_advances(repo, recorder):
    """R1.7: the transition is what it was; the bus is never even asked."""
    rt = Runtime(repo, graph=compile_graph(GRAPH), config={})
    rt.start("issue-378", ref=REF)
    report = rt.advance("issue-378", ref=REF)

    assert report.status == "pass"
    assert recorder.posted == []


def test_lifecycle_text_is_fixed_words_and_ids(repo, recorder):
    """A5: nothing from an artifact, a comment or the environment is read."""
    (repo / "docs" / "specs" / "issue-378" / "requirements.md").write_text(
        "---\nstatus: draft\n---\n\nSECRET-BODY\n"
    )
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)
    rt.advance("issue-378", ref=REF)

    for event in recorder.posted:
        assert "SECRET-BODY" not in event.text
        assert "SECRET-BODY" not in " ".join(map(str, event.detail.values()))


# -- T18: a provider the-loop does not ship --------------------------------------


def test_a_registered_provider_receives_the_lifecycle_with_no_slack_anywhere(
    repo, recorder
):
    """R6.3: the runtime, the publisher and the bus name no channel type."""
    rt = runtime_for(repo)
    rt.start("issue-378", ref=REF)

    assert [e.event_type for e in recorder.posted] == ["phase.started"]
    assert "slack" not in str(rt.config)


# -- T5: every human gate of the shipped outer loop is announced -------------------


def _hook_names(chain):
    names = []
    for spec in chain:
        if isinstance(spec, str):
            names.append(spec)
        elif isinstance(spec, dict):
            names.append(str(spec.get("hook") or ""))
    return names


def test_every_human_node_of_the_outer_loop_is_announced():
    """R2.1: a gate carries a phase (so `phase.started` announces it with
    `actor: human`) or runs `notify` on entry. A gate added without either
    fails here rather than parking a work item in silence."""
    graph = load_graph(name=PDLC_WORK_ITEM_LOOP)
    human = [node for node in graph.nodes.values() if node.actor == "human"]
    assert human, "the outer loop has human gates"
    for node in human:
        assert node.phase or "notify" in _hook_names(node.entry), (
            f"{node.id} is a human gate with neither a phase nor a notify hook"
        )
