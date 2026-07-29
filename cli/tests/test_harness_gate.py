"""The harness stop-hook gate wrapper (issue-109, task 34).

The wrapper used to be bash, which is why it had no tests: pytest cannot reach
into a shell script's branches, so its attempt cap, its two harness protocols
and its no-op paths were all asserted by reading them. It is Python now, so
they are asserted by running them.

It is loaded by path rather than imported as a module: it ships with the
**plugin**, not with the CLI, because what it encodes is harness protocol —
Claude Code's exit-2 contract and Cursor's followup_message. That split is the
same one the graph move settled, applied in the other direction.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[2] / "hooks" / "the-loop-gate.py"


def load_gate():
    spec = importlib.util.spec_from_file_location("the_loop_gate", GATE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate():
    return load_gate()


def report(ok: bool, current="design", status="block", messages=("missing X",)):
    return {
        "workItem": "issue-1",
        "currentNode": current,
        "ok": ok,
        "nodes": [
            {"node": "requirements", "status": "pass", "messages": []},
            {"node": current, "status": status, "messages": list(messages)},
            {"node": "later", "status": "block", "messages": ["not reached"]},
        ],
    }


def test_the_wrapper_is_stdlib_only_so_it_survives_a_missing_cli():
    """It must not import `the_loop` — it has to run when the CLI is absent."""
    source = GATE.read_text(encoding="utf-8")
    assert "import the_loop" not in source
    assert "from the_loop" not in source


class TestBlockingNode:
    def test_a_satisfied_report_blocks_nothing(self, gate):
        assert gate.blocking_node(report(ok=True)) is None

    def test_only_the_current_node_can_block(self, gate):
        """A node further along is not done yet — that is not a blocker.

        Without this the gate would fire on every turn of every work item
        forever, since there is always a later node that has not run.
        """
        found = gate.blocking_node(report(ok=False))
        assert found is not None and found["node"] == "design"

    def test_a_current_node_that_passes_is_not_a_blocker(self, gate):
        data = report(ok=False, status="pass")
        assert gate.blocking_node(data) is None

    @pytest.mark.parametrize("status", ["pass", "skip"])
    def test_skipped_and_passed_nodes_never_block(self, gate, status):
        assert gate.blocking_node(report(ok=False, status=status)) is None


class TestHarnessProtocols:
    def test_claude_blocks_the_stop_with_stderr(self, gate, capsys):
        code = gate.emit("claude", "please fix")
        captured = capsys.readouterr()
        assert code == 2, "exit 2 is what prevents the stop"
        assert "please fix" in captured.err
        assert captured.out == ""

    def test_cursor_returns_a_followup_message_on_stdout(self, gate, capsys):
        code = gate.emit("cursor", "please fix")
        captured = capsys.readouterr()
        assert code == 0, "Cursor cannot block a stop"
        assert json.loads(captured.out) == {"followup_message": "please fix"}
        assert captured.err == ""


class TestAttemptsFile:
    def test_two_repos_on_the_same_work_item_do_not_share_a_counter(self, gate):
        """The bash version keyed on the work-item id alone.

        Two checkouts working on `issue-1` shared one counter, so each one's
        attempts silently consumed the other's budget.
        """
        a = gate.attempts_path("issue-1", "/repo/a")
        b = gate.attempts_path("issue-1", "/repo/b")
        assert a != b

    def test_the_same_repo_and_item_is_stable_across_calls(self, gate):
        assert gate.attempts_path("issue-1", "/repo/a") == gate.attempts_path(
            "issue-1", "/repo/a"
        )

    def test_a_work_item_with_slashes_does_not_escape_the_temp_dir(self, gate):
        """A ref like `github:o/r#1` must not become a path traversal."""
        path = gate.attempts_path("../../etc/passwd", "/repo")
        assert path.parent == path.resolve().parent
        assert ".." not in path.name

    def test_a_missing_or_corrupt_counter_reads_as_zero(self, gate, tmp_path):
        assert gate.read_attempts(tmp_path / "nope") == 0
        junk = tmp_path / "junk"
        junk.write_text("not a number", encoding="utf-8")
        assert gate.read_attempts(junk) == 0


class TestMain:
    def _run(self, gate, monkeypatch, tmp_path, data, env=None):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("THE_LOOP_WORK_ITEM", "issue-1")
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(gate, "run_check", lambda _: data)
        return gate.main(["gate", "claude"])

    def test_no_work_item_is_a_no_op(self, gate, monkeypatch):
        monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
        assert gate.main(["gate", "claude"]) == 0

    def test_an_unavailable_cli_is_a_no_op_not_an_error(
        self, gate, monkeypatch, tmp_path
    ):
        """A missing `the-loop` must not error on every single turn."""
        assert self._run(gate, monkeypatch, tmp_path, None) == 0

    def test_a_satisfied_node_lets_the_turn_end(self, gate, monkeypatch, tmp_path):
        assert self._run(gate, monkeypatch, tmp_path, report(ok=True)) == 0

    def test_an_unmet_node_blocks_and_carries_the_findings(
        self, gate, monkeypatch, tmp_path, capsys
    ):
        code = self._run(gate, monkeypatch, tmp_path, report(ok=False))
        assert code == 2
        err = capsys.readouterr().err
        assert "missing X" in err
        assert "attempt 1/3" in err

    def test_the_attempt_cap_gives_up_rather_than_wedging_the_session(
        self, gate, monkeypatch, tmp_path, capsys
    ):
        """Claude Code caps nothing, so the-loop caps it here.

        A hook that can wedge a session forever is worse than one that gives up
        loudly — CI is the backstop that still gates the merge.
        """
        data = report(ok=False)
        codes = [
            self._run(
                gate, monkeypatch, tmp_path, data, {"THE_LOOP_GATE_MAX_ATTEMPTS": "2"}
            )
            for _ in range(3)
        ]
        assert codes == [2, 2, 0]
        assert "still incomplete after 2 attempts" in capsys.readouterr().err

    def test_the_counter_resets_once_the_node_is_satisfied(
        self, gate, monkeypatch, tmp_path
    ):
        self._run(gate, monkeypatch, tmp_path, report(ok=False))
        self._run(gate, monkeypatch, tmp_path, report(ok=True))
        # A fresh budget, not a spent one.
        assert self._run(gate, monkeypatch, tmp_path, report(ok=False)) == 2
        counter = gate.attempts_path("issue-1", str(tmp_path))
        assert gate.read_attempts(counter) == 1

    def test_a_nonsense_max_attempts_falls_back_to_the_default(
        self, gate, monkeypatch, tmp_path, capsys
    ):
        self._run(
            gate,
            monkeypatch,
            tmp_path,
            report(ok=False),
            {"THE_LOOP_GATE_MAX_ATTEMPTS": "banana"},
        )
        assert "attempt 1/3" in capsys.readouterr().err

    def test_cursor_is_selected_by_argv(self, gate, monkeypatch, tmp_path, capsys):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("THE_LOOP_WORK_ITEM", "issue-1")
        monkeypatch.setattr(gate, "run_check", lambda _: report(ok=False))
        assert gate.main(["gate", "cursor"]) == 0
        assert "followup_message" in capsys.readouterr().out


def test_the_gate_never_trusts_stored_graph_state(gate, monkeypatch):
    """`--recompute` is mandatory: this is a gate, and state is a cache.

    Two failures ride on this. Trusting the cache means trusting a file the
    agent being gated can write. And a work item whose pointer was never
    advanced sits at the start node reporting `ok`, so the gate would be inert
    no matter how much is unmet downstream.
    """
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd

        class P:
            stdout = "{}"

        return P()

    monkeypatch.setattr(gate.shutil, "which", lambda _: "/usr/bin/the-loop")
    monkeypatch.setattr(gate.subprocess, "run", fake_run)
    gate.run_check("issue-1")
    assert "--recompute" in seen["cmd"]
