"""The operator's own hooks, end to end through the shipped seams (issue-248, issue-352).

    cli-config.yaml declares routing.graph.hooks
        → build_runtime → read_declaration → load_graph(repo=…, declaration=…)
        → the module is executed and its x- hooks collected
        → the attachment is appended to the node's chain
        → Runtime.evaluate runs it, and `the-loop check` reports its finding

Every scenario builds a real checkout under ``tmp_path`` — a hook module of three
lines, a spec folder — and a real CLI config naming it, then drives the real runtime
over the real shipped graph. No network, no subprocess, no ``gh`` binary.

The operator-facing half is here too: the inspection action must import nothing, and a
checkout whose module is never declared must never have it run (issue-352 replaced the
``repoHooks`` kill switch with that rule — the CLI reads no repository's declaration).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from the_loop.commands.graph_cmd import GraphCommand
from the_loop.graph import extensions, hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime, load_cli_config_best_effort
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

HOOKS = """
version: "0.9.0"
routing:
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


def _repository(tmp_path: Path, module: str = BLOCKING_MODULE):
    (tmp_path / ".the-loop" / "hooks").mkdir(parents=True)
    (tmp_path / ".the-loop" / "hooks" / "house.py").write_text(module)
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("VALUE = 1\n")
    return tmp_path


def _cli_config(tmp_path: Path, monkeypatch, body: str = HOOKS) -> Path:
    path = tmp_path / "cli-config.yaml"
    path.write_text(body.lstrip())
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    return path


def _evaluate(repo: Path, node: str = "complete"):
    runtime = build_runtime(repo)
    return runtime.evaluate(node, runtime.work_item(WORK_ITEM, REF))


def test_a_declared_hook_gates_a_node(tmp_path, monkeypatch):
    """
    Feature: an operator brings a rule the-loop does not ship
      Scenario: the CLI config declares a hook module and the loop runs it at the
                boundary it named
        Given a CLI config declaring routing.graph.hooks with one module and one attachment
        And a checkout carrying that module and a source file missing the licence header
        When the-loop evaluates the node the hook is attached to
        Then the node is blocked, and the finding is the hook's own message
        And fixing the file makes the same node pass

    Requirement: docs/specs/issue-248/requirements.md R1.1, R1.3, R1.4; issue-352 R2
    """
    repo = _repository(tmp_path)
    _cli_config(tmp_path, monkeypatch)

    outcome = _evaluate(repo)
    assert outcome.status == "block"
    assert "missing SPDX header" in outcome.render()

    (repo / "src" / "a.py").write_text("# SPDX-License-Identifier: MIT\nVALUE = 1\n")
    assert _evaluate(repo).status == "pass"


def test_the_cli_and_the_runtime_evaluate_the_same_chain(tmp_path, monkeypatch):
    """
    Feature: one loader, so every caller sees the same process
      Scenario: the operator's hook gates a node for the CLI and the daemon alike
        Given a CLI config whose hook is attached to a node
        When the graph is loaded the way `the-loop check` loads it
        And the graph is loaded the way the daemon's runtime loads it
        Then both chains end in the declared hook

    Requirement: docs/specs/issue-248/requirements.md R1.5
    """
    repo = _repository(tmp_path)
    _cli_config(tmp_path, monkeypatch)
    declaration = extensions.read_declaration(load_cli_config_best_effort())
    direct = load_graph(repo=repo, declaration=declaration).node("complete").exit
    through_runtime = build_runtime(repo).graph.node("complete").exit
    assert direct == through_runtime == ({"hook": "x-licence-header"},)


def test_a_module_that_cannot_be_imported_stops_the_loop(tmp_path, monkeypatch):
    """
    Feature: a declared gate either runs or is loudly absent
      Scenario: a hook module that cannot be imported stops the loop instead of
                quietly disappearing
        Given a CLI config whose declared hook module raises on import
        When the graph is loaded
        Then the load fails, naming the module
        And no graph is returned with the gate silently missing

    Requirement: docs/specs/issue-248/requirements.md R4.1, R4.4
    """
    repo = _repository(tmp_path, module="raise RuntimeError('boom')\n")
    _cli_config(tmp_path, monkeypatch)
    with pytest.raises(GraphConfigError) as failure:
        build_runtime(repo)
    assert "house.py" in str(failure.value)
    assert "boom" in str(failure.value)


def test_the_operator_can_inspect_without_importing(tmp_path, monkeypatch, capsys):
    """
    Feature: an operator decides with the facts
      Scenario: the operator inspects the hook declarations without importing them
        Given a CLI config whose hook module would raise if it were ever executed
        When the operator runs `the-loop graph hooks`
        Then the declared module and attachment are reported
        And the module was never imported, so the command succeeds

    Requirement: docs/specs/issue-248/requirements.md R5.1
    """
    repo = _repository(tmp_path, module="raise RuntimeError('never run me')\n")
    _cli_config(tmp_path, monkeypatch)
    args = argparse.Namespace(repo=str(repo), action="hooks", format="json")
    assert GraphCommand().run(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["modules"] == [{"path": ".the-loop/hooks/house.py", "module": ""}]
    assert report["attach"] == [
        {"hook": "x-licence-header", "node": "complete", "boundary": "exit", "with": {}}
    ]
    assert "validate-artifacts" in report["shipped"]


def test_an_undeclared_module_in_a_checkout_is_never_run(tmp_path, monkeypatch):
    """
    Feature: a repository cannot opt its own code into the-loop's process
      Scenario: a checkout carries a hook module the operator never declared
        Given a checkout whose hook module would raise if it were ever executed
        And a CLI config declaring no hooks
        When the graph is loaded for that checkout
        Then the graph compiles with no hook attached and nothing imported

    Requirement: docs/specs/issue-352/requirements.md R2.3
    """
    repo = _repository(tmp_path, module="raise RuntimeError('never run me')\n")
    _cli_config(tmp_path, monkeypatch, 'version: "0.9.0"\n')
    graph = build_runtime(repo).graph
    assert graph.extension_hooks == {}
    assert graph.node("complete").exit == ()


def test_a_machine_that_declares_nothing_runs_the_shipped_graph(tmp_path, monkeypatch):
    """
    Feature: the feature costs nothing to an operator who never asked for it
      Scenario: a CLI config with no routing.graph.hooks block compiles the shipped graph
        Given a CLI config declaring no graph hooks
        When the graph is loaded
        Then it is the shipped graph, with no extra hook in any chain

    Requirement: docs/specs/issue-248/requirements.md R1.6
    """
    repo = _repository(tmp_path)
    _cli_config(tmp_path, monkeypatch, 'version: "0.9.0"\n')
    graph = build_runtime(repo).graph
    shipped = load_graph()
    assert graph.extension_hooks == {}
    assert [n.exit for n in graph.ordered()] == [n.exit for n in shipped.ordered()]
