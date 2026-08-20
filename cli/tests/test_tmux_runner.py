"""Unit tests for the tmux runner (issue-32).

Covers the pieces the integration file wires together: registry runner fields,
per-adapter interactive argv, TmuxRunner command construction, routing config
parsing, dependency preflight, and the sessions CLI helpers.

Spec: docs/specs/issue-32/design.md.
"""

import logging
import os
import signal

import pytest

from the_loop import runner as runner_mod
from the_loop.commands import sessions_cmd
from the_loop.core import sessions as core_sessions
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
from the_loop.sessions import Session, WorkItemRef, tmux_session_name
from the_loop.webhook.dispatcher import RoutingConfig, TmuxConfig

REF = "github:octo/repo#15"
# A work item whose slug carries a dot — a repo with one in its name (the same
# shape a GitHub Enterprise host produces). tmux rewrites that dot, which is
# issue-154.
DOTTED_REF = "github:octo/foo.js#15"
DOTTED_TARGET = "loop-github-octo-foo_js-15"


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
    does the same for stdout (e.g. ``list-panes`` pane-dead flags);
    ``stderr_per_verb`` for stderr (e.g. ``new-session`` reporting
    ``duplicate session``). ``timeout_verbs`` makes a sub-command raise
    ``TimeoutExpired`` instead of answering — a tmux server too busy to reply,
    which issue-146 is about not mistaking for "no such session".
    ``verbs_per_call`` overrides the exit code for the *n*-th occurrence of a
    verb, so a collision that clears can be modelled.
    """

    def __init__(
        self,
        returncode=0,
        per_verb=None,
        stdout_per_verb=None,
        stderr_per_verb=None,
        timeout_verbs=(),
        verbs_per_call=None,
    ):
        self.calls = []
        self.returncode = returncode
        self.per_verb = per_verb or {}
        self.stdout_per_verb = stdout_per_verb or {}
        self.stderr_per_verb = stderr_per_verb or {}
        self.timeout_verbs = set(timeout_verbs)
        self.verbs_per_call = verbs_per_call or {}

    def __call__(self, cmd, **kwargs):
        import subprocess as real_subprocess

        self.calls.append(list(cmd))
        verb = cmd[1]
        if verb in self.timeout_verbs:
            raise real_subprocess.TimeoutExpired(cmd, kwargs.get("timeout") or 10)
        seen = sum(1 for call in self.calls if call[1] == verb)
        per_call = self.verbs_per_call.get(verb)
        if per_call is not None and seen <= len(per_call):
            rc = per_call[seen - 1]
        else:
            rc = self.per_verb.get(verb, self.returncode)
        out = self.stdout_per_verb.get(verb, "")
        err = self.stderr_per_verb.get(verb, "")

        class Proc:
            returncode = rc
            stdout = out
            stderr = err

        return Proc()

    @property
    def verbs(self):
        return [call[1] for call in self.calls]


class TestSessionRunnerFields:
    def test_defaults_to_no_tmux_target(self):
        # "" means no tmux session spawned yet — the record heals on its next
        # dispatched event (issue-156).
        session = make_session()
        assert session.tmux_target == ""

    def test_round_trips_tmux_target_without_a_runner_field(self):
        session = make_session(tmux_target="loop-github-octo-repo-15")
        data = session.to_dict()
        assert "runner" not in data  # the selector was removed (issue-156)
        assert data["tmuxTarget"] == "loop-github-octo-repo-15"
        restored = Session.from_dict(data)
        assert restored.tmux_target == "loop-github-octo-repo-15"

    def test_normalises_a_legacy_tmux_target(self):
        # AC3 (issue-154): a record written before the fix holds the spelling
        # the-loop *asked* for; tmux had already renamed the session. Reading it
        # back must address the session that exists — no migration, nothing to
        # rename.
        data = make_session().to_dict()
        data["tmuxTarget"] = "loop-github-octo-foo.js-15"
        assert Session.from_dict(data).tmux_target == DOTTED_TARGET
        # …and a direct construction is normalised too, so the invariant is
        # total rather than path-dependent.
        assert (
            Session(
                work_item=WorkItemRef.parse(DOTTED_REF),
                harness="claude",
                harness_session_id="abc-123",
                cwd="/work",
                tmux_target="loop-github-octo-foo.js-15",
            ).tmux_target
            == DOTTED_TARGET
        )

    def test_a_process_session_keeps_its_empty_target(self):
        assert Session.from_dict(make_session().to_dict()).tmux_target == ""

    def test_reads_pre_issue32_registry_files(self):
        data = make_session().to_dict()
        del data["tmuxTarget"]  # a registry file written before issue-32
        restored = Session.from_dict(data)
        assert restored.tmux_target == ""

    def test_ignores_a_legacy_runner_field(self):
        # The reported bug (issue-156): a record whose runner said "process"
        # silently rerouted dispatch. The key is now ignored entirely.
        data = make_session().to_dict()
        data["runner"] = "process"
        restored = Session.from_dict(data)
        assert not hasattr(restored, "runner")


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


class TestTmuxSessionName:
    """tmux's own ``session_check_name`` rewrite, mirrored (issue-154)."""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("loop-github-octo-repo-15", "loop-github-octo-repo-15"),  # untouched
            ("loop-github-octo-foo.js-15", "loop-github-octo-foo_js-15"),
            (
                "loop-github-ghe.corp.example-octo-repo-15",
                "loop-github-ghe_corp_example-octo-repo-15",
            ),
            ("loop-a:b", "loop-a_b"),
            ("", ""),
        ],
    )
    def test_rewrites_only_tmux_target_syntax(self, raw, expected):
        assert tmux_session_name(raw) == expected

    def test_is_idempotent(self):
        once = tmux_session_name("loop-a.b:c-15")
        assert tmux_session_name(once) == once


class TestTmuxRunner:
    def test_target_is_slug_derived(self):
        target = TmuxRunner().target_for(WorkItemRef.parse(REF))
        assert target == "loop-github-octo-repo-15"

    def test_target_for_unchanged_for_plain_slugs(self):
        # AC2: no existing session, registry record or already-posted attach
        # command is invalidated by the issue-154 fix.
        for ref in ("github:octo/repo#15", "github:Octo-Org/the_loop#7"):
            item = WorkItemRef.parse(ref)
            assert TmuxRunner().target_for(item) == f"loop-{item.slug}"

    def test_target_for_strips_tmux_target_syntax(self):
        # AC1: the slug keeps its dots (it is also the registry file name), so
        # the rewrite has to happen here — otherwise tmux creates a different
        # session than the one the-loop records and posts.
        item = WorkItemRef.parse(DOTTED_REF)
        assert "." in item.slug  # the precondition this bug needs
        assert TmuxRunner().target_for(item) == DOTTED_TARGET

    def test_target_for_aliases_dot_and_underscore(self):
        # Known and intentional (issue-154 § Out of scope): tmux itself cannot
        # host both names at once. Pinned so a future change that makes the
        # alias *destructive* fails here rather than shipping.
        runner = TmuxRunner()
        assert runner.target_for(WorkItemRef.parse("github:octo/foo.bar#15")) == (
            runner.target_for(WorkItemRef.parse("github:octo/foo_bar#15"))
        )

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

    def test_the_target_addressed_entry_points_issue_the_same_tmux_commands(
        self, monkeypatch
    ):
        """issue-277's refactor is a refactor: `spawn`/`deliver`/`kill` for a work
        item produce byte-identical argv to the target-addressed calls they now
        delegate to. If they ever diverge, the work-item path has grown behaviour
        the standing-session path silently does not have — or the reverse."""
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        item = WorkItemRef.parse(REF)
        target = TmuxRunner().target_for(item)

        def argv_for(call, per_verb=None):
            fake = FakeRun(
                per_verb=per_verb if per_verb is not None else {"has-session": 1}
            )
            monkeypatch.setattr(runner_mod.subprocess, "run", fake)
            call(TmuxRunner())
            return [c for c in fake.calls if c[1] != "has-session"]

        by_item = argv_for(
            lambda r: r.spawn(
                work_item=item,
                adapter=ClaudeCodeAdapter(),
                prompt="start work",
                cwd="/work",
                session_id="uuid-1",
            )
        )
        by_target = argv_for(
            lambda r: r.spawn_in(
                target,
                ClaudeCodeAdapter(),
                "start work",
                cwd="/work",
                session_id="uuid-1",
            )
        )
        assert by_item == by_target

        session = make_session(tmux_target=target)

        # deliver's temporary buffer files differ per call, so compare the verbs
        # and targets rather than the file paths.
        def shape(calls):
            # The buffer file names are per-call temporaries; everything else —
            # the verb, the buffer name, the flags, the target — must match.
            return [
                [part for part in c if not part.startswith("/tmp/the-loop-")]
                for c in calls
                if c[1] != "list-panes"
            ]

        # `deliver` probes liveness first, so the session must look alive here.
        assert shape(argv_for(lambda r: r.deliver(session, "hello"), per_verb={})) == (
            shape(argv_for(lambda r: r.deliver_to(target, "hello"), per_verb={}))
        )
        assert argv_for(lambda r: r.kill(session)) == argv_for(
            lambda r: r.kill_target(target)
        )

    def test_terminate_harness_in_refuses_a_target_that_is_not_the_loops(self, caplog):
        """The guard that stops a hand-edited record aiming a SIGTERM at another
        tmux session applies to the target-addressed entry point too."""
        result = TmuxRunner().terminate_harness_in("not-a-loop-session", "standing:x")
        assert not result.ok and "not a the-loop tmux session name" in result.error

    def test_terminate_harness_in_accepts_a_standing_target(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        monkeypatch.setattr(
            runner_mod.subprocess, "run", FakeRun(per_verb={"has-session": 1})
        )
        # `has-session` non-zero: already gone, reported not refused.
        result = TmuxRunner().terminate_harness_in(
            "loop-standing-supervisor", "standing:supervisor"
        )
        assert result.ok and result.session_missing

    def test_spawn_clears_a_stale_session_with_the_same_name(self, monkeypatch):
        # has-session exits 0 and every pane is dead: a retained leftover holding
        # the name. Since issue-146 the pane read is what licenses the clear — a
        # leftover whose harness is still *running* is refused, not killed
        # (TestSpawnCollision).
        fake = FakeRun(stdout_per_verb={"list-panes": "1\n"})
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
            "list-panes",
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

    def test_deliver_pastes_bracketed_then_submits_without_send_keys(self, monkeypatch):
        # issue-240: the submit must not be `send-keys`. tmux resolves that
        # command's TARGET CLIENT from `-c`/the current client — never from `-t`
        # — so with a read-only observer attached (`tmux attach -r`) tmux >= 3.7
        # refuses it with "client is read-only" and the session's only input path
        # dies. `paste-buffer` writes straight into the pane and consults no
        # client, so both halves travel that way: the prompt bracketed, the
        # submit not.
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(tmux_target="loop-github-octo-repo-15")
        result = TmuxRunner().deliver(session, "event prompt")
        assert result.ok, result.error
        # liveness (has-session + list-panes), then the prompt buffer and its
        # bracketed paste, then the submit buffer and its unbracketed paste.
        assert fake.verbs == [
            "has-session",
            "list-panes",
            "load-buffer",
            "paste-buffer",
            "load-buffer",
            "paste-buffer",
        ]
        # Pinned as a whole rather than as "no send-keys": this repository's CI
        # runs a tmux without the guard, so only the argv itself can fail here
        # when a client-resolved command comes back.
        assert "send-keys" not in fake.verbs
        prompt_paste, submit_paste = fake.calls[3], fake.calls[5]
        assert "-p" in prompt_paste, "the prompt is one message, so it stays bracketed"
        assert "-p" not in submit_paste, "a bracketed submit would be literal text"
        for paste in (prompt_paste, submit_paste):
            assert "-d" in paste, "both buffers are deleted after use"
            assert paste[paste.index("-t") + 1] == "loop-github-octo-repo-15"
        # Two distinct buffers, so nothing depends on the order of a delete and
        # the next load.
        assert (
            prompt_paste[prompt_paste.index("-b") + 1]
            != submit_paste[submit_paste.index("-b") + 1]
        )

    def test_deliver_removes_both_temporary_files(self, monkeypatch):
        # R3.3: the prompt file was always unlinked; the submit file must be too,
        # including when the delivery fails between the two pastes.
        made = []
        real_mkstemp = runner_mod.tempfile.mkstemp

        def spy(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            made.append(path)
            return fd, path

        monkeypatch.setattr(runner_mod.tempfile, "mkstemp", spy)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        monkeypatch.setattr(runner_mod.subprocess, "run", FakeRun())
        assert TmuxRunner().deliver(make_session(tmux_target="loop-a"), "p").ok
        assert len(made) == 2
        assert not any(os.path.exists(path) for path in made)

        made.clear()
        # Second paste fails: the file written for it must still be cleaned up.
        monkeypatch.setattr(
            runner_mod.subprocess,
            "run",
            FakeRun(verbs_per_call={"paste-buffer": [0, 1]}),
        )
        assert not TmuxRunner().deliver(make_session(tmux_target="loop-a"), "p").ok
        assert made and not any(os.path.exists(path) for path in made)

    def test_a_failed_second_buffer_does_not_leak_the_first(self, monkeypatch):
        # Found by self-review. Writing the two files as a list literal left the
        # prompt file behind when the submit file could not be created (a full
        # disk) — a leak the single inline `mkstemp` this replaced did not have.
        made = []
        real_mkstemp = runner_mod.tempfile.mkstemp

        def spy(*args, **kwargs):
            if made:  # the second call: the disk is full
                raise OSError("No space left on device")
            fd, path = real_mkstemp(*args, **kwargs)
            made.append(path)
            return fd, path

        monkeypatch.setattr(runner_mod.tempfile, "mkstemp", spy)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        monkeypatch.setattr(runner_mod.subprocess, "run", FakeRun())
        with pytest.raises(OSError):
            TmuxRunner().deliver(make_session(tmux_target="loop-a"), "p")
        assert made and not os.path.exists(made[0])

    def test_a_buffer_file_that_cannot_be_written_leaves_nothing_behind(
        self, monkeypatch
    ):
        # The same property one level down: mkstemp created the file, the write
        # failed. Asserted on the helper, so it holds for any future caller.
        made = []
        real_mkstemp = runner_mod.tempfile.mkstemp

        def spy(*args, **kwargs):
            fd, path = real_mkstemp(*args, **kwargs)
            made.append(path)
            os.close(fd)  # fdopen on a closed fd raises inside the helper
            return -1, path

        monkeypatch.setattr(runner_mod.tempfile, "mkstemp", spy)
        # Whatever the failure is — the helper cleans up and re-raises it
        # unchanged, so the caller still sees a failed delivery.
        with pytest.raises(Exception):
            TmuxRunner._buffer_file("anything")
        assert made and not os.path.exists(made[0])

    def test_deliver_and_kill_address_the_normalised_target(self, monkeypatch):
        # AC5: every argv built from a legacy dotted record names the session
        # tmux created. Before issue-154 the probe here answered "can't find
        # pane: js-15" and a live session was reported `session_missing`.
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = Session.from_dict(
            {
                **make_session().to_dict(),
                "workItem": {"ref": DOTTED_REF},
                "tmuxTarget": "loop-github-octo-foo.js-15",
            }
        )
        assert TmuxRunner().deliver(session, "event prompt").ok
        assert TmuxRunner().kill(session).ok
        targeted = [call[call.index("-t") + 1] for call in fake.calls if "-t" in call]
        assert targeted and all(name == DOTTED_TARGET for name in targeted)

    def test_deliver_fails_when_session_is_gone(self, monkeypatch):
        fake = FakeRun(returncode=1)  # has-session exits non-zero
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        session = make_session(tmux_target="loop-gone")
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
        session = make_session(tmux_target="loop-alive")
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
        session = make_session(tmux_target="loop-retained")
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
        session = make_session(tmux_target="loop-x")
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


class TestSessionState:
    """``session_state`` — tmux's answer, and the absence of one (issue-146).

    The defect this closes: ``has_session`` returned False both when tmux said
    "no such session" *and* when tmux never answered (a busy server exceeding
    the probe timeout), so a **live** session read as gone and the respawn walked
    into ``duplicate session``.
    """

    @staticmethod
    def _runner(monkeypatch, **kwargs):
        fake = FakeRun(**kwargs)
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        return TmuxRunner(), fake

    def test_live_when_a_pane_is_running(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "0\n"})
        assert runner.session_state("loop-x") == runner_mod.SESSION_LIVE

    def test_dead_when_every_pane_has_exited(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "1\n"})
        assert runner.session_state("loop-x") == runner_mod.SESSION_DEAD

    def test_absent_when_tmux_answers_no_such_session(self, monkeypatch):
        runner, fake = self._runner(monkeypatch, per_verb={"has-session": 1})
        assert runner.session_state("loop-x") == runner_mod.SESSION_ABSENT
        assert "list-panes" not in fake.verbs

    def test_unknown_when_the_probe_times_out(self, monkeypatch):
        # The issue-146 trigger: a loaded/attached tmux server. NOT absent —
        # nothing may be killed or spawned over on this answer.
        runner, _ = self._runner(monkeypatch, timeout_verbs={"has-session"})
        assert runner.session_state("loop-x") == runner_mod.SESSION_UNKNOWN

    def test_unknown_when_tmux_is_not_installed(self, monkeypatch):
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        assert TmuxRunner().session_state("loop-x") == runner_mod.SESSION_UNKNOWN
        assert fake.calls == []

    def test_run_records_tmux_exit_status_and_leaves_it_none_on_no_answer(
        self, monkeypatch
    ):
        runner, _ = self._runner(monkeypatch, per_verb={"has-session": 1})
        assert runner._run(["has-session", "-t", "loop-x"]).exit_code == 1
        runner, _ = self._runner(monkeypatch, timeout_verbs={"has-session"})
        assert runner._run(["has-session", "-t", "loop-x"]).exit_code is None

    def test_has_session_truth_table(self, monkeypatch):
        runner, _ = self._runner(monkeypatch, stdout_per_verb={"list-panes": "1\n"})
        assert runner.has_session("loop-x") is True  # dead but present
        runner, _ = self._runner(monkeypatch, per_verb={"has-session": 1})
        assert runner.has_session("loop-x") is False
        # Unknown keeps reading as False for has_session's best-effort callers
        # (terminate_harness, sessions attach): "assume gone" is safe there.
        runner, _ = self._runner(monkeypatch, timeout_verbs={"has-session"})
        assert runner.has_session("loop-x") is False

    def test_an_unanswered_probe_is_live_for_delivery(self, monkeypatch):
        # has_live_session's documented bias — never declare a healthy session
        # dead — now applies to the has-session call too, not just the pane read.
        runner, _ = self._runner(monkeypatch, timeout_verbs={"has-session"})
        assert runner.has_live_session("loop-x") is True

    def test_delivery_to_an_unanswered_probe_is_not_a_missing_session(
        self, monkeypatch
    ):
        # So it is retried as a transient fault instead of triggering a respawn
        # that can only collide with the session that is still there (AC2).
        runner, _ = self._runner(
            monkeypatch, timeout_verbs={"has-session"}, per_verb={"load-buffer": 1}
        )
        result = runner.deliver(make_session(tmux_target="loop-busy"), "p")
        assert not result.ok
        assert result.session_missing is False


class TestSpawnCollision:
    """``spawn`` against an occupied ``loop-<slug>`` name (issue-146)."""

    @staticmethod
    def _spawn(monkeypatch, **kwargs):
        fake = FakeRun(**kwargs)
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        result = TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )
        return result, fake

    def test_a_live_occupant_is_neither_killed_nor_spawned_over(self, monkeypatch):
        # The bug this closes both ways: today's code kills a live agent when the
        # probe sees it, and crash-loops when the probe misses it.
        result, fake = self._spawn(monkeypatch, stdout_per_verb={"list-panes": "0\n"})
        assert not result.ok
        assert result.session_exists is True and result.session_live is True
        assert "kill-session" not in fake.verbs
        assert "new-session" not in fake.verbs
        assert "loop-github-octo-repo-15" in result.error

    def test_a_dead_occupant_is_cleared_then_spawned_over(self, monkeypatch):
        result, fake = self._spawn(monkeypatch, stdout_per_verb={"list-panes": "1\n"})
        assert result.ok, result.error
        assert fake.verbs.index("kill-session") < fake.verbs.index("new-session")

    def test_an_unclearable_dead_occupant_is_reported_not_spawned_over(
        self, monkeypatch
    ):
        result, fake = self._spawn(
            monkeypatch,
            stdout_per_verb={"list-panes": "1\n"},
            per_verb={"kill-session": 1},
        )
        assert not result.ok
        assert result.session_exists is True and result.session_live is False
        assert "new-session" not in fake.verbs  # never walk into the collision

    def test_a_kill_that_reports_failure_but_worked_still_spawns(self, monkeypatch):
        # kill-session errored, yet the session is gone: the only thing that
        # matters is that the name is free.
        fake = FakeRun(
            per_verb={"kill-session": 1},
            stdout_per_verb={"list-panes": "1\n"},
            verbs_per_call={"has-session": [0, 1]},
        )
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
        assert "new-session" in fake.verbs

    def test_an_unanswered_probe_lets_new_session_decide(self, monkeypatch):
        # Pre-flight cannot know, so it does not guess: tmux is the authority.
        result, fake = self._spawn(monkeypatch, timeout_verbs={"has-session"})
        assert result.ok, result.error
        assert "kill-session" not in fake.verbs
        assert "new-session" in fake.verbs

    @staticmethod
    def _staged_states(monkeypatch, states):
        """Make ``session_state`` answer ``states`` in order (last one repeats).

        The collision cases need the *pre-flight* probe to go unanswered and the
        re-probe after ``duplicate session`` to answer — a fixed return value
        cannot express that.
        """
        seen = []

        def state(self, target):
            seen.append(target)
            return states[min(len(seen) - 1, len(states) - 1)]

        monkeypatch.setattr(TmuxRunner, "session_state", state)
        return seen

    def _spawn_with(self, monkeypatch, fake, states):
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        self._staged_states(monkeypatch, states)
        return TmuxRunner().spawn(
            work_item=WorkItemRef.parse(REF),
            adapter=ClaudeCodeAdapter(),
            prompt="p",
            cwd="/work",
            session_id="uuid-1",
        )

    def test_duplicate_session_is_resolved_and_retried_exactly_once(self, monkeypatch):
        # tmux proves the name is taken (our probe timed out), the occupant turns
        # out to be a retained dead session -> clear it and spawn again. Once.
        fake = FakeRun(
            stderr_per_verb={
                "new-session": "duplicate session: loop-github-octo-repo-15"
            },
            verbs_per_call={"new-session": [1, 0]},
        )
        result = self._spawn_with(
            monkeypatch,
            fake,
            [runner_mod.SESSION_UNKNOWN, runner_mod.SESSION_DEAD],
        )
        assert result.ok, result.error
        assert fake.verbs.count("new-session") == 2
        assert fake.verbs.count("kill-session") == 1

    def test_duplicate_session_against_a_live_occupant_is_reported(self, monkeypatch):
        fake = FakeRun(
            per_verb={"new-session": 1},
            stderr_per_verb={
                "new-session": "duplicate session: loop-github-octo-repo-15"
            },
        )
        result = self._spawn_with(
            monkeypatch,
            fake,
            [runner_mod.SESSION_UNKNOWN, runner_mod.SESSION_LIVE],
        )
        assert not result.ok
        assert result.session_exists is True and result.session_live is True
        assert fake.verbs.count("new-session") == 1  # no blind retry
        assert "kill-session" not in fake.verbs

    def test_an_occupant_tmux_will_not_describe_is_assumed_live(self, monkeypatch):
        # tmux says the name is taken but the probe will not say by what. Only a
        # definite dead-pane reading licenses a kill, so this is reported as live:
        # never destroy what you cannot see. The caller tries delivering instead,
        # which is harmless if it really is a dead pane.
        fake = FakeRun(
            per_verb={"new-session": 1},
            stderr_per_verb={"new-session": "duplicate session: loop-x"},
        )
        result = self._spawn_with(
            monkeypatch,
            fake,
            [runner_mod.SESSION_UNKNOWN, runner_mod.SESSION_UNKNOWN],
        )
        assert not result.ok
        assert result.session_exists is True and result.session_live is True
        assert "kill-session" not in fake.verbs
        assert fake.verbs.count("new-session") == 1

    def test_has_session_stays_a_single_call(self, monkeypatch):
        # Existence only: terminate_harness / sessions attach do not need a pane
        # read, and this is on their hot path.
        fake = FakeRun()
        monkeypatch.setattr(runner_mod.subprocess, "run", fake)
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        assert TmuxRunner().has_session("loop-x") is True
        assert fake.verbs == ["has-session"]

    def test_a_persistent_duplicate_stops_after_one_retry(self, monkeypatch):
        fake = FakeRun(
            per_verb={"new-session": 1},
            stderr_per_verb={"new-session": "duplicate session: loop-x"},
        )
        result = self._spawn_with(
            monkeypatch,
            fake,
            [runner_mod.SESSION_UNKNOWN, runner_mod.SESSION_DEAD],
        )
        assert not result.ok
        assert fake.verbs.count("new-session") == 2  # bounded, not a loop


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

    @pytest.mark.parametrize(
        "target",
        [
            "my-work",
            "loop",
            "loop-x;rm",
            "0",
            # tmux target grammar (`session:window.pane`), rejected since
            # issue-154: `loop-other.session` is not a miss, it is a *pane*
            # lookup inside a session called `loop-other`.
            "loop-other.session",
            "loop-other:0.1",
        ],
    )
    def test_only_the_loops_own_sessions_are_ever_signalled(self, monkeypatch, target):
        # A corrupted/hand-edited registry must not be able to aim a SIGTERM at
        # some other tmux session's processes. `make_session` assigns the field
        # after construction, deliberately bypassing the normalisation, so the
        # guard itself is what is under test here.
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
        assert check_dependencies(web_enabled=True) == []

    def test_tmux_is_always_required(self, monkeypatch):
        # The process runner is gone (issue-156): the daemon cannot start
        # without tmux even with the web terminal off.
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        missing = check_dependencies(web_enabled=False)
        assert len(missing) == 1 and "tmux" in missing[0]

    def test_reports_missing_tmux_and_ttyd_with_guidance(self, monkeypatch):
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: None)
        missing = check_dependencies(web_enabled=True)
        text = "\n".join(missing)
        assert "tmux" in text and "ttyd" in text
        assert "brew install" in text and "apt" in text


class TestRoutingConfigRunner:
    def test_defaults(self):
        config = RoutingConfig.from_mapping({})
        assert not hasattr(config, "runner")  # the selector is gone (issue-156)
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

    def test_parses_web_terminal(self):
        config = RoutingConfig.from_mapping(
            {"webTerminal": {"enabled": True, "host": "10.0.0.5", "port": 9000}}
        )
        assert config.web_terminal.enabled is True
        assert config.web_terminal.host == "10.0.0.5"
        assert config.web_terminal.port == 9000

    def test_leftover_runner_key_warns_and_is_ignored(self, caplog):
        # An un-edited config must not brick the daemon (issue-156): the
        # removed key is tolerated, loudly, unless it already says tmux.
        with caplog.at_level(logging.WARNING):
            RoutingConfig.from_mapping({"runner": "process"})
        assert any("routing.runner" in r.message for r in caplog.records)
        caplog.clear()
        with caplog.at_level(logging.WARNING):
            RoutingConfig.from_mapping({"runner": "tmux"})
        assert not caplog.records


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
        session = make_session(tmux_target="loop-x")
        assert sessions_cmd._attach_argv(session, read_only=False) == [
            "tmux",
            "attach-session",
            "-t",
            "loop-x",
        ]
        assert "-r" in sessions_cmd._attach_argv(session, read_only=True)

    def test_attach_rejects_sessions_without_a_tmux_target(
        self, tmp_path, capsys, monkeypatch
    ):
        # A self-registered (or pre-tmux-only) record has no tmux session yet;
        # it gets one on its next dispatched event (issue-156).
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session())
        code = sessions_cmd.attach_session(
            registry, REF, read_only=False, execvp=lambda *_: None
        )
        assert code == 1
        assert "no tmux session recorded" in capsys.readouterr().err

    def test_attach_reports_missing_tmux_binary(self, tmp_path, capsys, monkeypatch):
        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
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
        registry.register(make_session(tmux_target="loop-x"))
        monkeypatch.setattr(
            core_sessions, "_tmux_config", lambda config=None: TmuxConfig()
        )
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
            work_item=REF,
            registry_dir=str(tmp_path),
            portable_dir=str(tmp_path),
            keep_tmux=None,
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
        registry.register(make_session(tmux_target="loop-x"))
        monkeypatch.setattr(
            core_sessions,
            "_tmux_config",
            lambda config=None: TmuxConfig(kill_harness_on_close=False),
        )
        ended = []
        monkeypatch.setattr(
            TmuxRunner,
            "terminate_harness",
            lambda self, s, **kw: ended.append(s) or TmuxResult(True),
        )
        args = argparse.Namespace(
            work_item=REF,
            registry_dir=str(tmp_path),
            portable_dir=str(tmp_path),
            keep_tmux=None,
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert ended == []

    def test_close_kill_tmux_flag_overrides_the_config_default(
        self, tmp_path, capsys, monkeypatch
    ):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(tmux_target="loop-x"))
        monkeypatch.setattr(
            core_sessions, "_tmux_config", lambda config=None: TmuxConfig()
        )
        monkeypatch.setattr(runner_mod.subprocess, "run", FakeRun())
        monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/tmux")
        args = argparse.Namespace(
            work_item=REF,
            registry_dir=str(tmp_path),
            portable_dir=str(tmp_path),
            keep_tmux=False,
        )
        assert sessions_cmd.SessionsCommand()._close(args) == 0
        assert "killed tmux session loop-x" in capsys.readouterr().out

    def test_list_shows_the_tmux_column(self, tmp_path, capsys):
        import argparse

        from the_loop.sessions import SessionRegistry

        registry = SessionRegistry(tmp_path)
        registry.register(make_session(tmux_target="loop-x"))
        cmd = sessions_cmd.SessionsCommand()
        args = argparse.Namespace(
            registry_dir=str(tmp_path),
            portable_dir=str(tmp_path),
            status=None,
            format="table",
        )
        assert cmd._list(args) == 0
        out = capsys.readouterr().out
        assert "Tmux" in out and "loop-x" in out
        assert "Runner" not in out  # the per-record selector is gone (issue-156)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(os.system("pytest -q " + __file__))
