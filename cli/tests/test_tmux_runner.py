"""Unit tests for the tmux runner (issue-32).

Covers the pieces the integration file wires together: registry runner fields,
per-adapter interactive argv, TmuxRunner command construction, routing config
parsing, dependency preflight, and the sessions CLI helpers.

Spec: docs/specs/issue-32/design.md.
"""

import os
import signal

import pytest

from the_loop import runner as runner_mod
from the_loop.commands import sessions_cmd
from the_loop.harness import ClaudeCodeAdapter, CursorAgentAdapter
from the_loop.runner import (
    TmuxResult,
    TmuxRunner,
    UnsupportedRunnerError,
    check_dependencies,
    start_web_terminal,
    stop_web_terminal,
    web_terminal_argv,
)
from the_loop.sessions import Session, WorkItemRef
from the_loop.webhook.dispatcher import RoutingConfig, TmuxConfig

REF = "github:octo/repo#15"


def make_session(**overrides) -> Session:
    session = Session(
        work_item=WorkItemRef.parse(REF),
        harness="claude",
        harness_session_id="abc-123",
        cwd="/work",
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class FakeRun:
    """Capture subprocess.run calls inside the runner module.

    ``per_verb`` overrides the exit code for specific tmux sub-commands
    (e.g. ``{"has-session": 1}`` = "no such session"); ``stdout_per_verb``
    does the same for stdout (e.g. ``list-panes`` pane-dead flags).
    """

    def __init__(self, returncode=0, per_verb=None, stdout_per_verb=None):
        self.calls = []
        self.returncode = returncode
        self.per_verb = per_verb or {}
        self.stdout_per_verb = stdout_per_verb or {}

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        rc = self.per_verb.get(cmd[1], self.returncode)
        out = self.stdout_per_verb.get(cmd[1], "")

        class Proc:
            returncode = rc
            stdout = out
            stderr = ""

        return Proc()

    @property
    def verbs(self):
        return [call[1] for call in self.calls]


class TestSessionRunnerFields:
    def test_defaults_to_process_runner(self):
        session = make_session()
        assert session.runner == "process"
        assert session.tmux_target == ""

    def test_round_trips_runner_fields(self):
        session = make_session(runner="tmux", tmux_target="loop-github-octo-repo-15")
        data = session.to_dict()
        assert data["runner"] == "tmux"
        assert data["tmuxTarget"] == "loop-github-octo-repo-15"
        restored = Session.from_dict(data)
        assert restored.runner == "tmux"
        assert restored.tmux_target == "loop-github-octo-repo-15"

    def test_reads_pre_issue32_registry_files(self):
        data = make_session().to_dict()
        del (
            data["runner"],
            data["tmuxTarget"],
        )  # a registry file written before issue-32
        restored = Session.from_dict(data)
        assert restored.runner == "process"
        assert restored.tmux_target == ""


class TestInteractiveArgv:
    def test_claude_uses_preassigned_session_id(self):
        argv = ClaudeCodeAdapter().interactive_argv("do the thing", "uuid-1")
        assert argv == ["--session-id", "uuid-1", "do the thing"]

    def test_claude_puts_extra_args_before_the_positional_prompt(self):
        adapter = ClaudeCodeAdapter(extra_args=["--permission-mode", "acceptEdits"])
        argv = adapter.interactive_argv("p", "id")
        assert argv == ["--session-id", "id", "--permission-mode", "acceptEdits", "p"]

    def test_cursor_is_unsupported(self):
        with pytest.raises(UnsupportedRunnerError):
            CursorAgentAdapter().interactive_argv("p", "id")


class TestInteractiveResumeArgv:
    """Respawning a dead session continues its conversation (issue-89)."""

    def test_claude_resumes_the_recorded_session_id(self):
        argv = ClaudeCodeAdapter().interactive_resume_argv("do the thing", "uuid-1")
        assert argv == ["--resume", "uuid-1", "do the thing"]

    def test_claude_puts_extra_args_before_the_positional_prompt(self):
        adapter = ClaudeCodeAdapter(extra_args=["--permission-mode", "acceptEdits"])
        argv = adapter.interactive_resume_argv("p", "id")
        assert argv == ["--resume", "id", "--permission-mode", "acceptEdits", "p"]

    def test_cursor_cannot_resume_interactively(self):
        # cursor-agent cannot be tmux-hosted at all, so there is no interactive
        # conversation to resume — the dispatcher reads this as "spawn fresh".
        with pytest.raises(UnsupportedRunnerError):
            CursorAgentAdapter().interactive_resume_argv("p", "id")


class TestTmuxRunner:
    def test_target_is_slug_derived(self):
        target = TmuxRunner().target_for(WorkItemRef.parse(REF))
        assert target == "loop-github-octo-repo-15"

    def test_spawn_builds_detached_session_with_interactive_argv(self, monkeypatch):
        fake = FakeRun(per_verb={"has-session": 1})  # no stale session
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="start work",
            cwd="/work",
            session_id="uuid-1",
        )
        assert result.ok, result.error
        cmd = next(c for c in fake.calls if c[1] == "new-session")
        assert cmd[:2] == ["tmux", "new-session"]
        assert "-d" in cmd
        assert cmd[cmd.index("-s") + 1] == "loop-github-octo-repo-15"
        assert cmd[cmd.index("-c") + 1] == "/work"
        tail = cmd[cmd.index("--") + 1 :]
        assert tail == ["claude", "--session-id", "uuid-1", "start work"]

    def test_spawn_clears_a_stale_session_with_the_same_name(self, monkeypatch):
        fake = FakeRun()  # has-session exits 0: a stale leftover exists
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )
        assert result.ok, result.error
        assert fake.verbs == [
            "has-session",
            "kill-session",
            "new-session",
            "set-option",  # remain-on-exit (issue-86)
        ]

    def test_spawn_fails_without_tmux(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd=".",
            session_id="id",
        )
        assert not result.ok
        assert "tmux" in result.error

    def test_deliver_pastes_with_bracketed_paste_then_enter(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-github-octo-repo-15")
        result = TmuxRunner().deliver(session, "event prompt")
        assert result.ok, result.error
        # liveness (has-session + list-panes), then load-buffer, paste-buffer
        # -p, send-keys Enter — in order.
        assert fake.verbs == [
            "has-session",
            "list-panes",
            "load-buffer",
            "paste-buffer",
            "send-keys",
        ]
        paste = fake.calls[3]
        assert "-p" in paste
        assert paste[paste.index("-t") + 1] == "loop-github-octo-repo-15"
        assert fake.calls[4][-1] == "Enter"

    def test_deliver_fails_when_session_is_gone(self, monkeypatch):
        fake = FakeRun(returncode=1)  # has-session exits non-zero
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-gone")
        result = TmuxRunner().deliver(session, "event prompt")
        assert not result.ok
        assert "loop-gone" in result.error
        # The dispatcher keys respawn on this flag (issue-80): a missing session
        # is the terminal fault it recovers from.
        assert result.session_missing is True

    def test_spawn_sets_remain_on_exit(self, monkeypatch):
        fake = FakeRun(per_verb={"has-session": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )
        opt = next(c for c in fake.calls if c[1] == "set-option")
        assert opt[opt.index("-t") + 1] == "loop-github-octo-repo-15"
        # remain-on-exit is a *window* option in tmux >= 3.0.
        assert "-w" in opt
        assert opt[-2:] == ["remain-on-exit", "on"]

    def test_spawn_skips_remain_on_exit_when_disabled(self, monkeypatch):
        fake = FakeRun(per_verb={"has-session": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        TmuxRunner(remain_on_exit=False).spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )
        assert "set-option" not in fake.verbs

    def test_spawn_survives_a_tmux_that_rejects_remain_on_exit(self, monkeypatch):
        # An older tmux may refuse the option — the session is usable anyway.
        fake = FakeRun(per_verb={"has-session": 1, "set-option": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )
        assert result.ok, result.error

    def test_deliver_paste_failure_is_not_session_missing(self, monkeypatch):
        # has-session succeeds (session is alive) but a paste sub-command errors:
        # NOT a missing-session case, so the dispatcher must not respawn.
        fake = FakeRun(per_verb={"paste-buffer": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-alive")
        result = TmuxRunner().deliver(session, "event prompt")
        assert not result.ok
        assert result.session_missing is False

    def test_deliver_treats_a_dead_pane_as_a_missing_session(self, monkeypatch):
        # With remain-on-exit the session outlives its harness (issue-86), so
        # has-session alone is no longer proof there is anything to talk to —
        # a dead pane must take the issue-80 respawn path, not swallow events.
        fake = FakeRun(stdout_per_verb={"list-panes": "1\n"})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-retained")
        result = TmuxRunner().deliver(session, "event prompt")
        assert not result.ok
        assert result.session_missing is True
        assert "paste-buffer" not in fake.verbs

    def test_spawn_with_resume_continues_the_recorded_conversation(self, monkeypatch):
        fake = FakeRun(per_verb={"has-session": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="event prompt",
            cwd="/work",
            session_id="uuid-1",
            resume=True,
        )
        assert result.ok, result.error
        cmd = next(c for c in fake.calls if c[1] == "new-session")
        tail = cmd[cmd.index("--") + 1 :]
        assert tail == ["claude", "--resume", "uuid-1", "event prompt"]

    def test_spawn_with_resume_fails_for_a_harness_that_cannot_resume(
        self, monkeypatch
    ):
        fake = FakeRun(per_verb={"has-session": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=CursorAgentAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
            resume=True,
        )
        assert not result.ok
        assert "resume" in result.error
        assert "new-session" not in fake.verbs

    def test_kill_targets_the_session(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-x")
        assert TmuxRunner().kill(session).ok
        (cmd,) = fake.calls
        assert cmd[1] == "kill-session"
        assert cmd[cmd.index("-t") + 1] == "loop-x"


class TestPaneLiveness:
    """``has_live_session`` — "the session exists" vs "its harness is running"."""

    @staticmethod
    def _runner(monkeypatch, **kwargs):
        fake = FakeRun(**kwargs)
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        return TmuxRunner(), fake

    def test_live_pane(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "0\n"})
        assert runner.has_live_session("loop-x") is True

    def test_dead_pane(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "1\n"})
        assert runner.has_live_session("loop-x") is False

    def test_one_live_pane_among_dead_ones_counts_as_live(self, monkeypatch):
        runner, _ = self._runner(
            monkeypatch, stdout_per_verb={"list-panes": "1\n0\n1\n"}
        )
        assert runner.has_live_session("loop-x") is True

    def test_missing_session_is_not_live(self, monkeypatch):
        runner, fake = self._runner(monkeypatch, per_verb={"has-session": 1})
        assert runner.has_live_session("loop-x") is False
        assert "list-panes" not in fake.verbs

    def test_unreadable_output_degrades_to_live(self, monkeypatch):
        # A tmux too old to know #{pane_dead}: never declare a healthy session
        # dead — fall back to the pre-issue-86 has-session behaviour.
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "  \n"})
        assert runner.has_live_session("loop-x") is True

    def test_failing_list_panes_degrades_to_live(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, per_verb={"list-panes": 1})
        assert runner.has_live_session("loop-x") is True


class TestSurvivedProbe:
    """``survived`` — did the harness we just started stay up? (issue-89)"""

    @staticmethod
    def _runner(monkeypatch, **kwargs):
        fake = FakeRun(**kwargs)
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        return TmuxRunner(), fake

    def test_live_pane_after_the_grace_period(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "0\n"})
        slept = []
        assert runner.survived("loop-x", 2.0, sleeper=slept.append) is True
        assert slept == [2.0]

    def test_dead_pane_means_the_harness_refused_to_start(self, monkeypatch):
        # What `claude --resume <unknown-id>` looks like: tmux started, the
        # harness exited 1 immediately.
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "1\n"})
        assert runner.survived("loop-x", 2.0, sleeper=lambda _: None) is False

    def test_missing_session_did_not_survive(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, per_verb={"has-session": 1})
        assert runner.survived("loop-x", 0, sleeper=lambda _: None) is False

    def test_zero_delay_does_not_wait(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "0\n"})
        slept = []
        assert runner.survived("loop-x", 0, sleeper=slept.append) is True
        assert slept == []


class FakeTmuxServer:
    """A one-session tmux double whose pane dies when it is signalled.

    Enough shape for ``terminate_harness``: ``has-session`` answers existence,
    ``list-panes`` answers the requested format (``#{pane_pid} #{pane_dead}``
    or just ``#{pane_dead}``), and ``killer`` records signals, marking the pane
    dead when the signal it is configured to obey arrives (issue-94).
    """

    def __init__(
        self,
        pids=(4242,),
        exists=True,
        alive=True,
        dies_on: "signal.Signals | None" = signal.SIGTERM,
    ):
        self.pids = list(pids)
        self.exists = exists
        self.alive = alive
        self.dies_on = dies_on
        self.calls = []
        self.signals = []

    def run(self, cmd, **kwargs):
        import subprocess

        argv = list(cmd[1:])
        self.calls.append(argv)
        if argv[0] == "has-session":
            return subprocess.CompletedProcess(cmd, 0 if self.exists else 1, "", "")
        if argv[0] == "list-panes":
            flag = "0" if self.alive else "1"
            with_pid = "pane_pid" in argv[-1]
            out = "".join(
                f"{pid} {flag}\n" if with_pid else f"{flag}\n" for pid in self.pids
            )
            return subprocess.CompletedProcess(cmd, 0, out, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    def killer(self, pid, sig):
        self.signals.append((pid, sig))
        if sig == self.dies_on:
            self.alive = False

    @property
    def verbs(self):
        return [argv[0] for argv in self.calls]


class TestTerminateHarness:
    """``terminate_harness`` — a retained session is a record, not a live TUI."""

    @staticmethod
    def _runner(monkeypatch, server):
        monkeypatch.setattr(runner_mod.subprocess, "run", server.run)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        return TmuxRunner()

    def test_sigterm_ends_the_harness_and_keeps_the_pane(self, monkeypatch):
        server = FakeTmuxServer()
        runner = self._runner(monkeypatch, server)
        result = runner.terminate_harness(
            make_session(tmux_target="loop-x"), killer=server.killer
        )
        assert result.ok and not result.session_missing
        assert server.signals == [(4242, signal.SIGTERM)]
        # remain-on-exit is (re-)set so the scrollback survives the process…
        assert ["set-option", "-t", "loop-x", "-w", "remain-on-exit", "on"] in (
            server.calls
        )
        # …and the session itself is never killed — that would destroy it.
        assert "kill-session" not in server.verbs

    def test_escalates_to_sigkill_when_sigterm_is_ignored(self, monkeypatch):
        server = FakeTmuxServer(dies_on=signal.SIGKILL)
        runner = self._runner(monkeypatch, server)
        slept = []
        result = runner.terminate_harness(
            make_session(tmux_target="loop-x"),
            grace=0.4,
            sleeper=slept.append,
            killer=server.killer,
        )
        assert result.ok
        assert server.signals == [(4242, signal.SIGTERM), (4242, signal.SIGKILL)]
        assert slept  # the grace period was actually waited out

    def test_zero_grace_escalates_without_waiting(self, monkeypatch):
        server = FakeTmuxServer(dies_on=signal.SIGKILL)
        runner = self._runner(monkeypatch, server)
        slept = []
        runner.terminate_harness(
            make_session(tmux_target="loop-x"),
            grace=0,
            sleeper=slept.append,
            killer=server.killer,
        )
        assert slept == []
        assert (4242, signal.SIGKILL) in server.signals

    def test_a_harness_that_survives_sigkill_is_reported_not_raised(self, monkeypatch):
        server = FakeTmuxServer(dies_on=None)
        runner = self._runner(monkeypatch, server)
        result = runner.terminate_harness(
            make_session(tmux_target="loop-x"),
            grace=0,
            sleeper=lambda _: None,
            killer=server.killer,
        )
        assert result.ok is False and "still running" in result.error

    def test_already_dead_pane_signals_nothing(self, monkeypatch):
        server = FakeTmuxServer(alive=False)
        runner = self._runner(monkeypatch, server)
        assert runner.terminate_harness(
            make_session(tmux_target="loop-x"), killer=server.killer
        ).ok
        assert server.signals == []

    def test_missing_session_is_not_a_failure(self, monkeypatch):
        server = FakeTmuxServer(exists=False)
        runner = self._runner(monkeypatch, server)
        result = runner.terminate_harness(
            make_session(tmux_target="loop-x"), killer=server.killer
        )
        assert result.ok and result.session_missing
        assert server.signals == []

    def test_an_already_exited_process_is_not_a_failure(self, monkeypatch):
        server = FakeTmuxServer()

        def killer(pid, sig):
            server.alive = False
            raise ProcessLookupError(pid)

        runner = self._runner(monkeypatch, server)
        assert runner.terminate_harness(
            make_session(tmux_target="loop-x"), killer=killer
        ).ok

    def test_a_session_with_no_tmux_target_is_a_no_op(self, monkeypatch):
        server = FakeTmuxServer()
        runner = self._runner(monkeypatch, server)
        assert runner.terminate_harness(make_session(), killer=server.killer).ok
        assert server.calls == []

    @pytest.mark.parametrize("target", ["my-work", "loop", "loop-x;rm", "0"])
    def test_only_the_loops_own_sessions_are_ever_signalled(self, monkeypatch, target):
        # A corrupted/hand-edited registry must not be able to aim a SIGTERM at
        # some other tmux session's processes.
        server = FakeTmuxServer()
        runner = self._runner(monkeypatch, server)
        result = runner.terminate_harness(
            make_session(tmux_target=target), killer=server.killer
        )
        assert result.ok is False and "the-loop tmux session" in result.error
        assert server.signals == [] and server.calls == []


class TestLivePanePids:
    @staticmethod
    def _runner(monkeypatch, stdout):
        fake = FakeRun(stdout_per_verb={"list-panes": stdout})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        return TmuxRunner()

    def test_reads_live_panes_and_skips_dead_ones(self, monkeypatch):
        runner = self._runner(monkeypatch, "4242 0\n77 1\n99 0\n")
        assert runner.live_pane_pids("loop-x") == [4242, 99]

    @pytest.mark.parametrize("line", ["0 0\n", "-1 0\n", "nonsense 0\n", "\n"])
    def test_never_returns_a_pid_that_would_signal_a_process_group(
        self, monkeypatch, line
    ):
        # os.kill(0/-n, …) signals a whole process group — the one pid value
        # that must never leave this helper.
        runner = self._runner(monkeypatch, line)
        assert runner.live_pane_pids("loop-x") == []

    def test_unreadable_pane_list_signals_nothing(self, monkeypatch):
        fake = FakeRun(per_verb={"list-panes": 1})
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        assert TmuxRunner().live_pane_pids("loop-x") == []


class TestCheckDependencies:
    def test_silent_when_satisfied(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/x")
        assert check_dependencies("tmux", web_enabled=True) == []

    def test_process_runner_needs_nothing(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        assert check_dependencies("process", web_enabled=False) == []

    def test_reports_missing_tmux_and_ttyd_with_guidance(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        missing = check_dependencies("tmux", web_enabled=True)
        text = "\n".join(missing)
        assert "tmux" in text and "ttyd" in text
        assert "brew install" in text and "apt" in text


class TestRoutingConfigRunner:
    def test_defaults(self):
        config = RoutingConfig.from_mapping({})
        assert config.runner == "process"
        assert config.web_terminal.enabled is False
        assert config.web_terminal.host == "127.0.0.1"
        assert config.web_terminal.port == 7681
        # issue-86: a finished session stays readable out of the box.
        assert config.tmux.keep_session_on_close is True
        assert config.tmux.remain_on_exit is True
        # issue-89: a respawn continues the conversation out of the box.
        assert config.tmux.resume_on_respawn is True
        assert config.tmux.resume_probe_seconds == 2.0
        # issue-94: a closed work item's harness is ended out of the box.
        assert config.tmux.kill_harness_on_close is True
        assert config.tmux.harness_kill_grace_seconds == 5.0

    def test_parses_tmux_lifetime(self):
        config = RoutingConfig.from_mapping(
            {
                "tmux": {
                    "keepSessionOnClose": False,
                    "remainOnExit": False,
                    "resumeOnRespawn": False,
                    "resumeProbeSeconds": 0,
                    "killHarnessOnClose": False,
                    "harnessKillGraceSeconds": 0,
                }
            }
        )
        assert config.tmux.keep_session_on_close is False
        assert config.tmux.remain_on_exit is False
        assert config.tmux.resume_on_respawn is False
        assert config.tmux.resume_probe_seconds == 0.0
        assert config.tmux.kill_harness_on_close is False
        assert config.tmux.harness_kill_grace_seconds == 0.0

    def test_parses_runner_and_web_terminal(self):
        config = RoutingConfig.from_mapping(
            {
                "runner": "tmux",
                "webTerminal": {"enabled": True, "host": "10.0.0.5", "port": 9000},
            }
        )
        assert config.runner == "tmux"
        assert config.web_terminal.enabled is True
        assert config.web_terminal.host == "10.0.0.5"
        assert config.web_terminal.port == 9000


class TestReceiverPreflight:
    def test_web_terminal_argv_binds_configured_interface(self):
        argv = web_terminal_argv(host="127.0.0.1", port=7681)
        assert argv[0] == "ttyd"
        assert "--writable" in argv
        assert argv[argv.index("-p") + 1] == "7681"
        assert argv[argv.index("-i") + 1] == "127.0.0.1"
        assert argv[-5:] == ["tmux", "new-session", "-A", "-s", "the-loop-hub"]


class FakePopen:
    """Stand-in for subprocess.Popen recording argv, no real process spawned."""

    instances = []

    def __init__(self, argv):
        self.argv = argv
        self.terminated = False
        self.killed = False
        FakePopen.instances.append(self)

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        pass

    def kill(self):
        self.killed = True


class TestSharedWebTerminalLifecycle:
    """The ttyd start/stop helper both `gh-webhook start` and `poll start` share
    (issue-65: poll never launched ttyd because it had no equivalent code)."""

    def setup_method(self):
        FakePopen.instances = []

    def test_start_web_terminal_spawns_ttyd_and_logs_url(self, monkeypatch, caplog):
        monkeypatch.setattr(runner_mod.subprocess, "Popen", FakePopen)
        web = RoutingConfig.from_mapping(
            {"webTerminal": {"enabled": True, "host": "10.0.0.5", "port": 9000}}
        ).web_terminal

        with caplog.at_level("INFO", logger="the-loop.runner"):
            proc = start_web_terminal(web)

        assert isinstance(proc, FakePopen)
        assert proc.argv[0] == "ttyd"
        assert "10.0.0.5" in "".join(caplog.messages)
        assert "9000" in "".join(caplog.messages)

    def test_stop_web_terminal_terminates_the_process(self, monkeypatch):
        monkeypatch.setattr(runner_mod.subprocess, "Popen", FakePopen)
        web = RoutingConfig.from_mapping(
            {"webTerminal": {"enabled": True}}
        ).web_terminal
        proc = start_web_terminal(web)
        assert isinstance(proc, FakePopen)

        stop_web_terminal(proc)

        assert proc.terminated is True
        assert proc.killed is False

    def test_stop_web_terminal_is_a_noop_on_none(self):
        stop_web_terminal(None)  # no ttyd was started — must not raise


class TestSessionsCli:
    def test_attach_argv_read_write_and_read_only(self):
        session = make_session(runner="tmux", tmux_target="loop-x")
        assert sessions_cmd._attach_argv(session, read_only=False) == [
            "tmux",
            "attach-session",
            "-t",
            "loop-x",
        ]
        assert "-r" in sessions_cmd._attach_argv(session, read_only=True)

    def test_attach_rejects_process_sessions(self, tmp_path, capsys, monkeypatch):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session())
        code = sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda *_: None
        )
        assert code == 1
        assert "process" in capsys.readouterr().err

    def test_attach_reports_missing_tmux_binary(self, tmp_path, capsys, monkeypatch):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: False)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        code = sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda *_: None
        )
        assert code == 1
        assert "install" in capsys.readouterr().err

    def test_attach_execs_tmux_for_live_session(self, tmp_path, monkeypatch):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: True)
        monkeypatch.setattr(TmuxRunner, "has_session", lambda self, target: True)
        execs = []
        code = sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda f, a: execs.append((f, a))
        )
        assert code == 0
        assert execs == [("tmux", ["tmux", "attach-session", "-t", "loop-x"])]

    def test_attach_explains_dead_tmux_session(self, tmp_path, capsys, monkeypatch):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: True)
        monkeypatch.setattr(TmuxRunner, "has_session", lambda self, target: False)
        code = sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda *_: None
        )
        assert code == 1
        assert "sessions list" in capsys.readouterr().err

    def test_attach_reaches_a_retained_session_of_a_closed_work_item(
        self, tmp_path, capsys, monkeypatch
    ):
        # issue-86: reading back what the agent did is exactly why the session
        # is kept, so a closed work item must still be attachable.
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        registry.close(REF)
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: True)
        monkeypatch.setattr(TmuxRunner, "has_session", lambda self, target: True)
        execs = []
        code = sessions_cmd.attach_session(
            registry, REF, read_only=True, execvp=lambda f, a: execs.append((f, a))
        )
        assert code == 0
        assert execs and execs[0][1][-1] == "loop-x"
        assert "closed" in capsys.readouterr().err

    def test_attach_to_a_closed_session_is_always_read_only(
        self, tmp_path, capsys, monkeypatch
    ):
        # issue-94: a finished work item's terminal must not take input, even
        # when the caller forgot --read-only.
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        registry.close(REF)
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: True)
        monkeypatch.setattr(TmuxRunner, "has_session", lambda self, target: True)
        execs = []
        sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda f, a: execs.append((f, a))
        )
        assert "-r" in execs[0][1]
        assert "read-only" in capsys.readouterr().err

    def test_attach_to_an_active_session_keeps_read_only_opt_in(
        self, tmp_path, monkeypatch
    ):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(TmuxRunner, "is_available", lambda self: True)
        monkeypatch.setattr(TmuxRunner, "has_session", lambda self, target: True)
        execs = []
        sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda f, a: execs.append((f, a))
        )
        assert "-r" not in execs[0][1]

    def test_close_keeps_the_tmux_session_by_default(
        self, tmp_path, capsys, monkeypatch
    ):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(sessions_cmd, "_tmux_config", TmuxConfig)
        killed = []
        monkeypatch.setattr(
            TmuxRunner, "kill", lambda self, s, timeout=None: killed.append(s)
        )
        # issue-94: keeping the session still ends the harness inside it.
        ended = []
        monkeypatch.setattr(
            TmuxRunner,
            "terminate_harness",
            lambda self, s, **kw: ended.append((s.tmux_target, kw)) or TmuxResult(True),
        )
        args = argparse.Namespace(
            work_item=REF, registry_dir=str(tmp_path), keep_tmux=None
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert killed == []
        assert ended and ended[0][0] == "loop-x"
        assert ended[0][1]["grace"] == 5.0
        assert "tmux attach -r -t loop-x" in capsys.readouterr().out

    def test_close_can_leave_the_harness_running(self, tmp_path, capsys, monkeypatch):
        # routing.tmux.killHarnessOnClose: false — the pre-issue-94 behaviour.
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(
            sessions_cmd,
            "_tmux_config",
            lambda: TmuxConfig(kill_harness_on_close=False),
        )
        ended = []
        monkeypatch.setattr(
            TmuxRunner,
            "terminate_harness",
            lambda self, s, **kw: ended.append(s) or TmuxResult(True),
        )
        args = argparse.Namespace(
            work_item=REF, registry_dir=str(tmp_path), keep_tmux=None
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert ended == []

    def test_close_kill_tmux_flag_overrides_the_config_default(
        self, tmp_path, capsys, monkeypatch
    ):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(sessions_cmd, "_tmux_config", TmuxConfig)
        monkeypatch.setattr(runner_mod.subprocess, "run", FakeRun())
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        args = argparse.Namespace(
            work_item=REF, registry_dir=str(tmp_path), keep_tmux=False
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert "killed tmux session loop-x" in capsys.readouterr().out

    def test_list_shows_runner_and_tmux_columns(self, tmp_path, capsys):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        cmd = sessions_cmd.SessionsCommand()
        args = argparse.Namespace(
            registry_dir=str(tmp_path), status=None, format="table"
        )
        assert cmd._list(args) == 0
        out = capsys.readouterr().out
        assert "Runner" in out and "tmux" in out and "loop-x" in out


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(os.system("pytest -q " + __file__))
