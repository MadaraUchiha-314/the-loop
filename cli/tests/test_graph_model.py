"""Graph compilation — every structural failure is a STARTUP failure (R1, R6b.1)."""

from __future__ import annotations

import pytest

from the_loop.graph import hooks  # noqa: F401 — register the built-ins
from the_loop.graph.model import GraphConfigError, compile_graph, load_graph

MINIMAL = {
    "nodes": [
        {"id": "a", "exit": ["validate-artifacts"]},
        {"id": "b", "terminal": True},
    ],
    "edges": [{"from": "a", "to": "b", "on": "pass"}],
}


def test_a_minimal_graph_compiles():
    graph = compile_graph(MINIMAL)
    assert graph.start == "a"
    assert graph.next_node("a", "pass") == "b"


def test_an_edge_naming_an_undeclared_node_fails_at_load():
    """Negative test, abuse case 5 — and it names the offender."""
    data = {
        "nodes": [{"id": "a"}],
        "edges": [{"from": "a", "to": "ghost", "on": "pass"}],
    }
    with pytest.raises(GraphConfigError, match="ghost"):
        compile_graph(data)


def test_an_unknown_hook_fails_at_load_and_lists_the_registered_ones():
    data = {"nodes": [{"id": "a", "exit": ["not-a-hook"]}]}
    with pytest.raises(GraphConfigError, match="unknown hook 'not-a-hook'"):
        compile_graph(data)


def test_a_node_without_an_id_is_refused():
    with pytest.raises(GraphConfigError, match="needs an id"):
        compile_graph({"nodes": [{"phase": "design"}]})


def test_a_duplicate_node_id_is_refused():
    with pytest.raises(GraphConfigError, match="duplicate node id"):
        compile_graph({"nodes": [{"id": "a"}, {"id": "a"}]})


def test_an_unknown_actor_is_refused():
    with pytest.raises(GraphConfigError, match="actor"):
        compile_graph({"nodes": [{"id": "a", "actor": "robot"}]})


def test_a_malformed_hook_entry_is_refused():
    with pytest.raises(GraphConfigError, match="malformed"):
        compile_graph({"nodes": [{"id": "a", "exit": [123]}]})


def test_cycles_are_accepted():
    """review -> fix -> review is a transition set, not a modelling error (R1.6)."""
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [
            {"from": "a", "to": "b", "on": "pass"},
            {"from": "b", "to": "a", "on": "changes-requested"},
        ],
    }
    graph = compile_graph(data)
    assert graph.next_node("b", "changes-requested") == "a"


def test_the_yaml_on_key_boolean_trap_is_handled():
    """`on:` unquoted parses as True in YAML 1.1 — authors should not have to know."""
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"from": "a", "to": "b", True: "pass"}],
    }
    assert compile_graph(data).next_node("a", "pass") == "b"


def test_first_declared_edge_wins_on_ambiguity():
    data = {
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [
            {"from": "a", "to": "b", "on": "pass"},
            {"from": "a", "to": "c", "on": "pass"},
        ],
    }
    assert compile_graph(data).next_node("a", "pass") == "b"


def test_unknown_node_lookup_lists_the_declared_ones():
    graph = compile_graph(MINIMAL)
    with pytest.raises(GraphConfigError, match="declared nodes are"):
        graph.node("nope")


# -- the shipped graph itself --------------------------------------------------


def test_the_shipped_graph_compiles():
    """CI validates the graph the plugin ships, so a malformed one cannot release."""
    graph = load_graph()
    assert graph.start == "brainstorming"
    assert "security-review" in graph.nodes
    assert graph.node("security-review").required is True


def test_the_shipped_graph_splits_the_needs_review_label():
    """The six nodes that were one label — where the measured drift piled up."""
    graph = load_graph()
    for node_id in (
        "self-review",
        "critic-review",
        "security-review",
        "evidence",
        "capability-docs",
        "reviewer-briefing",
    ):
        assert node_id in graph.nodes, f"{node_id} should be its own node"


def test_the_shipped_graph_has_no_dead_ends():
    graph = load_graph()
    for node in graph.ordered():
        if node.terminal:
            continue
        assert graph.edges_from(node.id), f"{node.id} has no outgoing edge"


def test_an_optional_node_is_declared_as_such():
    """Brainstorming is optional — the workflow reference says a work item whose
    scope is already clear starts at requirements-definition."""
    graph = load_graph()
    assert graph.node("brainstorming").optional is True
