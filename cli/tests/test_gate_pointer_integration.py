"""The stop gate never demands a node the work item has not reached (issue-429).

A work item parked at ``phase-selection`` with its selection recorded — the
spec chain's front declared away, the pointer not yet advanced — had its every
turn blocked by the harness stop gate demanding ``design.md``. The gate runs
``the-loop check --recompute``, and under ``--recompute`` ``currentNode`` is the
first node the *artifacts* leave unmet: ``design``, several nodes past where the
item is. ``check`` without the flag, meanwhile, said ``phase-selection``.

Every scenario builds a real checkout under ``tmp_path`` with a real state file
and evaluates the shipped graph through the real core facade. The last class
runs the gate script itself as a subprocess against the real CLI — the path a
spawned session takes — with the service routing off, so nothing starts a
daemon.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from the_loop.commands.graph_cmd import CheckCommand
from the_loop.core import graphs

GATE = Path(__file__).resolve().parents[2] / "hooks" / "the-loop-gate.py"
WORK_ITEM = "issue-1"

#: The ticket's shape: the selection is recorded (so `phase-selection` passes on
#: the artifacts), the front of the spec chain is declared away, and the item is
#: still parked where the selection left it.
PARKED_AT_SELECTION = {
    "workItem": WORK_ITEM,
    "currentNode": "phase-selection",
    "decisions": {"phase-selection": {"at": "2026-09-25T00:00:00Z"}},
    "parked": {"node": "phase-selection", "reason": "awaiting a human"},
    "skips": {
        "brainstorming": {"by": "octocat", "reason": "doc fix"},
        "requirements-definition": {"by": "octocat", "reason": "doc fix"},
        "requirements-approval": {"by": "octocat", "reason": "doc fix"},
    },
}


def load_gate():
    spec = importlib.util.spec_from_file_location("the_loop_gate", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _checkout(root: Path, state: dict | None) -> Path:
    spec_dir = root / "docs" / "specs" / WORK_ITEM
    spec_dir.mkdir(parents=True)
    if state is not None:
        (spec_dir / "work-item-state.json").write_text(json.dumps(state))
    return root


def _at(state: dict, node: str) -> dict:
    return {**state, "currentNode": node, "parked": None}


class TestTheReportCarriesThePointer:
    def test_recompute_reports_both_positions(self, tmp_path):
        """The derived position and the recorded one, side by side."""
        repo = _checkout(tmp_path, PARKED_AT_SELECTION)
        report = graphs.check(str(repo), WORK_ITEM, recompute=True)
        assert report["currentNode"] == "design", "the artifacts run ahead"
        assert report["pointer"] == "phase-selection"

    def test_without_recompute_the_pointer_is_the_current_node(self, tmp_path):
        repo = _checkout(tmp_path, PARKED_AT_SELECTION)
        report = graphs.check(str(repo), WORK_ITEM)
        assert report["currentNode"] == report["pointer"] == "phase-selection"

    @pytest.mark.parametrize("recompute", [False, True])
    def test_no_state_file_is_no_pointer(self, tmp_path, recompute):
        """The start-node fallback is `currentNode`'s, never the pointer's."""
        repo = _checkout(tmp_path, None)
        report = graphs.check(str(repo), WORK_ITEM, recompute=recompute)
        assert report["stateFound"] is False
        assert report["pointer"] == ""
        assert report["currentNode"] == "phase-selection"

    def test_the_position_unknown_answer_keeps_its_six_keys(self, tmp_path):
        """issue-238's answer for a repository that is not there is unchanged."""
        report = graphs.check(str(tmp_path / "gone"), WORK_ITEM, recompute=True)
        assert "pointer" not in report
        assert report["repoResolved"] is False


class TestTheGateOnARealReport:
    def test_a_parked_item_is_not_told_to_write_a_later_phase(self, tmp_path):
        """The ticket's reproduction, on the shipped graph."""
        repo = _checkout(tmp_path, PARKED_AT_SELECTION)
        report = graphs.check(str(repo), WORK_ITEM, recompute=True)
        assert load_gate().blocking_node(report) is None

    def test_the_same_item_once_at_design_is_blocked_on_design(self, tmp_path):
        """The fix narrows WHICH node is asked about, not whether one can block."""
        repo = _checkout(tmp_path, _at(PARKED_AT_SELECTION, "design"))
        report = graphs.check(str(repo), WORK_ITEM, recompute=True)
        found = load_gate().blocking_node(report)
        assert found is not None and found["node"] == "design"
        assert any("design.md" in m for m in found["messages"])

    def test_a_pointer_moved_past_an_unmet_node_still_blocks_on_it(self, tmp_path):
        """A forward-moved pointer (agent-writable) hides nothing behind it."""
        repo = _checkout(tmp_path, _at(PARKED_AT_SELECTION, "implementation"))
        report = graphs.check(str(repo), WORK_ITEM, recompute=True)
        found = load_gate().blocking_node(report)
        assert found is not None and found["node"] == "design"


class TestTheCheckTableSaysBoth:
    def _check(self, repo: Path, recompute: bool) -> int:
        args = argparse.Namespace(
            work_item=WORK_ITEM,
            repo=str(repo),
            spec_dir="",
            format="table",
            all=False,
            recompute=recompute,
            fail_on="unmet",
        )
        return CheckCommand().run(args)

    def test_a_derived_position_ahead_of_the_pointer_is_named(self, tmp_path, capsys):
        repo = _checkout(tmp_path, PARKED_AT_SELECTION)
        self._check(repo, recompute=True)
        out = capsys.readouterr().out
        assert "(at design)" in out
        assert "(pointer at phase-selection; position derived from the artifacts)" in (
            out
        )

    def test_agreeing_positions_print_the_plain_state_line(self, tmp_path, capsys):
        repo = _checkout(tmp_path, _at(PARKED_AT_SELECTION, "design"))
        self._check(repo, recompute=True)
        assert "pointer at" not in capsys.readouterr().out

    def test_without_recompute_nothing_changes(self, tmp_path, capsys):
        repo = _checkout(tmp_path, PARKED_AT_SELECTION)
        self._check(repo, recompute=False)
        out = capsys.readouterr().out
        assert "(at phase-selection)" in out
        assert "pointer at" not in out


class TestTheStopHookEndToEnd:
    """The gate script as the harness runs it, against the real CLI."""

    @pytest.fixture
    def run_gate(self, tmp_path):
        # A `the-loop` on PATH that is this interpreter's CLI, so the gate's
        # `shutil.which` finds it whatever the environment installed.
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        shim = bin_dir / "the-loop"
        shim.write_text(f'#!/bin/sh\nexec "{sys.executable}" -m the_loop "$@"\n')
        shim.chmod(0o755)
        config = tmp_path / "cli-config.yaml"
        config.write_text('version: "0.12.0"\n')

        def run(repo: Path) -> subprocess.CompletedProcess:
            env = {
                **os.environ,
                "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                "THE_LOOP_WORK_ITEM": WORK_ITEM,
                "THE_LOOP_SERVICE_LOCAL": "1",
                "THE_LOOP_CLI_CONFIG": str(config),
                "THE_LOOP_GATE_MAX_ATTEMPTS": "3",
                "TMPDIR": str(tmp_path),  # the attempt counter stays in the test's tree
            }
            return subprocess.run(
                [sys.executable, str(GATE), "claude"],
                cwd=repo,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
            )

        return run

    @pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell shim")
    def test_the_ticket_reproduction_lets_the_turn_end(self, tmp_path, run_gate):
        repo = _checkout(tmp_path / "checkout", PARKED_AT_SELECTION)
        proc = run_gate(repo)
        assert proc.returncode == 0, proc.stderr
        assert "design.md" not in proc.stderr

    @pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell shim")
    def test_an_item_at_design_is_still_held_on_it(self, tmp_path, run_gate):
        repo = _checkout(tmp_path / "checkout", _at(PARKED_AT_SELECTION, "design"))
        proc = run_gate(repo)
        assert proc.returncode == 2
        assert "design.md" in proc.stderr
