"""Graph compilation — every structural failure is a STARTUP failure (R1, R6b.1)."""

from __future__ import annotations

from pathlib import Path

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


class TestTheGraphShipsWithTheCli:
    """The graph is executed by the CLI, so it must ship *in* the CLI.

    It previously lived under `skills/the-loop/graph/` — the plugin, which is
    the harness integration. That made `pip install the-loopy-one` produce a
    runtime with no process to run: every hook the graph names is registered in
    this package, so a graph the package cannot find is a graph nothing can use.
    """

    def test_the_graph_lives_inside_the_the_loop_package(self):
        from the_loop.graph import model

        path = model.shipped_graph_path()
        package_root = Path(model.__file__).resolve().parent.parent
        assert package_root in path.resolve().parents, (
            f"{path} is outside {package_root}; it will not ship in the wheel"
        )

    def test_it_resolves_without_a_plugin_root_or_a_repo_checkout(self, monkeypatch):
        """The regression: a pip-only install must still find its graph.

        Neither a `CLAUDE_PLUGIN_ROOT` nor a repository checkout is available to
        someone who ran `pip install the-loopy-one`, and telling them to set an
        env var pointing at a plugin they never installed is not a remedy.
        """
        from the_loop.graph import model

        monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
        monkeypatch.chdir(Path(__file__).resolve().parent)
        path = model.shipped_graph_path()
        assert path.is_file()

    def test_the_resolved_graph_actually_compiles(self):
        """Shipping the file is only half of it — it must still load."""
        from the_loop.graph.model import load_graph, shipped_graph_path

        graph = load_graph(shipped_graph_path())
        assert graph.start and graph.nodes


class TestProducesNamesAnArtifactNotAFile:
    """One artifact, several accepted names (issue-124, decision-045).

    A bug's phase-1 spec is called `bugfix.md`. The graph had no way to say
    that, so the node gating phase 1 demanded `requirements.md` and every bug
    work item blocked on the absence of a file the documentation told it not to
    write.
    """

    def test_alternatives_are_split_in_declaration_order(self):
        from the_loop.graph.model import artifact_names

        assert artifact_names("requirements.md|bugfix.md") == (
            "requirements.md",
            "bugfix.md",
        )

    def test_a_single_name_is_a_one_element_group(self):
        from the_loop.graph.model import artifact_names

        assert artifact_names("design.md") == ("design.md",)

    def test_surrounding_whitespace_is_not_part_of_the_name(self):
        from the_loop.graph.model import artifact_names

        assert artifact_names("requirements.md | bugfix.md") == (
            "requirements.md",
            "bugfix.md",
        )

    @pytest.mark.parametrize("entry", ["a.md||b.md", "|a.md", "a.md|", "|", "  |  "])
    def test_an_empty_alternative_fails_at_load(self, entry):
        """A slip that would otherwise resolve to a silently shorter list of
        names — a gate quietly accepting fewer artifacts than its author wrote.
        Every structural failure is a startup failure."""
        with pytest.raises(GraphConfigError, match="empty alternative"):
            compile_graph({"nodes": [{"id": "a", "produces": [entry]}]})

    def test_the_offending_node_and_entry_are_both_named(self):
        with pytest.raises(GraphConfigError, match="'phase-one'.*'a.md\\|\\|b.md'"):
            compile_graph({"nodes": [{"id": "phase-one", "produces": ["a.md||b.md"]}]})

    def test_the_entry_is_kept_verbatim_so_graph_show_reports_what_was_declared(self):
        """Splitting at parse time would make `the-loop graph show --format json`
        claim two artifacts where the graph means one."""
        graph = compile_graph(
            {"nodes": [{"id": "a", "produces": ["requirements.md|bugfix.md"]}]}
        )
        assert graph.node("a").produces == ("requirements.md|bugfix.md",)
        assert graph.node("a").as_mapping()["produces"] == ["requirements.md|bugfix.md"]

    def test_resolution_reports_which_names_are_present(self, tmp_path):
        from the_loop.graph.model import resolve_produces

        (tmp_path / "bugfix.md").write_text("x")
        (slot,) = resolve_produces(["requirements.md|bugfix.md"], tmp_path)
        assert slot.names == ("requirements.md", "bugfix.md")
        assert slot.present == (tmp_path / "bugfix.md",)
        assert slot.alternatives is True

    def test_resolution_never_chooses_between_two_present_names(self, tmp_path):
        """Choosing is a policy decision, and it belongs to the hook that has to
        make it — `validate-artifacts` blocks rather than preferring whichever
        name the graph happened to list first."""
        from the_loop.graph.model import resolve_produces

        (tmp_path / "requirements.md").write_text("x")
        (tmp_path / "bugfix.md").write_text("x")
        (slot,) = resolve_produces(["requirements.md|bugfix.md"], tmp_path)
        assert len(slot.present) == 2

    def test_the_shipped_phase_one_node_accepts_both_documented_names(self):
        """The end of the mismatch, asserted against the real graph."""
        from the_loop.graph.model import artifact_names, load_graph, shipped_graph_path

        node = load_graph(shipped_graph_path()).node("requirements-definition")
        accepted = {n for entry in node.produces for n in artifact_names(entry)}
        assert accepted == {"requirements.md", "bugfix.md"}
