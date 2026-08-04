"""Integration tests: routed webhook events → dispatcher → stub tmux binary.

Drives the real Router + Dispatcher with a stub ``tmux`` executable (recording
every invocation, the same pattern as the stub harness CLI in
``test_webhook_routing_integration.py``) to prove what tmux is actually asked
to do — spawn, paste, kill — without requiring a real tmux server in CI.

Feature: tmux-hosted interactive sessions
Requirement: docs/specs/issue-32/requirements.md#R1 #R2 #R3 #R7
"""

import json
import signal
import stat
import time

import pytest

from the_loop import eventlog
from the_loop import runner as runner_mod
from the_loop.harness import ClaudeCodeAdapter
from the_loop.runner import TmuxRunner
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

REF = "github:octo/repo#15"
AUTO_LABEL = "the-loop: auto-execute"

# Records argv as JSON lines and keeps just enough state to answer like tmux.
#
# **Which sessions exist** is tracked, not assumed (issue-146): the names in
# $STUB_TMUX_EXISTING (comma-separated) plus every name a recorded `new-session`
# created, minus every name a recorded `kill-session` removed. So `has-session`
# answers truthfully, and `new-session` against a name already held exits 1 with
# tmux's own `duplicate session: <name>` — the collision this stub could not
# express before, and therefore could not have caught.
#
# Everything else succeeds unless its tmux sub-command is listed in
# $STUB_TMUX_FAIL (comma-separated) — `has-session` to make the *probe* fail while
# the session is whatever the state says (a crashed session, issue-80, or the
# mis-read at the heart of issue-146), `kill-session` for a leftover that will not
# clear. $STUB_TMUX_PANE_DEAD makes `list-panes` report a dead pane, i.e. a session
# retained after its harness exited (issue-86); $STUB_TMUX_PANE_DEAD_ONCE reports
# one dead pane and then live ones — a liveness probe that read dead while the
# harness was in fact alive. `list-panes` answers whichever format was asked for,
# so the pid-carrying query `terminate_harness` uses (issue-94) gets
# $STUB_TMUX_PANE_PID; once $STUB_TMUX_KILLED_FLAG exists the pane reports dead —
# that file is how a test's fake `os.kill` says the harness took the signal.
# $STUB_TMUX_SLOW (comma-separated) makes a sub-command sleep
# $STUB_TMUX_SLOW_SECONDS before answering — a tmux server too busy to reply,
# which is how the-loop's probe times out (issue-146) without a test waiting out
# the real ten seconds.
STUB_TMUX = """#!/usr/bin/env python3
import json, os, sys, time
argv = sys.argv[1:]
record = os.environ["STUB_TMUX_RECORD"]
with open(record, "a") as f:
    f.write(json.dumps(argv) + "\\n")


def history():
    with open(record) as handle:
        return [json.loads(line) for line in handle if line.strip()]


def named(call, flag):
    return call[call.index(flag) + 1] if flag in call else ""


def existing(calls):  # reads `fail`, assigned below before any call
    names = set(n for n in os.environ.get("STUB_TMUX_EXISTING", "").split(",") if n)
    for call in calls:
        if call[0] == "new-session":
            names.add(named(call, "-s"))
        elif call[0] == "kill-session" and "kill-session" not in fail:
            names.discard(named(call, "-t"))
    return names


fail = set(v for v in os.environ.get("STUB_TMUX_FAIL", "").split(",") if v)
slow = set(v for v in os.environ.get("STUB_TMUX_SLOW", "").split(",") if v)
if argv and argv[0] in slow:
    time.sleep(float(os.environ.get("STUB_TMUX_SLOW_SECONDS", "0.5")))
past = history()[:-1]  # state BEFORE this call
if argv and argv[0] == "list-panes":
    dead = bool(os.environ.get("STUB_TMUX_PANE_DEAD"))
    if os.environ.get("STUB_TMUX_PANE_DEAD_ONCE"):
        dead = not any(call[0] == "list-panes" for call in past)
    killed = os.environ.get("STUB_TMUX_KILLED_FLAG")
    if killed and os.path.exists(killed):
        dead = True
    flag = "1" if dead else "0"
    pid = os.environ.get("STUB_TMUX_PANE_PID", "4242")
    print(pid + " " + flag if "pane_pid" in argv[-1] else flag)
if argv and argv[0] == "has-session" and named(argv, "-t") not in existing(past):
    sys.exit(1)
if argv and argv[0] == "new-session" and named(argv, "-s") in existing(past):
    sys.stderr.write("duplicate session: " + named(argv, "-s") + "\\n")
    sys.exit(1)
sys.exit(1 if argv and argv[0] in fail else 0)
"""

TARGET = "loop-github-octo-repo-15"


class RecordingAnnouncer:
    """Stand-in for SessionAnnouncer capturing what would be commented."""

    def __init__(self, ok=True):
        self.calls = []
        self.ok = ok

    def announce(self, session):
        self.calls.append((session.work_item.ref, session.tmux_target))
        return self.ok


def wait_until(predicate, timeout=5.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def stub_tmux(tmp_path, monkeypatch):
    record = tmp_path / "tmux-calls.jsonl"
    binary = tmp_path / "tmux"
    binary.write_text(STUB_TMUX)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("STUB_TMUX_RECORD", str(record))

    def calls():
        if not record.exists():
            return []
        return [json.loads(line) for line in record.read_text().splitlines()]

    return str(binary), calls


@pytest.fixture
def pipeline_factory(tmp_path, stub_tmux):
    """Build a Router + Dispatcher wired for tmux mode over the stub binary."""
    binary, calls = stub_tmux
    # The dispatcher refuses to spawn when the harness CLI is absent, so give
    # the adapter a stub `claude` too (never executed — the stub tmux records
    # the argv instead of running it).
    claude = tmp_path / "claude"
    claude.write_text("#!/usr/bin/env python3\n")
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR)
    dispatchers = []

    def build(overrides=None, announcer=None):
        registry = SessionRegistry(tmp_path / "sessions")
        config = RoutingConfig.from_mapping(
            {
                "runner": "tmux",
                "spawnOnUnmatched": "labeled",
                "spawnWorkdir": str(tmp_path),
                # Never wait out the resume probe in tests (issue-89); the stub
                # tmux answers `list-panes` instantly either way.
                "tmux": {"resumeProbeSeconds": 0},
                # Pre-issue-106 spawn behaviour: these cover the tmux runner,
                # not the start-command gate (which has its own tests).
                "control": {"requireStartCommand": False},
                **(overrides or {}),
            }
        )
        dispatcher = Dispatcher(
            registry=registry,
            adapters={"claude": ClaudeCodeAdapter(binary=str(claude))},
            config=config,
            tmux_runner=TmuxRunner(binary=binary),
            announcer=announcer,
        )
        dispatchers.append(dispatcher)
        router = Router(
            events=["issues", "issue_comment", "pull_request"],
            deduper=dispatcher.deduper,
            auto_execute_label=config.auto_execute_label,
        )

        def deliver(event, payload, delivery_id):
            routed = router.route(event, payload, delivery_id)
            assert routed is not None
            dispatcher.handle(routed)

        return deliver, registry, calls

    yield build
    for dispatcher in dispatchers:
        dispatcher.stop()


@pytest.fixture
def pipeline(pipeline_factory):
    return pipeline_factory()


def issue_payload(action="labeled", labels=(AUTO_LABEL,)):
    return {
        "action": action,
        "repository": {"full_name": "octo/repo"},
        "label": {"name": AUTO_LABEL} if action == "labeled" else {},
        "issue": {"number": 15, "labels": [{"name": name} for name in labels]},
    }


def test_labeled_issue_spawns_tmux_hosted_interactive_session(pipeline):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: an auto-execute-labeled issue spawns the harness TUI in tmux
      Given routing runs with runner=tmux and spawnOnUnmatched=labeled
      When a labeled issues event arrives with no registered session
      Then tmux is asked for a detached session named loop-<slug>
      And the harness starts interactively with a pre-assigned session id
      And the registry records a tmux-mode session for the work item
    Requirement: docs/specs/issue-32/requirements.md#R1 #R2
    """
    deliver, registry, calls = pipeline
    deliver("issues", issue_payload(), "d-spawn-1")
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)

    session = registry.find_by_work_item(REF)
    assert session.runner == "tmux"
    assert session.tmux_target == "loop-github-octo-repo-15"
    assert session.harness_session_id  # the pre-assigned uuid

    (spawn,) = [c for c in calls() if c[0] == "new-session"]
    assert "-d" in spawn
    assert spawn[spawn.index("-s") + 1] == "loop-github-octo-repo-15"
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[0].endswith("claude")
    assert tail[1] == "--session-id"
    assert tail[2] == session.harness_session_id


def test_followup_event_is_pasted_into_the_running_session(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a follow-up comment is pasted into the live TUI
      Given a registered tmux-mode session for the work item, live in tmux
      When an issue_comment event for that work item arrives
      Then the prompt is delivered via load-buffer, bracketed paste-buffer and Enter
      And the session records the processed delivery id
    Requirement: docs/specs/issue-32/requirements.md#R3
    """
    deliver, registry, calls = pipeline
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
            runner="tmux",
            tmux_target="loop-github-octo-repo-15",
        )
    )
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    deliver("issue_comment", issue_payload(action="created"), "d-evt-1")
    assert wait_until(
        lambda: (
            "d-evt-1"
            in (
                registry.find_by_work_item(REF)
                or Session(
                    work_item=WorkItemRef.parse(REF),
                    harness="",
                    harness_session_id="",
                    cwd="",
                )
            ).recent_deliveries
        )
    )

    verbs = [c[0] for c in calls()]
    # has-session + list-panes = the liveness probe (issue-86).
    assert verbs == [
        "has-session",
        "list-panes",
        "load-buffer",
        "paste-buffer",
        "send-keys",
    ]
    paste = calls()[3]
    assert "-p" in paste
    assert paste[paste.index("-t") + 1] == "loop-github-octo-repo-15"


def pr_close_payload(number=15):
    """A merged PR that **is** the work item (the non-GitHub-ticketing path).

    Only the closing object's own session ends (issue-101), so this is the PR
    payload that closes ``REF``; :func:`linked_pr_close_payload` is the other
    case — a PR merely *linked* to the work item, which leaves it running.
    """
    return {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "merged": True,
            "head": {"ref": "claude/github-issue-15-x"},
            "body": "Closes #15",
        },
    }


def linked_pr_close_payload():
    return pr_close_payload(number=99)


def register_tmux_session(registry, harness_session_id="uuid-1"):
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id=harness_session_id,
            cwd=".",
            runner="tmux",
            tmux_target="loop-github-octo-repo-15",
        ),
        force=True,
    )


def test_pr_close_keeps_the_tmux_session_by_default(pipeline):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a completed work item's tmux session survives for post-mortem
      Given a registered tmux-mode session for the work item
      And routing.tmux.keepSessionOnClose is left at its default
      When the pull_request closed event for its PR arrives
      Then the registry session is closed
      And tmux is NOT asked to kill the session, so its transcript stays readable
    Requirement: docs/specs/issue-86/requirements.md#R1
    """
    deliver, registry, calls = pipeline
    register_tmux_session(registry)
    deliver("pull_request", pr_close_payload(), "d-close-1")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    assert [c for c in calls() if c[0] == "kill-session"] == []


def test_pr_close_kills_the_tmux_session_when_configured_off(pipeline_factory):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: an operator opts back into killing the session on close
      Given a registered tmux-mode session for the work item
      And routing.tmux.keepSessionOnClose is false
      When the pull_request closed event for its PR arrives
      Then the registry session is closed
      And tmux is asked to kill-session the session's target
    Requirement: docs/specs/issue-86/requirements.md#R1
    """
    deliver, registry, calls = pipeline_factory({"tmux": {"keepSessionOnClose": False}})
    register_tmux_session(registry)
    deliver("pull_request", pr_close_payload(), "d-close-2")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    kills = [c for c in calls() if c[0] == "kill-session"]
    assert kills and kills[0][kills[0].index("-t") + 1] == "loop-github-octo-repo-15"


def test_a_linked_prs_close_leaves_the_tmux_session_running(pipeline_factory):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: one PR of a multi-PR work item merging leaves the session alone
      Given a registered tmux-mode session for work item 15
      And routing.tmux.keepSessionOnClose is false (so a close WOULD kill it)
      When the pull_request closed event for PR 99, linked to issue 15, arrives
      Then the registry session stays active
      And tmux is not asked to kill the session — the work item is still open
    Requirement: docs/specs/issue-101/requirements.md#AC1
    """
    deliver, registry, calls = pipeline_factory({"tmux": {"keepSessionOnClose": False}})
    register_tmux_session(registry)
    deliver("pull_request", linked_pr_close_payload(), "d-close-linked")
    time.sleep(0.2)
    session = registry.find_by_work_item(REF)
    assert session is not None and session.status == "active"
    assert [c for c in calls() if c[0] == "kill-session"] == []


def issue_close_payload():
    return {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15, "state_reason": "completed"},
    }


@pytest.fixture
def fake_kill(tmp_path, monkeypatch):
    """Record signals and let the stub tmux see the pane die (issue-94)."""
    flag = tmp_path / "harness-killed"
    monkeypatch.setenv("STUB_TMUX_KILLED_FLAG", str(flag))
    signals = []

    def killer(pid, sig):
        signals.append((pid, sig))
        flag.write_text("dead")

    monkeypatch.setattr(runner_mod.os, "kill", killer)
    return signals


@pytest.mark.parametrize(
    "event,payload_fn",
    [("pull_request", pr_close_payload), ("issues", issue_close_payload)],
)
def test_closing_a_work_item_ends_the_harness_but_keeps_the_session(
    pipeline, fake_kill, monkeypatch, event, payload_fn
):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a closed work item's harness is ended, its transcript retained
      Given a registered tmux-mode session for the work item, live in tmux
      And routing.tmux.keepSessionOnClose and killHarnessOnClose are at their defaults
      When the work item is closed (its PR merged, or the issue closed)
      Then the harness process in the session's pane is sent SIGTERM
      And remain-on-exit is set so the pane and its scrollback survive it
      And tmux is NOT asked to kill the session
    Requirement: docs/specs/issue-94/requirements.md#R3
    """
    deliver, registry, calls = pipeline
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    deliver(event, payload_fn(), f"d-term-{event}")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    assert wait_until(lambda: fake_kill == [(4242, signal.SIGTERM)])
    assert [c for c in calls() if c[0] == "kill-session"] == []
    assert [
        c
        for c in calls()
        if c[0] == "set-option" and c[-2:] == ["remain-on-exit", "on"]
    ]


def test_ending_the_harness_on_close_can_be_switched_off(pipeline_factory, fake_kill):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: an operator keeps the pre-issue-94 behaviour
      Given routing.tmux.killHarnessOnClose is false
      When the work item's PR is merged
      Then the registry session is closed
      And the harness inside the retained tmux session is left running
    Requirement: docs/specs/issue-94/requirements.md#R3
    """
    deliver, registry, calls = pipeline_factory({"tmux": {"killHarnessOnClose": False}})
    register_tmux_session(registry)
    deliver("pull_request", pr_close_payload(), "d-noterm-1")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    time.sleep(0.1)
    assert fake_kill == []


def test_retained_session_with_a_dead_pane_is_respawned(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: an event for a retained session whose harness exited respawns it
      Given a registered tmux-mode session that still exists in tmux
      But whose pane is dead (kept by remain-on-exit)
      When an issue_comment event for that work item arrives
      Then the event is not pasted into the dead pane
      And a fresh session is spawned with the event as its boot prompt
    Requirement: docs/specs/issue-86/requirements.md#R2
    """
    deliver, registry, calls = pipeline
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_PANE_DEAD", "1")
    deliver("issue_comment", issue_payload(action="created"), "d-dead-pane-1")

    assert wait_until(
        lambda: registry.find_by_work_item(REF).harness_session_id != "uuid-1"
    )
    assert any(c[0] == "new-session" for c in calls())
    assert [c for c in calls() if c[0] == "paste-buffer"] == []


def test_spawn_announces_the_session_on_the_work_item(pipeline_factory):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: the attach command reaches the humans on the ticket
      Given routing runs with runner=tmux and announcements enabled
      When a labeled issues event spawns a tmux-hosted session
      Then a comment announcing the tmux session is posted on the work item
    Requirement: docs/specs/issue-86/requirements.md#R3
    """
    announcer = RecordingAnnouncer()
    deliver, registry, _ = pipeline_factory(announcer=announcer)
    deliver("issues", issue_payload(), "d-announce-1")
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    assert wait_until(lambda: announcer.calls)
    assert announcer.calls == [(REF, "loop-github-octo-repo-15")]


def test_respawn_does_not_re_announce(pipeline_factory, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a respawn stays quiet on the ticket
      Given a registered tmux-mode session whose tmux session is gone
      When an issue_comment event for that work item arrives
      Then the session is respawned under the same loop-<slug> name
      And no second announcement comment is posted (the first one still applies)
    Requirement: docs/specs/issue-86/requirements.md#R3
    """
    announcer = RecordingAnnouncer()
    deliver, registry, calls = pipeline_factory(announcer=announcer)
    register_tmux_session(registry)  # nothing holds TARGET in tmux: it is gone
    deliver("issue_comment", issue_payload(action="created"), "d-announce-2")
    assert wait_until(
        lambda: "d-announce-2" in registry.find_by_work_item(REF).recent_deliveries
    )
    spawn = [c for c in calls() if c[0] == "new-session"][-1]
    assert spawn[spawn.index("-s") + 1] == TARGET  # same name, hence no re-announce
    assert announcer.calls == []


def test_a_failed_announcement_does_not_change_the_dispatch(pipeline_factory):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: announcing is best-effort
      Given an announcer that cannot post (e.g. gh is unauthenticated)
      When a labeled issues event spawns a tmux-hosted session
      Then the session is still registered and the delivery still marked processed
    Requirement: docs/specs/issue-86/requirements.md#R3
    """
    announcer = RecordingAnnouncer(ok=False)
    deliver, registry, _ = pipeline_factory(announcer=announcer)
    deliver("issues", issue_payload(), "d-announce-3")
    assert wait_until(lambda: registry.find_by_work_item(REF) is not None)
    session = registry.find_by_work_item(REF)
    assert session.runner == "tmux"
    assert wait_until(
        lambda: "d-announce-3" in registry.find_by_work_item(REF).recent_deliveries
    )


def test_dead_session_is_respawned_with_the_event_as_boot_prompt(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: an event to a crashed/killed tmux session respawns it
      Given a registered tmux-mode session whose tmux session is gone
      When an issue_comment event for that work item arrives
      Then tmux is asked for a fresh detached loop-<slug> session
      And the pending event is delivered as the new TUI's boot prompt
      And the registry records the respawned session (a new harness id)
      And the delivery is marked processed (not left to loop on redelivery)
    Requirement: docs/specs/issue-80/bugfix.md#AC7
    """
    deliver, registry, calls = pipeline
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
            runner="tmux",
            tmux_target="loop-github-octo-repo-15",
        )
    )
    # The session crashed, and its conversation is gone with it: the resume
    # attempt comes up dead, so the respawn falls back to a fresh conversation.
    monkeypatch.setenv("STUB_TMUX_PANE_DEAD", "1")
    deliver("issue_comment", issue_payload(action="created"), "d-dead-1")

    def respawned_and_recorded() -> bool:
        """Both registry writes landed, not just the first.

        ``_spawn_tmux`` registers the respawned session and *then* marks the
        delivery processed — ``register()`` followed by ``touch()``, two separate
        writes. Waiting only on the new harness id observes the first and races
        the second, so a worker thread descheduled between them left
        ``recent_deliveries`` empty and failed the assertion below (seen in CI,
        never locally). Every sibling test here already waits on the delivery
        itself; this one was the exception.
        """
        found = registry.find_by_work_item(REF)
        return bool(
            found
            and found.harness_session_id != "uuid-1"
            and "d-dead-1" in found.recent_deliveries
        )

    assert wait_until(respawned_and_recorded)
    respawned = registry.find_by_work_item(REF)
    assert respawned is not None and respawned.runner == "tmux"
    assert respawned.tmux_target == "loop-github-octo-repo-15"
    assert "d-dead-1" in respawned.recent_deliveries  # marked processed

    # Every pane comes up dead here, so the resume attempt (issue-89) cannot be
    # verified and the respawn falls back to a fresh conversation — the session
    # the registry ends up pointing at.
    spawn = [c for c in calls() if c[0] == "new-session"][-1]
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[0].endswith("claude")
    assert tail[1] == "--session-id" and tail[2] == respawned.harness_session_id
    assert "issue_comment" in tail[-1]  # the event delivered as the boot prompt


def test_respawn_resumes_the_dead_sessions_conversation(pipeline_factory, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a respawned session continues the same harness conversation
      Given a registered tmux-mode session whose tmux session was killed
      When an issue_comment event for that work item arrives
      Then the harness TUI is respawned with --resume <the recorded session id>
      And the registry keeps that same harness session id
      And no second announcement comment is posted
    Requirement: docs/specs/issue-89/requirements.md#R1
    Requirement: docs/specs/issue-146/bugfix.md#AC12
    """
    announcer = RecordingAnnouncer()
    deliver, registry, calls = pipeline_factory(announcer=announcer)
    register_tmux_session(registry)  # nothing holds TARGET in tmux any more
    deliver("issue_comment", issue_payload(action="created"), "d-resume-1")

    assert wait_until(
        lambda: "d-resume-1" in registry.find_by_work_item(REF).recent_deliveries
    )
    resumed = registry.find_by_work_item(REF)
    assert resumed.harness_session_id == "uuid-1"  # same conversation (R1.2)
    assert resumed.tmux_target == "loop-github-octo-repo-15"

    (spawn,) = [c for c in calls() if c[0] == "new-session"]  # no fallback spawn
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[0].endswith("claude")
    assert tail[1] == "--resume" and tail[2] == "uuid-1"
    assert "issue_comment" in tail[-1]  # the event is still the boot prompt
    assert announcer.calls == []  # same loop-<slug> name, no new comment


def test_a_busy_tmux_server_does_not_trigger_a_respawn(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a liveness probe the tmux server is too busy to answer
      Given a registered tmux-mode session that is alive in tmux
      But a tmux server too slow to answer the liveness probe before it times out
      When an issue_comment event for that work item arrives
      Then the event is still pasted into the live session
      And nothing is respawned (an unanswered probe is not an absent session)
    Requirement: docs/specs/issue-146/bugfix.md#AC1 #AC2
    """
    deliver, registry, calls = pipeline
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    monkeypatch.setenv("STUB_TMUX_SLOW", "has-session")
    monkeypatch.setenv("STUB_TMUX_SLOW_SECONDS", "0.2")
    monkeypatch.setattr(runner_mod, "_PROBE_TIMEOUT_SECONDS", 0.05)
    deliver("issue_comment", issue_payload(action="created"), "d-busy-1")

    assert wait_until(
        lambda: "d-busy-1" in registry.find_by_work_item(REF).recent_deliveries
    )
    assert any(c[0] == "paste-buffer" for c in calls())
    assert [c for c in calls() if c[0] == "new-session"] == []
    assert registry.find_by_work_item(REF).harness_session_id == "uuid-1"


def test_a_respawn_that_finds_the_session_alive_delivers_into_it(
    pipeline, monkeypatch, tmp_path
):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: the session is alive after all, so the pending event is pasted into it
      Given a registered tmux-mode session that is alive in tmux
      But whose liveness probe read dead when the event was delivered
      When the respawn re-checks the target name and finds a running harness
      Then the pending event is pasted into that session
      And no new session is spawned over it
      And the averted respawn is recorded as session.respawn_averted
    Requirement: docs/specs/issue-146/bugfix.md#AC6
    """
    deliver, registry, calls = pipeline
    log_path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log_path)
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    # Dead to the delivery's probe, alive to every probe after it: the race that
    # used to send a live session into `tmux new-session` and `duplicate session`.
    monkeypatch.setenv("STUB_TMUX_PANE_DEAD_ONCE", "1")
    deliver("issue_comment", issue_payload(action="created"), "d-averted-1")

    assert wait_until(
        lambda: "d-averted-1" in registry.find_by_work_item(REF).recent_deliveries
    )
    assert [c for c in calls() if c[0] == "new-session"] == []  # nothing spawned
    assert [c for c in calls() if c[0] == "kill-session"] == []  # nothing killed
    paste = [c for c in calls() if c[0] == "paste-buffer"]
    assert paste and paste[0][paste[0].index("-t") + 1] == TARGET
    kept = registry.find_by_work_item(REF)
    assert kept.harness_session_id == "uuid-1"  # same conversation, untouched
    types = [json.loads(line)["event"] for line in log_path.read_text().splitlines()]
    assert "session.respawn_averted" in types
    assert "session.respawned" not in types


def test_an_unclearable_occupant_skips_the_event_instead_of_looping(
    pipeline, monkeypatch, tmp_path
):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a dead session holds the name and will not clear
      Given a registered tmux-mode session whose pane is dead
      And a tmux that refuses to kill that session
      When an issue_comment event for that work item arrives
      Then no session is spawned over it (no `duplicate session` collision)
      And the dispatch is dropped as session-occupied, not failed
      And the delivery id is NOT released, so no cycle retries the same collision
    Requirement: docs/specs/issue-146/bugfix.md#AC5 #AC8
    """
    deliver, registry, calls = pipeline
    log_path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log_path)
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    monkeypatch.setenv("STUB_TMUX_PANE_DEAD", "1")
    monkeypatch.setenv("STUB_TMUX_FAIL", "kill-session")
    deliver("issue_comment", issue_payload(action="created"), "d-occupied-1")

    def dropped():
        if not log_path.exists():
            return False
        return any(
            json.loads(line).get("reason") == "session-occupied"
            for line in log_path.read_text().splitlines()
        )

    assert wait_until(dropped)
    assert [c for c in calls() if c[0] == "new-session"] == []
    kept = registry.find_by_work_item(REF)
    assert kept is not None and kept.harness_session_id == "uuid-1"
    assert "d-occupied-1" not in kept.recent_deliveries  # not claimed as handled


def test_an_unresumable_conversation_falls_back_to_a_fresh_session(
    pipeline, monkeypatch, tmp_path
):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a resume that cannot start does not swallow the event
      Given a registered tmux-mode session whose recorded conversation is gone
      When an issue_comment event for that work item arrives
      And the resumed harness exits immediately (its pane comes up dead)
      Then a fresh session is spawned with a new pre-assigned id
      And the pending event is still delivered as that session's boot prompt
      And the delivery is marked processed rather than left to loop
      And the event log says the resume was abandoned
    Requirement: docs/specs/issue-89/requirements.md#R2 #R3
    """
    deliver, registry, calls = pipeline
    log_path = tmp_path / "events.jsonl"
    eventlog.configure("test", path=log_path)
    register_tmux_session(registry)
    # Every pane reads dead: the resume attempt never comes up.
    monkeypatch.setenv("STUB_TMUX_PANE_DEAD", "1")
    deliver("issue_comment", issue_payload(action="created"), "d-resume-2")

    assert wait_until(
        lambda: registry.find_by_work_item(REF).harness_session_id != "uuid-1"
    )
    fresh = registry.find_by_work_item(REF)
    assert wait_until(
        lambda: "d-resume-2" in registry.find_by_work_item(REF).recent_deliveries
    )

    attempt, fallback = [c for c in calls() if c[0] == "new-session"]
    assert attempt[attempt.index("--") + 1 :][1:3] == ["--resume", "uuid-1"]
    tail = fallback[fallback.index("--") + 1 :]
    assert tail[1] == "--session-id" and tail[2] == fresh.harness_session_id
    assert "issue_comment" in tail[-1]

    # Wait for the log, not just the registry. `session.respawned` is emitted
    # AFTER `registry.register()` and `registry.touch()` (dispatcher.py), so both
    # waits above can be satisfied while the record is still unwritten — reading
    # here directly is a race the dispatcher wins on an idle laptop and loses on a
    # loaded CI runner.
    assert wait_until(lambda: "session.respawned" in log_path.read_text())

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    (abandoned,) = [r for r in records if r["event"] == "session.resume_failed"]
    assert abandoned["level"] == "warning"
    assert abandoned["harness_session_id"] == "uuid-1"
    (respawned,) = [r for r in records if r["event"] == "session.respawned"]
    assert respawned["resumed"] is False


def test_a_flag_shaped_session_id_is_never_passed_to_the_harness(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a registry id that is not shaped like one the-loop wrote
      Given a registered tmux-mode session whose recorded harness id is flag-shaped
      When an issue_comment event finds that session dead
      Then the id is never handed to the harness CLI
      And the respawn starts a fresh conversation instead
    Requirement: docs/specs/issue-89/requirements.md#R1
    """
    deliver, registry, calls = pipeline
    register_tmux_session(registry, harness_session_id="--dangerously-skip-permissions")
    deliver("issue_comment", issue_payload(action="created"), "d-resume-4")

    assert wait_until(
        lambda: "d-resume-4" in registry.find_by_work_item(REF).recent_deliveries
    )
    (spawn,) = [c for c in calls() if c[0] == "new-session"]
    assert "--resume" not in spawn
    assert "--dangerously-skip-permissions" not in spawn
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[1] == "--session-id"
    assert tail[2] == registry.find_by_work_item(REF).harness_session_id


def test_resume_on_respawn_can_be_switched_off(pipeline_factory, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: the pre-issue-89 behaviour stays available
      Given routing.tmux.resumeOnRespawn is false
      And a registered tmux-mode session whose tmux session was killed
      When an issue_comment event for that work item arrives
      Then the respawn starts a fresh conversation without attempting a resume
    Requirement: docs/specs/issue-89/requirements.md#R1
    """
    deliver, registry, calls = pipeline_factory(
        overrides={"tmux": {"resumeOnRespawn": False, "resumeProbeSeconds": 0}}
    )
    register_tmux_session(registry)
    deliver("issue_comment", issue_payload(action="created"), "d-resume-3")

    assert wait_until(
        lambda: registry.find_by_work_item(REF).harness_session_id != "uuid-1"
    )
    (spawn,) = [c for c in calls() if c[0] == "new-session"]
    assert "--resume" not in spawn
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[1] == "--session-id"


def test_non_missing_delivery_failure_does_not_respawn(pipeline, monkeypatch):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a delivery failure while the session is alive does not respawn
      Given a registered tmux-mode session that is alive (has-session succeeds)
      When a paste sub-command fails mid-delivery
      Then no fresh session is spawned
      And the delivery is released for retry (not marked processed)
    Requirement: docs/specs/issue-80/bugfix.md#AC8
    """
    deliver, registry, calls = pipeline
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="uuid-1",
            cwd=".",
            runner="tmux",
            tmux_target="loop-github-octo-repo-15",
        )
    )
    # Session is alive, but the bracketed paste errors.
    monkeypatch.setenv("STUB_TMUX_EXISTING", TARGET)
    monkeypatch.setenv("STUB_TMUX_FAIL", "paste-buffer")
    deliver("issue_comment", issue_payload(action="created"), "d-alive-1")

    assert wait_until(lambda: any(c[0] == "paste-buffer" for c in calls()))
    # A respawn would issue new-session; it never does (the session is alive).
    # These hold at any point since nothing rewrites the registry on this path.
    assert [c for c in calls() if c[0] == "new-session"] == []  # no respawn
    still = registry.find_by_work_item(REF)
    assert still is not None and still.harness_session_id == "uuid-1"
    assert "d-alive-1" not in still.recent_deliveries  # released for retry
