"""Unit tests for the tmux runner (issue-32).

Covers the pieces the integration file wires together: registry runner fields,
per-adapter interactive argv, TmuxRunner command construction, routing config
parsing, dependency preflight, and the sessions CLI helpers.

Spec: docs/specs/issue-32/design.md.
"""

import os

import pytest

from the_loop import runner as runner_mod
from the_loop.commands import sessions_cmd
from the_loop.harness import ClaudeCodeAdapter, CursorAgentAdapter
from the_loop.runner import (
    TmuxRunner,
    UnsupportedRunnerError,
    check_dependencies,
    start_web_terminal,
    stop_web_terminal,
    web_terminal_argv,
)
from the_loop.sessions import Session, WorkItemRef
from the_loop.webhook.dispatcher import RoutingConfig

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

    def test_parses_tmux_lifetime(self):
        config = RoutingConfig.from_mapping(
            {"tmux": {"keepSessionOnClose": False, "remainOnExit": False}}
        )
        assert config.tmux.keep_session_on_close is False
        assert config.tmux.remain_on_exit is False

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

    def test_close_keeps_the_tmux_session_by_default(
        self, tmp_path, capsys, monkeypatch
    ):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(sessions_cmd, "_default_keep_tmux", lambda: True)
        killed = []
        monkeypatch.setattr(
            TmuxRunner, "kill", lambda self, s, timeout=None: killed.append(s)
        )
        args = argparse.Namespace(
            work_item=REF, registry_dir=str(tmp_path), keep_tmux=None
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert killed == []
        assert "tmux attach -t loop-x" in capsys.readouterr().out

    def test_close_kill_tmux_flag_overrides_the_config_default(
        self, tmp_path, capsys, monkeypatch
    ):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(runner="tmux", tmux_target="loop-x"))
        monkeypatch.setattr(sessions_cmd, "_default_keep_tmux", lambda: True)
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
