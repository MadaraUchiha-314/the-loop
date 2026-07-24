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
# crashed/killed session (issue-80).
STUB_TMUX = """#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STUB_TMUX_RECORD"], "a") as f:
    f.write(json.dumps(argv) + "\\n")
fail = set(v for v in os.environ.get("STUB_TMUX_FAIL", "").split(",") if v)
sys.exit(1 if argv and argv[0] in fail else 0)
"""


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
def pipeline(tmp_path, stub_tmux):
    """Router + Dispatcher wired for tmux mode over the stub binary."""
    binary, calls = stub_tmux
    # The dispatcher refuses to spawn when the harness CLI is absent, so give
    # the adapter a stub `claude` too (never executed — the stub tmux records
    # the argv instead of running it).
    claude = tmp_path / "claude"
    claude.write_text("#!/usr/bin/env python3\n")
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR)
    registry = SessionRegistry(tmp_path / "sessions")
    config = RoutingConfig.from_mapping(
        {"runner": "tmux", "spawnOnUnmatched": "labeled", "spawnWorkdir": str(tmp_path)}
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": ClaudeCodeAdapter(binary=str(claude))},
        config=config,
        tmux_runner=TmuxRunner(binary=binary),
    )
    router = Router(
        events=["issues", "issue_comment", "pull_request"],
        deduper=dispatcher.deduper,
        auto_execute_label=config.auto_execute_label,
    )

    def deliver(event, payload, delivery_id):
        routed = router.route(event, payload, delivery_id)
        assert routed is not None
        dispatcher.handle(routed)

    yield deliver, registry, calls
    dispatcher.stop()


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
    assert verbs == ["has-session", "load-buffer", "paste-buffer", "send-keys"]
    paste = calls()[2]
    assert "-p" in paste
    assert paste[paste.index("-t") + 1] == "loop-github-octo-repo-15"


def test_pr_close_kills_the_tmux_session(pipeline):
    """
    Feature: tmux-hosted interactive sessions
    Scenario: closing the work item's PR terminates its tmux session
      Given a registered tmux-mode session for the work item
      When the pull_request closed event for its PR arrives
      Then the registry session is closed
      And tmux is asked to kill-session the session's target
    Requirement: docs/specs/issue-32/requirements.md#R7
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
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": 99,
            "merged": True,
            "head": {"ref": "claude/github-issue-15-x"},
            "body": "Closes #15",
        },
    }
    deliver("pull_request", payload, "d-close-1")
    assert wait_until(lambda: registry.find_by_work_item(REF) is None)
    kills = [c for c in calls() if c[0] == "kill-session"]
    assert kills and kills[0][kills[0].index("-t") + 1] == "loop-github-octo-repo-15"


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
