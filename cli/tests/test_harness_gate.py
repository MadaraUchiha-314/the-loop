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
import io
import json
import subprocess
import sys
import tempfile
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


def report(ok: bool, current="design", status=None, messages=("missing X",)):
    """A check report. `ok` and the node statuses are kept consistent.

    They cannot disagree in reality, and `blocking_node` reads the per-node
    statuses rather than the `ok` summary — the facts, not the derived field.
    """
    if status is None:
        status = "pass" if ok else "block"
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

    def test_waiting_on_a_human_does_not_block_the_stop(self, gate):
        """`wait` means a review has not come back. Nobody is there to answer.

        Blocking the turn would spin the agent against an absent person — the
        thing the attempt cap exists to contain, not to cause.
        """
        assert gate.blocking_node(report(ok=False, status="wait")) is None

    def test_a_genuine_block_still_blocks(self, gate):
        found = gate.blocking_node(report(ok=False, status="block"))
        assert found is not None and found["node"] == "design"


def walked(pointer, statuses, current=None):
    """A recomputed report with a ``pointer`` (issue-429).

    ``statuses`` is the graph in order, ``(node, status)``. ``currentNode`` is
    what ``--recompute`` puts there — the first node that is not satisfied —
    unless given.
    """
    if current is None:
        current = next(
            (n for n, s in statuses if s not in ("pass", "skip")), statuses[-1][0]
        )
    return {
        "workItem": "issue-1",
        "currentNode": current,
        "ok": False,
        "pointer": pointer,
        "nodes": [
            {"node": n, "status": s, "messages": [f"{n} is {s}"]} for n, s in statuses
        ],
    }


GRAPH = [
    ("phase-selection", "pass"),
    ("brainstorming", "skip"),
    ("requirements-definition", "skip"),
    ("design", "block"),
    ("test-planning", "block"),
]


class TestThePointerBoundsTheGate:
    """The gate never looks past the node the work item is at (issue-429).

    Under ``--recompute`` ``currentNode`` is the first node the artifacts leave
    unmet. That runs ahead of the item whenever the nodes before it pass but the
    item was never advanced into it — and the gate then ordered the agent to
    write an artifact for a phase that had not started, on every turn.
    """

    def test_a_node_the_item_never_entered_does_not_block(self, gate):
        """The ticket's case: parked at phase-selection, told to write design.md."""
        data = walked("phase-selection", GRAPH)
        assert data["currentNode"] == "design", "the recomputed position runs ahead"
        assert gate.blocking_node(data) is None

    def test_a_node_the_item_is_at_still_blocks(self, gate):
        found = gate.blocking_node(walked("design", GRAPH))
        assert found is not None and found["node"] == "design"

    def test_a_broken_node_behind_the_pointer_still_blocks(self, gate):
        """The pointer bounds the gate; it never excuses what it walked past.

        A pointer is agent-writable, so moving it FORWARD must hide nothing: the
        first unmet node at or before it is still the finding.
        """
        found = gate.blocking_node(walked("test-planning", GRAPH))
        assert found is not None and found["node"] == "design"

    def test_a_wait_before_the_pointer_counts_as_passed(self, gate):
        """The P3 regression (issue-551, R3.3): an approved human gate recomputes
        as `wait`, and one behind the pointer used to switch the gate off for
        every node after it."""
        graph = [("phase-selection", "pass"), ("approval", "wait"), ("design", "block")]
        found = gate.blocking_node(walked("design", graph))
        assert found is not None and found["node"] == "design"

    def test_a_block_before_the_pointer_blocks_past_a_wait_too(self, gate):
        """issue-429's rule is kept (R3.4): the broken node is the one named."""
        graph = [("approval", "wait"), ("design", "block"), ("tasks", "block")]
        found = gate.blocking_node(walked("tasks", graph))
        assert found is not None and found["node"] == "design"

    def test_a_wait_at_the_pointer_lets_the_turn_end(self, gate):
        graph = [("phase-selection", "pass"), ("approval", "wait"), ("design", "block")]
        assert gate.blocking_node(walked("approval", graph)) is None

    def test_an_unknown_status_before_the_pointer_is_inconclusive(self, gate):
        graph = [("phase-selection", "error"), ("design", "block")]
        assert gate.blocking_node(walked("design", graph)) is None

    def test_a_cli_without_a_pointer_is_bounded_by_the_current_node(self, gate):
        """An older CLI: `currentNode` is the only position there is."""
        data = walked("design", GRAPH)
        del data["pointer"]
        found = gate.blocking_node(data)
        assert found is not None and found["node"] == "design"
        data["nodes"][3]["status"] = "wait"
        assert gate.blocking_node(data) is None

    def test_a_satisfied_walk_up_to_the_pointer_blocks_nothing(self, gate):
        graph = [("phase-selection", "pass"), ("design", "pass"), ("later", "block")]
        assert gate.blocking_node(walked("design", graph)) is None

    @pytest.mark.parametrize("pointer", ["", None])
    def test_no_recorded_position_is_inconclusive(self, gate, pointer):
        """No state file was found: the gate cannot tell where the item is.

        It lets the turn end rather than inventing a requirement.
        """
        assert gate.blocking_node(walked(pointer, GRAPH)) is None

    def test_a_pointer_naming_no_node_in_the_report_is_inconclusive(self, gate):
        """Not "walk every node": that would reach the downstream blocks."""
        assert gate.blocking_node(walked("no-such-node", GRAPH)) is None

    @pytest.mark.parametrize("current", ["", None, "no-such-node"])
    def test_an_unresolved_current_node_is_inconclusive(self, gate, current):
        """`currentNode: null` must not surface an arbitrary downstream block."""
        data = walked("design", GRAPH, current=current)
        data["currentNode"] = current
        assert gate.blocking_node(data) is None
        del data["pointer"]  # and not on a CLI that predates the pointer either
        assert gate.blocking_node(data) is None

    def test_an_unread_repository_is_inconclusive(self, gate):
        """issue-238's position-unknown answer: no nodes, no pointer."""
        data = {
            "workItem": "issue-1",
            "currentNode": "",
            "ok": False,
            "parked": None,
            "nodes": [],
            "repoResolved": False,
        }
        assert gate.blocking_node(data) is None


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


class TestFeedbackText:
    """The words come from `hooks/prompts/gate-feedback.md` (issue-540)."""

    def test_the_rendered_text_is_pinned(self, gate):
        node = {"messages": ["design.md missing", "a {brace} $x"]}
        assert gate.feedback_text(node, 1, 3) == (
            "the-loop: this step is not complete.\n"
            "  · design.md missing\n"
            "  · a {brace} $x\n"
            "\n"
            "Fix the above, then finish. (attempt 1/3)"
        )

    def test_a_node_without_messages_still_says_why_it_stops(self, gate):
        assert gate.feedback_text({"messages": None}, 2, 5) == (
            "the-loop: this step is not complete.\n"
            "\n"
            "Fix the above, then finish. (attempt 2/5)"
        )

    def test_the_prompt_file_ships_beside_the_script(self, gate):
        assert gate.FEEDBACK_PROMPT == GATE.parent / "prompts" / "gate-feedback.md"
        assert gate.FEEDBACK_PROMPT.is_file()

    def test_a_missing_prompt_file_still_blocks_with_the_checks_own_messages(
        self, gate, monkeypatch, tmp_path, capsys
    ):
        """A broken install must neither crash a stop nor switch the gate off."""
        monkeypatch.setattr(gate, "FEEDBACK_PROMPT", tmp_path / "absent.md")
        assert gate.feedback_text({"messages": ["missing X"]}, 1, 3) == "missing X"
        assert gate.feedback_text({"messages": []}, 1, 3) == "the-loop check: unmet"
        assert gate.give_up_text("issue-1", 3) == ""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("THE_LOOP_WORK_ITEM", "issue-1")
        monkeypatch.setattr(gate, "ask_service", lambda *a, **k: None)
        monkeypatch.setattr(gate, "run_check", lambda *_: report(ok=False))
        gate.main(["gate", "codex"])
        out = capsys.readouterr().out
        assert json.loads(out) == {"decision": "block", "reason": "missing X"}

    def test_the_give_up_line_is_pinned(self, gate):
        assert gate.give_up_text("issue-1", 3) == (
            "the-loop: issue-1 is still incomplete after 3 attempts; letting the "
            "turn end. `the-loop check` will still report it, and CI gates the merge."
        )


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

    @pytest.mark.parametrize(
        "work_item", ["../../etc/passwd", "github:o/r#1", "/etc/passwd", "a/../../b"]
    )
    def test_a_work_item_with_slashes_does_not_escape_the_temp_dir(
        self, gate, work_item
    ):
        """A ref like `github:o/r#1` must not become a path traversal.

        Both sides are compared canonically (issue-454): on macOS the temp dir is
        `/var/…`, an alias of `/private/var/…`, so a resolved path never equals an
        unresolved one even when nothing escaped.
        """
        path = gate.attempts_path(work_item, "/repo")
        assert path.parent == Path(tempfile.gettempdir())
        assert path.resolve().parent == Path(tempfile.gettempdir()).resolve()
        assert ".." not in path.name and "/" not in path.name

    def test_containment_holds_when_the_temp_dir_is_a_symlink(
        self, gate, tmp_path, monkeypatch
    ):
        """macOS's `/var` → `/private/var`, recreated on any POSIX host (issue-454)."""
        real = tmp_path / "private-tmp"
        real.mkdir()
        alias = tmp_path / "tmp-alias"
        alias.symlink_to(real, target_is_directory=True)
        monkeypatch.setattr(tempfile, "tempdir", str(alias))

        path = gate.attempts_path("../../etc/passwd", "/repo")
        # The alias is really in play: comparing a resolved parent with an
        # unresolved one — the old assertion — would report an escape here.
        assert path.parent != path.resolve().parent
        assert path.parent == alias
        assert path.resolve().parent == real.resolve()

    def test_a_missing_or_corrupt_counter_reads_as_zero(self, gate, tmp_path):
        assert gate.read_attempts(tmp_path / "nope") == 0
        junk = tmp_path / "junk"
        junk.write_text("not a number", encoding="utf-8")
        assert gate.read_attempts(junk) == 0


class TestMain:
    """The fallback path (issue-551): the service does not answer, so the gate
    judges `the-loop check` itself, as it did before there was a service."""

    def _run(self, gate, monkeypatch, tmp_path, data, env=None):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("THE_LOOP_WORK_ITEM", "issue-1")
        for key, value in (env or {}).items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(gate, "ask_service", lambda *a, **k: None)
        monkeypatch.setattr(gate, "run_check", lambda *_: data)
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
        monkeypatch.setattr(gate, "ask_service", lambda *a, **k: None)
        monkeypatch.setattr(gate, "run_check", lambda *_: report(ok=False))
        assert gate.main(["gate", "cursor"]) == 0
        assert "followup_message" in capsys.readouterr().out


def test_the_gate_never_trusts_stored_graph_state(gate, monkeypatch):
    """`--recompute` is mandatory: this is a gate, and state is a cache.

    The state file is one the agent being gated can write. The gate takes only
    *where* the item is from it — the `pointer` that bounds which nodes it asks
    about (issue-429) — and walks up to it from the start of the graph, so a
    pointer moved forward still finds a broken node behind it.
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


# -- issue-551: the gate asks the service -----------------------------------------

GATE_REF = "github:octo/repo#7"
REFUSAL = {
    "workItem": GATE_REF,
    "verdict": "refuse",
    "reason": "work-owed",
    "node": "design",
    "nodeStatus": "block",
    "messages": ["design.md missing"],
    "command": "/the-loop:create-design issue-7",
    "text": "the-loop: do not end this turn. Node `design` still owes work:",
}
ALLOWED = {"workItem": GATE_REF, "verdict": "allow", "reason": "exit-met"}
#: The P3 shape as `the-loop check` reports it: an approved gate behind the pointer.
PAST_A_GATE = [("requirements-approval", "wait"), ("design", "block")]


class FakeCli:
    """A `the-loop` on PATH: it records each run and answers by verb."""

    def __init__(self, stop_check, check=None):
        self.stop_check = stop_check
        self.check = check
        self.calls = []

    def verbs(self):
        return ["gave-up" if "--gave-up" in argv else argv[1] for argv, _ in self.calls]

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[1] == "check":
            return subprocess.CompletedProcess(argv, 0, json.dumps(self.check), "")
        answer = ALLOWED if "--gave-up" in argv else self.stop_check
        if isinstance(answer, list):
            # One answer per call, in order; the last one repeats.
            answer = answer.pop(0) if len(answer) > 1 else answer[0]
        if isinstance(answer, BaseException):
            raise answer
        if isinstance(answer, subprocess.CompletedProcess):
            return answer
        return subprocess.CompletedProcess(argv, 0, json.dumps(answer), "")


def failed(code, stdout="", stderr=""):
    return subprocess.CompletedProcess(["the-loop"], code, stdout, stderr)


class TestTheGateAsksTheService:
    """`the-loop sessions stop-check` decides; the hook keeps the attempt cap."""

    @pytest.fixture
    def run(self, gate, monkeypatch, tmp_path):
        def run(cli, harness="claude", maximum="3", payload="{}"):
            monkeypatch.chdir(tmp_path)
            monkeypatch.setenv("THE_LOOP_WORK_ITEM", GATE_REF)
            monkeypatch.setenv("THE_LOOP_GATE_MAX_ATTEMPTS", maximum)
            monkeypatch.setattr(gate.shutil, "which", lambda name: f"/bin/{name}")
            monkeypatch.setattr(gate.subprocess, "run", cli.run)
            monkeypatch.setattr(gate.sys, "stdin", io.StringIO(payload))
            return gate.main(["gate", harness])

        return run

    def counter(self, gate, tmp_path):
        return gate.attempts_path(GATE_REF, str(tmp_path))

    def test_an_allowed_stop_goes_through_and_resets_the_counter(
        self, gate, run, tmp_path, capsys
    ):
        self.counter(gate, tmp_path).write_text("2")
        cli = FakeCli(ALLOWED)
        assert run(cli, payload='{"background_tasks": []}') == 0
        ((argv, kwargs),) = cli.calls
        assert argv == ["the-loop", "sessions", "stop-check", "--work-item", GATE_REF]
        assert kwargs["input"] == '{"background_tasks": []}'
        assert 0 < kwargs["timeout"] <= 30
        assert not self.counter(gate, tmp_path).exists()
        captured = capsys.readouterr()
        assert (captured.out, captured.err) == ("", "")

    def test_an_allowed_stop_answers_codex_with_empty_json(self, run, capsys):
        assert run(FakeCli(ALLOWED), harness="codex") == 0
        assert json.loads(capsys.readouterr().out) == {}

    def test_a_refusal_blocks_claude_with_the_services_text(
        self, gate, run, tmp_path, capsys
    ):
        cli = FakeCli(REFUSAL)
        assert run(cli) == 2
        err = capsys.readouterr().err
        assert err == REFUSAL["text"] + "\n(attempt 1/3)\n"
        assert gate.read_attempts(self.counter(gate, tmp_path)) == 1
        assert cli.verbs() == ["sessions"], "the service judged; `check` is not run"

    def test_a_refusal_blocks_codex_with_the_services_text(self, run, capsys):
        assert run(FakeCli(REFUSAL), harness="codex") == 0
        assert json.loads(capsys.readouterr().out) == {
            "decision": "block",
            "reason": REFUSAL["text"] + "\n(attempt 1/3)",
        }

    def test_a_refusal_hands_cursor_a_followup_message(self, run, capsys):
        assert run(FakeCli(REFUSAL), harness="cursor") == 0
        assert json.loads(capsys.readouterr().out) == {
            "followup_message": REFUSAL["text"] + "\n(attempt 1/3)"
        }

    def test_a_refusal_without_text_is_worded_from_its_messages(self, run, capsys):
        answer = {k: v for k, v in REFUSAL.items() if k != "text"}
        assert run(FakeCli(answer)) == 2
        assert capsys.readouterr().err == (
            "the-loop: this step is not complete.\n"
            "  · design.md missing\n"
            "\n"
            "Fix the above, then finish. (attempt 1/3)\n"
        )

    def test_abuse_a_service_refusing_forever_is_capped_and_the_give_up_reported(
        self, gate, run, tmp_path, capsys
    ):
        """Abuse case 7 (issue-551, R3.6): the stop is allowed after the cap, and
        the service is told, so the record says `gate-gave-up`."""
        cli = FakeCli(REFUSAL)
        codes = [run(cli, maximum="2") for _ in range(3)]
        assert codes == [2, 2, 0]
        assert cli.verbs() == ["sessions", "sessions", "sessions", "gave-up"]
        argv, kwargs = cli.calls[-1]
        assert argv == [
            "the-loop",
            "sessions",
            "stop-check",
            "--work-item",
            GATE_REF,
            "--gave-up",
        ]
        assert 0 < kwargs["timeout"] <= 30
        assert "still incomplete after 2 attempts" in capsys.readouterr().err
        assert not self.counter(gate, tmp_path).exists()

    def test_a_give_up_that_cannot_be_reported_still_lets_the_turn_end(
        self, gate, run, monkeypatch
    ):
        cli = FakeCli(REFUSAL)
        assert run(cli, maximum="1") == 2

        def fail(argv, **kwargs):
            if "--gave-up" in argv:
                raise subprocess.TimeoutExpired(argv, 10)
            return cli.run(argv, **kwargs)

        monkeypatch.setattr(gate.subprocess, "run", fail)
        assert gate.main(["gate", "claude"]) == 0

    @pytest.mark.parametrize(
        "silent",
        [
            failed(2, stderr="the-loop sessions: invalid choice: 'stop-check'"),
            failed(2, stderr="the-loop: the service is not running"),
            failed(1, stderr="the-loop sessions: no live session"),
            failed(1, stdout=json.dumps(REFUSAL)),
            failed(0, stdout="not json"),
            failed(0, stdout=""),
            failed(0, stdout='["allow"]'),
            failed(0, stdout='{"verdict": "maybe"}'),
            subprocess.TimeoutExpired("the-loop", 20),
            OSError("gone"),
        ],
        ids=[
            "verb-missing",
            "service-down",
            "unknown-ref",
            "failed-with-json",
            "garbage",
            "nothing",
            "not-an-object",
            "unknown-verdict",
            "timeout",
            "cannot-run",
        ],
    )
    def test_a_service_that_does_not_answer_falls_back_to_check(
        self, gate, run, tmp_path, capsys, silent
    ):
        """Version skew (issue-551): the plugin and the CLI ship separately. The
        fallback applies the P3 fix itself and blocks on the pointer's node."""
        cli = FakeCli(silent, check=walked("design", PAST_A_GATE))
        assert run(cli) == 2
        assert cli.verbs() == ["sessions", "check"]
        assert cli.calls[1][0] == [
            "the-loop",
            "check",
            GATE_REF,
            "--format",
            "json",
            "--recompute",
        ]
        err = capsys.readouterr().err
        assert "design is block" in err and "attempt 1/3" in err

    def test_the_fallback_lets_a_satisfied_item_stop(self, run):
        graph = [("requirements-approval", "wait"), ("design", "pass")]
        cli = FakeCli(failed(2), check=walked("design", graph))
        assert run(cli) == 0

    SATISFIED = [("requirements-approval", "wait"), ("design", "pass")]

    def test_a_fallback_that_allows_asks_the_service_once_more(
        self, gate, run, tmp_path, capsys
    ):
        """Requirement: R4.5, R4.6 — the service was down for a moment. Nothing
        recorded this turn's end, and the session would read as working for
        ever. One more try: when it answers, it records the end."""
        self.counter(gate, tmp_path).write_text("1")
        cli = FakeCli([failed(2), ALLOWED], check=walked("design", self.SATISFIED))
        assert run(cli, payload='{"background_tasks": []}') == 0
        assert cli.verbs() == ["sessions", "check", "sessions"]
        stop_checks = [(a, k) for a, k in cli.calls if a[1] == "sessions"]
        assert len(stop_checks) == 2
        assert all("--gave-up" not in argv for argv, _ in stop_checks)
        assert stop_checks[1][1]["input"] == '{"background_tasks": []}'
        assert 0 < stop_checks[1][1]["timeout"] <= 5
        assert not self.counter(gate, tmp_path).exists()
        assert capsys.readouterr().err == ""

    def test_the_second_answer_is_the_verdict_when_it_refuses(self, run, capsys):
        """The fallback knows of no ask and no wait; the service does."""
        cli = FakeCli([failed(2), REFUSAL], check=walked("design", self.SATISFIED))
        assert run(cli) == 2
        assert capsys.readouterr().err == REFUSAL["text"] + "\n(attempt 1/3)\n"

    def test_a_service_still_down_lets_the_fallbacks_allow_stand(self, run):
        cli = FakeCli(failed(2), check=walked("design", self.SATISFIED))
        assert run(cli) == 0
        assert cli.verbs() == ["sessions", "check", "sessions"]
        cli = FakeCli(failed(2), check=None)
        assert run(cli, harness="codex") == 0

    def test_a_fallback_that_blocks_does_not_ask_again(self, run):
        cli = FakeCli([failed(2), ALLOWED], check=walked("design", PAST_A_GATE))
        assert run(cli) == 2
        assert cli.verbs() == ["sessions", "check"]

    def test_the_hook_stays_inside_the_harness_minute(self, gate, run, monkeypatch):
        """Every call times out, and the clock runs as if each used its whole
        timeout: the timeouts handed out sum to no more than the budget."""
        clock = [1000.0]
        monkeypatch.setattr(gate.time, "monotonic", lambda: clock[0])
        given = []

        def slow(argv, **kwargs):
            given.append(kwargs["timeout"])
            clock[0] += kwargs["timeout"]
            if argv[1] == "check":
                return subprocess.CompletedProcess(
                    argv, 0, json.dumps(walked("design", self.SATISFIED)), ""
                )
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

        cli = FakeCli(ALLOWED)
        cli.run = slow
        assert run(cli) == 0
        assert len(given) == 3 and sum(given) <= gate.HOOK_BUDGET_SECONDS <= 55

    def test_the_fallback_gives_up_without_recording_anything(self, run, capsys):
        """It knows nothing of the service, so it reports nothing to it."""
        cli = FakeCli(failed(2), check=walked("design", PAST_A_GATE))
        codes = [run(cli, maximum="1") for _ in range(2)]
        assert codes == [2, 0]
        assert "gave-up" not in cli.verbs()
        assert "still incomplete after 1 attempts" in capsys.readouterr().err

    def test_a_work_item_shaped_like_a_flag_is_never_sent_to_the_service(
        self, gate, monkeypatch
    ):
        calls = []
        monkeypatch.setattr(gate.shutil, "which", lambda name: f"/bin/{name}")
        monkeypatch.setattr(gate.subprocess, "run", lambda *a, **k: calls.append(a))
        assert gate.ask_service("--gave-up", "") is None
        assert calls == []


class TestThePayloadIsReadOnce:
    def test_a_terminal_is_never_read(self, gate, monkeypatch):
        class Terminal(io.StringIO):
            def isatty(self):
                return True

            def read(self, *args):
                raise AssertionError("read a terminal")

        monkeypatch.setattr(gate.sys, "stdin", Terminal())
        assert gate.read_payload() == ""

    def test_a_closed_or_unreadable_stdin_is_an_empty_payload(self, gate, monkeypatch):
        class Broken(io.StringIO):
            def read(self, *args):
                raise OSError("closed")

        monkeypatch.setattr(gate.sys, "stdin", Broken())
        assert gate.read_payload() == ""
        monkeypatch.setattr(gate.sys, "stdin", None)
        assert gate.read_payload() == ""

    def test_a_pipe_nobody_writes_to_does_not_hold_the_stop(self, tmp_path):
        """The script as a harness runs it, with stdin left open and silent."""
        empty = tmp_path / "empty-bin"
        empty.mkdir()
        proc = subprocess.Popen(
            [sys.executable, str(GATE), "codex"],
            env={"PATH": str(empty), "THE_LOOP_WORK_ITEM": GATE_REF},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.wait(timeout=20) == 0
            assert proc.stdout is not None
            assert json.loads(proc.stdout.read()) == {}
        finally:
            proc.kill()
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None:
                    stream.close()


# -- issue-551: the turn-start hook ------------------------------------------------

HOOKS_DIR = GATE.parent
TURN_START = HOOKS_DIR / "the-loop-turn-start.py"
REF = "github:octo/repo#7"


@pytest.fixture
def turn_start():
    spec = importlib.util.spec_from_file_location("the_loop_turn_start", TURN_START)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli_calls(turn_start, monkeypatch):
    """A `the-loop` that is on PATH and records how it was run."""
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))

    monkeypatch.setattr(turn_start.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(turn_start.subprocess, "run", run)
    return calls


def _run_hook_process(tmp_path, harness, work_item=REF):
    """The script as a harness runs it, with no `the-loop` anywhere on PATH."""
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    env = {"PATH": str(empty)}
    if work_item:
        env["THE_LOOP_WORK_ITEM"] = work_item
    return subprocess.run(
        [sys.executable, str(TURN_START), harness],
        env=env,
        input='{"hook_event_name": "UserPromptSubmit", "prompt": "go on"}',
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_the_turn_start_hook_is_stdlib_only():
    source = TURN_START.read_text(encoding="utf-8")
    assert "import the_loop" not in source
    assert "from the_loop" not in source


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_turn_start_without_cli_is_a_silent_no_op(tmp_path, harness):
    """No CLI on PATH: exit 0 and not one byte, or the harness would read it as
    context for the prompt."""
    proc = _run_hook_process(tmp_path, harness)
    assert (proc.returncode, proc.stdout, proc.stderr) == (0, "", "")


def test_turn_start_without_cli_still_lets_cursor_submit(tmp_path):
    proc = _run_hook_process(tmp_path, "cursor")
    assert proc.returncode == 0 and proc.stderr == ""
    assert json.loads(proc.stdout) == {"continue": True}


def test_turn_start_without_a_work_item_runs_nothing(
    turn_start, cli_calls, monkeypatch, capsys
):
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    assert turn_start.main(["hook", "claude"]) == 0
    assert cli_calls == [] and capsys.readouterr().out == ""


def test_turn_start_runs_the_verb_for_the_sessions_work_item(
    turn_start, cli_calls, monkeypatch, capsys
):
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    assert turn_start.main(["hook", "claude"]) == 0
    ((argv, kwargs),) = cli_calls
    assert argv == ["the-loop", "sessions", "turn-start", "--work-item", REF]
    assert 0 < kwargs["timeout"] <= 10
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


@pytest.mark.parametrize(
    "failure",
    [OSError("gone"), subprocess.TimeoutExpired("the-loop", 10), RuntimeError("x")],
)
def test_turn_start_survives_a_failing_cli(turn_start, monkeypatch, capsys, failure):
    def fail(argv, **kwargs):
        raise failure

    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    monkeypatch.setattr(turn_start.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(turn_start.subprocess, "run", fail)
    assert turn_start.main(["hook", "codex"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_turn_start_never_passes_a_flag_as_the_work_item(
    turn_start, cli_calls, monkeypatch
):
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", "--registry-dir=/tmp/x")
    assert turn_start.main(["hook", "claude"]) == 0
    assert cli_calls == []


@pytest.mark.parametrize(
    "manifest, event, harness",
    [
        ("hooks/hooks.json", "UserPromptSubmit", "claude"),
        ("hooks/codex-hooks.json", "UserPromptSubmit", "codex"),
        (".cursor/hooks.json", "beforeSubmitPrompt", "cursor"),
    ],
)
def test_every_harness_manifest_declares_the_turn_start_hook(manifest, event, harness):
    """A hook nothing wires up is a file, not a record of a turn."""
    entries = json.loads((HOOKS_DIR.parent / manifest).read_text())["hooks"][event]
    commands = [
        hook["command"] for entry in entries for hook in (entry.get("hooks") or [entry])
    ]
    assert any(
        command.endswith(f'the-loop-turn-start.py" {harness}') for command in commands
    )
    assert TURN_START.exists()
