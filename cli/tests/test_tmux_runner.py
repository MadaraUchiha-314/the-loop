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
    (e.g. ``{"has-session": 1}`` = "no such session").
    """

    def __init__(self, returncode=0, per_verb=None):
        self.calls = []
        self.returncode = returncode
        self.per_verb = per_verb or {}

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        rc = self.per_verb.get(cmd[1], self.returncode)

        class Proc:
            returncode = rc
            stdout = ""
            stderr = ""

        return Proc()


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
        cmd = fake.calls[-1]
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
        assert [c[1] for c in fake.calls] == [
            "has-session",
            "kill-session",
            "new-session",
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
        # has-session, load-buffer, paste-buffer -p, send-keys Enter — in order.
        verbs = [call[1] for call in fake.calls]
        assert verbs == ["has-session", "load-buffer", "paste-buffer", "send-keys"]
        paste = fake.calls[2]
        assert "-p" in paste
        assert paste[paste.index("-t") + 1] == "loop-github-octo-repo-15"
        assert fake.calls[3][-1] == "Enter"

    def test_deliver_fails_when_session_is_gone(self, monkeypatch):
        fake = FakeRun(returncode=1)  # has-session exits non-zero
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-gone")
        result = TmuxRunner().deliver(session, "event prompt")
        assert not result.ok
        assert "loop-gone" in result.error

    def test_kill_targets_the_session(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(runner="tmux", tmux_target="loop-x")
        assert TmuxRunner().kill(session).ok
        (cmd,) = fake.calls
        assert cmd[1] == "kill-session"
        assert cmd[cmd.index("-t") + 1] == "loop-x"


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
