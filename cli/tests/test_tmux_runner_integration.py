"""Integration tests: routed webhook events → dispatcher → stub tmux binary.

Drives the real Router + Dispatcher with a stub ``tmux`` executable (recording
every invocation, the same pattern as the stub harness CLI in
``test_webhook_routing_integration.py``) to prove what tmux is actually asked
to do — spawn, paste, kill — without requiring a real tmux server in CI.

Feature: tmux-hosted interactive sessions
Requirement: docs/specs/issue-32/requirements.md#R1 #R2 #R3 #R7
"""

import json
import stat
import time

import pytest

from the_loop.harness import ClaudeCodeAdapter
from the_loop.runner import TmuxRunner
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import Router

REF = "github:octo/repo#15"
AUTO_LABEL = "the-loop: auto-execute"

# Records argv as JSON lines; everything succeeds unless its tmux sub-command is
# listed in $STUB_TMUX_FAIL (comma-separated) — e.g. `has-session` to simulate a
# crashed/killed session (issue-80). $STUB_TMUX_PANE_DEAD makes `list-panes`
# report a dead pane, i.e. a session retained after its harness exited
# (issue-86).
STUB_TMUX = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STUB_TMUX_RECORD"], "a") as f:
    f.write(json.dumps(argv) + "\\n")
if argv and argv[0] == "list-panes":
    print("1" if os.environ.get("STUB_TMUX_PANE_DEAD") else "0")
fail = set(v for v in os.environ.get("STUB_TMUX_FAIL", "").split(",") if v)
sys.exit(1 if argv and argv[0] in fail else 0)
"""


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


def test_followup_event_is_pasted_into_the_running_session(pipeline):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: a follow-up comment is pasted into the live TUI
      Given a registered tmux-mode session for the work item
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


def pr_close_payload():
    return {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": 99,
            "merged": True,
            "head": {"ref": "claude/github-issue-15-x"},
            "body": "Closes #15",
        },
    }


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
    deliver, registry, _ = pipeline_factory(announcer=announcer)
    register_tmux_session(registry)
    monkeypatch.setenv("STUB_TMUX_FAIL", "has-session")
    deliver("issue_comment", issue_payload(action="created"), "d-announce-2")
    assert wait_until(
        lambda: registry.find_by_work_item(REF).harness_session_id != "uuid-1"
    )
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
    # The session crashed: every has-session probe now fails.
    monkeypatch.setenv("STUB_TMUX_FAIL", "has-session")
    deliver("issue_comment", issue_payload(action="created"), "d-dead-1")

    assert wait_until(
        lambda: (
            (
                registry.find_by_work_item(REF)
                or Session(WorkItemRef.parse(REF), "", "uuid-1", "")
            ).harness_session_id
            != "uuid-1"
        )
    )
    respawned = registry.find_by_work_item(REF)
    assert respawned is not None and respawned.runner == "tmux"
    assert respawned.tmux_target == "loop-github-octo-repo-15"
    assert "d-dead-1" in respawned.recent_deliveries  # marked processed

    (spawn,) = [c for c in calls() if c[0] == "new-session"]
    tail = spawn[spawn.index("--") + 1 :]
    assert tail[0].endswith("claude")
    assert tail[1] == "--session-id" and tail[2] == respawned.harness_session_id
    assert "issue_comment" in tail[-1]  # the event delivered as the boot prompt


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
    monkeypatch.setenv("STUB_TMUX_FAIL", "paste-buffer")
    deliver("issue_comment", issue_payload(action="created"), "d-alive-1")

    assert wait_until(lambda: any(c[0] == "paste-buffer" for c in calls()))
    # A respawn would issue new-session; it never does (the session is alive).
    # These hold at any point since nothing rewrites the registry on this path.
    assert [c for c in calls() if c[0] == "new-session"] == []  # no respawn
    still = registry.find_by_work_item(REF)
    assert still is not None and still.harness_session_id == "uuid-1"
    assert "d-alive-1" not in still.recent_deliveries  # released for retry
