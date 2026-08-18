"""A repository's own hooks, end to end through the shipped seams (issue-248).

    .the-loop/harness-config.yaml declares graph.hooks
        → build_runtime → load_graph(repo=…) reads it
        → the module is executed and its x- hooks collected
        → the attachment is appended to the node's chain
        → Runtime.evaluate runs it, and `the-loop check` reports its finding

Every scenario builds a real repository under ``tmp_path`` — a harness config, a hook
module of three lines, a spec folder — and drives the real runtime over the real
shipped graph. No network, no subprocess, no ``gh`` binary.

The operator-facing half is here too, because "an operator can see what a repository
would run before running it" is a behaviour, not an implementation detail: the
inspection action must import nothing, and the kill switch must import nothing.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from the_loop.commands.graph_cmd import GraphCommand
from the_loop.graph import extensions, hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.model import GraphConfigError, load_graph

WORK_ITEM = "issue-248"
REF = "github:octo/repo#248"

BLOCKING_MODULE = """
from the_loop.graph import HookResult, Message, hook


@hook("x-licence-header")
def licence_header(ctx):
    missing = [p.name for p in (ctx.repo / "src").glob("*.py")
               if "SPDX" not in p.read_text()]
    if missing:
        return HookResult.blocked(
            "x-licence-header",
            [Message(text="missing SPDX header", path=name) for name in missing],
        )
    return HookResult.ok("x-licence-header")
"""

HARNESS = """
version: "0.2.0"
ticketing:
  system: github
  github:
    owner: octo
    repo: repo
graph:
  hooks:
    modules:
      - path: .the-loop/hooks/house.py
    attach:
      - hook: x-licence-header
        node: complete
"""


@pytest.fixture(autouse=True)
def _forget_loaded_modules():
    extensions.clear_module_cache()
    yield
    extensions.clear_module_cache()


def _repository(tmp_path: Path, module: str = BLOCKING_MODULE, harness: str = HARNESS):
    (tmp_path / ".the-loop" / "hooks").mkdir(parents=True)
    (tmp_path / ".the-loop" / "hooks" / "house.py").write_text(module)
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(harness)
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("VALUE = 1\n")
    return tmp_path


def _evaluate(repo: Path, node: str = "complete"):
    runtime = build_runtime(repo)
    return runtime.evaluate(node, runtime.work_item(WORK_ITEM, REF))


def test_a_repository_hook_gates_a_node(tmp_path):
    """
    Feature: a repository brings a rule the-loop does not ship
      Scenario: a repository declares a hook module and the loop runs it at the
                boundary it named
        Given a repository declaring graph.hooks with one module and one attachment
        And a source file missing the licence header its hook requires
        When the-loop evaluates the node the hook is attached to
        Then the node is blocked, and the finding is the repository's own message
        And fixing the file makes the same node pass

    Requirement: docs/specs/issue-248/requirements.md R1.1, R1.3, R1.4
    """
    repo = _repository(tmp_path)

    outcome = _evaluate(repo)
    assert outcome.status == "block"
    assert "missing SPDX header" in outcome.render()

    (repo / "src" / "a.py").write_text("# SPDX-License-Identifier: MIT\nVALUE = 1\n")
    assert _evaluate(repo).status == "pass"


def test_the_cli_and_the_runtime_evaluate_the_same_chain(tmp_path):
    """
    Feature: one loader, so every caller sees the same process
      Scenario: a repository's own hook gates a node for the CLI and the daemon alike
        Given a repository whose hook is attached to a node
        When the graph is loaded the way `the-loop check` loads it
        And the graph is loaded the way the daemon's runtime loads it
        Then both chains end in the repository's hook

    Requirement: docs/specs/issue-248/requirements.md R1.5
    """
    repo = _repository(tmp_path)
    direct = load_graph(repo=repo).node("complete").exit
    through_runtime = build_runtime(repo).graph.node("complete").exit
    assert direct == through_runtime == ({"hook": "x-licence-header"},)


def test_a_module_that_cannot_be_imported_stops_the_loop(tmp_path):
    """
    Feature: a declared gate either runs or is loudly absent
      Scenario: a hook module that cannot be imported stops the loop instead of
                quietly disappearing
        Given a repository whose declared hook module raises on import
        When the graph is loaded
        Then the load fails, naming the module
        And no graph is returned with the gate silently missing

    Requirement: docs/specs/issue-248/requirements.md R4.1, R4.4
    """
    repo = _repository(tmp_path, module="raise RuntimeError('boom')\n")
    with pytest.raises(GraphConfigError) as failure:
        load_graph(repo=repo)
    assert "house.py" in str(failure.value)
    assert "boom" in str(failure.value)


def test_the_operator_can_inspect_without_importing(tmp_path, capsys):
    """
    Feature: an operator decides with the facts
      Scenario: the operator inspects a repository's hook declarations without
                importing them
        Given a repository whose hook module would raise if it were ever executed
        When the operator runs `the-loop graph hooks` against that repository
        Then the declared module and attachment are reported
        And the module was never imported, so the command succeeds

    Requirement: docs/specs/issue-248/requirements.md R5.1
    """
    repo = _repository(tmp_path, module="raise RuntimeError('never run me')\n")
    args = argparse.Namespace(repo=str(repo), action="hooks", format="json")
    assert GraphCommand().run(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["modules"] == [{"path": ".the-loop/hooks/house.py", "module": ""}]
    assert report["attach"] == [
        {"hook": "x-licence-header", "node": "complete", "boundary": "exit", "with": {}}
    ]
    assert "validate-artifacts" in report["shipped"]


def test_the_operator_can_refuse_repository_hooks(tmp_path, caplog):
    """
    Feature: an operator refuses repository code machine-wide
      Scenario: the operator refuses repository hooks and nothing from the repository
                is imported
        Given a repository whose hook module would raise if it were ever executed
        When the graph is loaded with repository hooks refused
        Then the graph compiles with no repository hook attached
        And a warning names the repository whose hooks were refused

    Requirement: docs/specs/issue-248/requirements.md R5.2
    """
    repo = _repository(tmp_path, module="raise RuntimeError('never run me')\n")
    with caplog.at_level("WARNING"):
        graph = load_graph(repo=repo, allow_repo_hooks=False)
    assert graph.extension_hooks == {}
    assert graph.node("complete").exit == ()
    assert "refuses them" in caplog.text


def test_a_repository_that_declares_nothing_is_untouched(tmp_path):
    """
    Feature: the feature costs nothing to a repository that never asked for it
      Scenario: a repository with no graph.hooks block compiles the shipped graph
        Given a repository whose harness config declares no graph hooks
        When the graph is loaded for that repository
        Then it is the shipped graph, with no repository hooks in any chain

    Requirement: docs/specs/issue-248/requirements.md R1.6
    """
    repo = _repository(tmp_path, harness='version: "0.2.0"\n')
    graph = load_graph(repo=repo)
    shipped = load_graph()
    assert graph.extension_hooks == {}
    assert [n.exit for n in graph.ordered()] == [n.exit for n in shipped.ordered()]


def test_a_repository_on_the_pre_rename_config_still_works(tmp_path):
    """
    Feature: the declaration is read wherever the harness config is
      Scenario: a repository that never renamed config.yaml still gets its hooks
        Given a repository declaring graph.hooks in the pre-rename .the-loop/config.yaml
        When the graph is loaded for that repository
        Then its hook is attached, because one reader resolves both filenames

    Requirement: docs/specs/issue-248/requirements.md R1.1 (T10)
    """
    repo = _repository(tmp_path)
    (repo / ".the-loop" / "harness-config.yaml").unlink()
    (repo / ".the-loop" / "config.yaml").write_text(HARNESS)
    assert load_graph(repo=repo).node("complete").exit == ({"hook": "x-licence-header"},)
