"""Unit tests for webhook→session routing: registry, router, adapters, dispatcher.

Spec: docs/specs/issue-15/ (requirements R2–R5).
"""

import json
import stat
import threading
import time
from pathlib import Path

import pytest

from the_loop.harness import (
    ClaudeCodeAdapter,
    CursorAgentAdapter,
    DispatchResult,
)
from the_loop.sessions import (
    RegistryError,
    Session,
    SessionRegistry,
    WorkItemRef,
)
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import (
    Deduper,
    RoutedEvent,
    Router,
    event_actor,
    event_body,
    event_carries_label,
    extract_work_items,
)

LABEL = "the-loop: auto-execute"

REF = "github:octo/repo#15"


def make_session(ref=REF, harness="claude", session_id="sess-1", cwd="."):
    return Session(
        work_item=WorkItemRef.parse(ref),
        harness=harness,
        harness_session_id=session_id,
        cwd=str(Path(cwd).resolve()),
    )


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# -- session registry (R2) ----------------------------------------------------


def test_registry_work_item_ref_parse_roundtrip():
    ref = WorkItemRef.parse(REF)
    assert (ref.provider, ref.owner, ref.repo, ref.number) == (
        "github",
        "octo",
        "repo",
        15,
    )
    assert ref.ref == REF


@pytest.mark.parametrize(
    "bad", ["", "github:octo/repo", "octo/repo#1", "github:octo#2", "jira:"]
)
def test_registry_work_item_ref_rejects_garbage(bad):
    with pytest.raises(ValueError):
        WorkItemRef.parse(bad)


def test_registry_register_and_find_roundtrip(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    found = registry.find_by_work_item(REF)
    assert found is not None
    assert found.harness_session_id == "sess-1"
    assert found.status == "active"
    assert found.created_at  # timestamped
    # the on-disk artifact is a single human-inspectable JSON file
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text())["workItem"]["ref"] == REF


def test_registry_refuses_second_active_session_unless_forced(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session(session_id="old"))
    with pytest.raises(RegistryError):
        registry.register(make_session(session_id="new"))
    registry.register(make_session(session_id="new"), force=True)
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "new"


def test_registry_close_and_list(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.register(make_session(ref="github:octo/repo#16", session_id="s2"))
    assert registry.close(REF) is True
    assert registry.find_by_work_item(REF) is None  # closed != active
    assert {s.status for s in registry.list_sessions()} == {"active", "closed"}
    assert len(registry.list_sessions(status="active")) == 1
    # closing again is a no-op that reports nothing to close
    assert registry.close(REF) is False


def test_registry_reregister_after_close_is_allowed(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session(session_id="first"))
    registry.close(REF)
    registry.register(make_session(session_id="second"))
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "second"


def test_registry_touch_records_event_and_delivery(tmp_path):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    registry.touch(REF, delivery_id="uuid-1")
    found = registry.find_by_work_item(REF)
    assert found is not None
    assert found.last_event_at
    assert "uuid-1" in found.recent_deliveries


def test_registry_skips_corrupt_file(tmp_path, caplog):
    registry = SessionRegistry(tmp_path)
    registry.register(make_session())
    (tmp_path / "garbage.json").write_text("{not json")
    assert len(registry.list_sessions()) == 1  # corrupt entry skipped, no crash


# -- event router (R3) --------------------------------------------------------


def payload_issue_comment(number=15, body="hi"):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"body": body},
    }


def payload_pull_request(number=16, branch="claude/github-issue-15-x", body=""):
    return {
        "action": "synchronize",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": body,
        },
    }


def payload_workflow_run(branch="claude/github-issue-15-x", prs=(16,)):
    return {
        "action": "completed",
        "repository": {"full_name": "octo/repo"},
        "workflow_run": {
            "head_branch": branch,
            "conclusion": "failure",
            "pull_requests": [{"number": n} for n in prs],
        },
    }


def test_router_extracts_issue_comment_work_item():
    refs = extract_work_items("issue_comment", payload_issue_comment())
    assert [r.ref for r in refs] == [REF]


def test_router_extracts_pr_number_branch_issue_and_closing_keyword():
    payload = payload_pull_request(body="Closes #15")
    refs = {r.ref for r in extract_work_items("pull_request", payload)}
    # PR itself, the issue from the branch name, and the closing keyword (deduped)
    assert refs == {"github:octo/repo#16", REF}


def test_router_extracts_workflow_run_prs_and_branch_issue():
    refs = {r.ref for r in extract_work_items("workflow_run", payload_workflow_run())}
    assert refs == {"github:octo/repo#16", REF}


def test_router_returns_nothing_for_unknown_event():
    assert extract_work_items("ping", {"zen": "ok"}) == []


def test_router_filters_disabled_event_types():
    router = Router(events=["workflow_run"])
    routed = router.route("issue_comment", payload_issue_comment(), "d-1")
    assert routed is None
    routed = router.route("workflow_run", payload_workflow_run(), "d-2")
    assert routed is not None and routed.event == "workflow_run"


def test_router_empty_event_filter_allows_all():
    router = Router(events=[])
    assert router.route("issue_comment", payload_issue_comment(), "d-1") is not None


def test_event_carries_label_from_labeled_action():
    payload = {"action": "labeled", "label": {"name": LABEL}, "issue": {"number": 15}}
    assert event_carries_label(payload, LABEL) is True
    other = {"action": "labeled", "label": {"name": "bug"}, "issue": {"number": 15}}
    assert event_carries_label(other, LABEL) is False


def test_event_carries_label_from_current_label_set():
    issue = {"action": "created", "issue": {"number": 15, "labels": [{"name": LABEL}]}}
    assert event_carries_label(issue, LABEL) is True
    pr = {"action": "synchronize", "pull_request": {"labels": [{"name": LABEL}]}}
    assert event_carries_label(pr, LABEL) is True


def test_event_carries_label_false_when_absent_or_unlabelled():
    assert event_carries_label({"issue": {"number": 15, "labels": []}}, LABEL) is False
    assert event_carries_label({"workflow_run": {}}, LABEL) is False  # no labels
    assert event_carries_label({"issue": {"labels": [{"name": LABEL}]}}, "") is False


def test_router_sets_labeled_flag():
    router = Router(events=[], auto_execute_label=LABEL)
    labeled = router.route(
        "issues",
        {
            "action": "labeled",
            "label": {"name": LABEL},
            "repository": {"full_name": "octo/repo"},
            "issue": {"number": 15},
        },
        "d-1",
    )
    assert labeled is not None and labeled.labeled is True
    plain = router.route("issue_comment", payload_issue_comment(), "d-2")
    assert plain is not None and plain.labeled is False


def _issue_comment_by(login, number=15):
    return {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
        "comment": {"user": {"login": login}, "body": "hi"},
    }


def test_event_actor_extraction():
    assert event_actor("issue_comment", _issue_comment_by("alice")) == "alice"
    assert (
        event_actor(
            "pull_request_review",
            {"review": {"user": {"login": "bob"}}},
        )
        == "bob"
    )
    assert (
        event_actor("issues", {"sender": {"login": "carol"}, "action": "labeled"})
        == "carol"
    )
    # pure system events (CI) have no human actor
    assert event_actor("workflow_run", {"workflow_run": {}}) is None


def test_event_body_extraction():
    assert event_body("issue_comment", _issue_comment_by("alice")) == "hi"
    assert (
        event_body("pull_request_review_comment", {"comment": {"body": "nit: typo"}})
        == "nit: typo"
    )
    assert event_body("pull_request_review", {"review": {"body": "LGTM"}}) == "LGTM"
    # events with no reply text carry no body to check
    assert event_body("workflow_run", {"workflow_run": {}}) is None
    assert event_body("issues", {"issue": {"body": "issue body"}}) is None


def test_router_drops_event_from_unauthorized_actor():
    router = Router(events=[], authorized_users=["me"])
    assert router.route("issue_comment", _issue_comment_by("attacker"), "d-1") is None
    assert router.route("issue_comment", _issue_comment_by("me"), "d-2") is not None


def test_router_empty_allowlist_fails_closed_for_human_events():
    router = Router(events=[], authorized_users=[])  # nobody authorized
    assert router.route("issue_comment", _issue_comment_by("anyone"), "d-1") is None


def test_router_allows_actorless_ci_event_even_when_gated():
    router = Router(events=[], authorized_users=["me"])
    routed = router.route(
        "workflow_run",
        {
            "repository": {"full_name": "octo/repo"},
            "workflow_run": {"head_branch": "issue-15", "pull_requests": []},
        },
        "d-1",
    )
    assert routed is not None  # CI status carries no human instruction


def test_router_pr_close_bypasses_authz_for_cleanup():
    router = Router(events=[], authorized_users=["me"])
    routed = router.route(
        "pull_request",
        {
            "action": "closed",
            "repository": {"full_name": "octo/repo"},
            "sender": {"login": "attacker"},
            "pull_request": {"number": 20, "merged": True},
        },
        "d-1",
    )
    assert routed is not None  # lifecycle auto-close must still fire


def test_router_drops_its_own_self_marked_reply():
    from the_loop.authz import SELF_COMMENT_MARKER

    router = Router(events=[], authorized_users=["me"])
    own_reply = _issue_comment_by("me")
    own_reply["comment"]["body"] = f"will-fix, pushed a fix.\n\n{SELF_COMMENT_MARKER}"
    assert router.route("issue_comment", own_reply, "d-1") is None
    # a same-author comment with no marker is still routed normally
    assert router.route("issue_comment", _issue_comment_by("me"), "d-2") is not None


def test_router_deduper_is_bounded_lru():
    deduper = Deduper(maxsize=2)
    deduper.add("a")
    deduper.add("b")
    assert "a" in deduper and "b" in deduper
    deduper.add("c")  # evicts the oldest
    assert "a" not in deduper and "c" in deduper
    deduper.discard("b")
    assert "b" not in deduper


# -- harness adapters (R4) ----------------------------------------------------

STUB_SOURCE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_RECORD"], "a") as f:
    f.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd()}) + "\\n")
if os.environ.get("STUB_EXIT", "0") != "0":
    sys.stderr.write("stub harness exploded\\n")
    sys.exit(int(os.environ["STUB_EXIT"]))
print(os.environ.get("STUB_STDOUT", "{}"))
"""


@pytest.fixture()
def stub_harness(tmp_path, monkeypatch):
    """A fake harness CLI that records its argv/cwd and prints canned JSON."""
    binary = tmp_path / "stub-harness"
    binary.write_text(STUB_SOURCE)
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    record = tmp_path / "record.jsonl"
    monkeypatch.setenv("STUB_RECORD", str(record))

    def calls():
        if not record.exists():
            return []
        lines = record.read_text().strip().splitlines()
        return [json.loads(line) for line in lines]

    return binary, calls


def test_claude_adapter_resume_invokes_cli_in_session_cwd(
    tmp_path, stub_harness, monkeypatch
):
    binary, calls = stub_harness
    monkeypatch.setenv("STUB_STDOUT", json.dumps({"session_id": "sess-1"}))
    workdir = tmp_path / "work"
    workdir.mkdir()
    adapter = ClaudeCodeAdapter(binary=str(binary), extra_args=["--extra-flag"])
    session = make_session(cwd=str(workdir))
    result = adapter.resume(session, "handle the event", timeout=30)
    assert result.ok, result.error
    (call,) = calls()
    assert call["argv"] == [
        "-p",
        "handle the event",
        "--resume",
        "sess-1",
        "--output-format",
        "json",
        "--extra-flag",
    ]
    assert Path(call["cwd"]).resolve() == workdir.resolve()


def test_claude_adapter_spawn_parses_new_session_id(stub_harness, monkeypatch):
    binary, calls = stub_harness
    monkeypatch.setenv("STUB_STDOUT", json.dumps({"session_id": "new-42"}))
    adapter = ClaudeCodeAdapter(binary=str(binary))
    result = adapter.spawn(WorkItemRef.parse(REF), "start work", cwd=".")
    assert result.ok and result.session_id == "new-42"
    (call,) = calls()
    assert "--resume" not in call["argv"]


def test_claude_adapter_reports_failure_with_stderr(stub_harness, monkeypatch):
    binary, _ = stub_harness
    monkeypatch.setenv("STUB_EXIT", "3")
    adapter = ClaudeCodeAdapter(binary=str(binary))
    result = adapter.resume(make_session(), "boom", timeout=30)
    assert not result.ok
    assert "stub harness exploded" in result.error


def test_claude_adapter_unavailable_binary_is_actionable():
    adapter = ClaudeCodeAdapter(binary="definitely-not-installed-xyz")
    assert adapter.is_available() is False
    result = adapter.resume(make_session(), "hello", timeout=5)
    assert not result.ok and "definitely-not-installed-xyz" in result.error


def test_cursor_adapter_resume_uses_chat_id(tmp_path, stub_harness, monkeypatch):
    binary, calls = stub_harness
    monkeypatch.setenv("STUB_STDOUT", json.dumps({"chat_id": "chat-9"}))
    adapter = CursorAgentAdapter(binary=str(binary))
    session = make_session(harness="cursor", session_id="chat-9")
    result = adapter.resume(session, "handle it", timeout=30)
    assert result.ok
    (call,) = calls()
    assert call["argv"][:4] == ["-p", "handle it", "--resume", "chat-9"]


def test_cursor_adapter_spawn_parses_chat_id(stub_harness, monkeypatch):
    binary, _ = stub_harness
    monkeypatch.setenv("STUB_STDOUT", json.dumps({"chat_id": "chat-77"}))
    adapter = CursorAgentAdapter(binary=str(binary))
    result = adapter.spawn(WorkItemRef.parse(REF), "start", cwd=".")
    assert result.ok and result.session_id == "chat-77"


# -- dispatcher (R3.2/R3.3, R5) -----------------------------------------------


class FakeAdapter:
    """In-process HarnessAdapter double recording calls and concurrency."""

    name = "claude"

    def __init__(self, delay=0.0, spawn_id="spawned-1"):
        self.delay = delay
        self.spawn_id = spawn_id
        self.calls = []
        self.spawns = []
        self._lock = threading.Lock()
        self._in_flight = 0
        self.max_in_flight = 0

    def is_available(self):
        return True

    def resume(self, session, prompt, timeout=None):
        with self._lock:
            self._in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self._in_flight)
        try:
            if self.delay:
                time.sleep(self.delay)
            with self._lock:
                self.calls.append((session.work_item.ref, prompt))
            return DispatchResult(ok=True, session_id=session.harness_session_id)
        finally:
            with self._lock:
                self._in_flight -= 1

    def spawn(self, work_item, prompt, cwd, timeout=None):
        with self._lock:
            self.spawns.append((work_item.ref, prompt, cwd))
        return DispatchResult(ok=True, session_id=self.spawn_id)


def make_dispatcher(tmp_path, adapter, **config_overrides):
    registry = SessionRegistry(tmp_path / "sessions")
    config = RoutingConfig(**config_overrides)
    dispatcher = Dispatcher(
        registry=registry, adapters={"claude": adapter}, config=config
    )
    return registry, dispatcher


def routed_issue_comment(delivery="d-1", number=15, body="please fix"):
    payload = payload_issue_comment(number=number, body=body)
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def test_dispatcher_resumes_matched_session_with_rendered_prompt(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session())
    dispatcher.handle(routed_issue_comment(body="the build is red"))
    assert wait_until(lambda: len(adapter.calls) == 1)
    dispatcher.stop()
    ref, prompt = adapter.calls[0]
    assert ref == REF
    assert REF in prompt and "issue_comment" in prompt
    assert "the build is red" in prompt  # payload excerpt is embedded
    assert "UNTRUSTED" in prompt  # ...and marked as data, not instructions
    found = registry.find_by_work_item(REF)
    assert found is not None and found.last_event_at
    assert "d-1" in found.recent_deliveries


def test_dispatcher_serializes_events_for_one_session_in_order(tmp_path):
    adapter = FakeAdapter(delay=0.03)
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session())
    for i in range(3):
        dispatcher.handle(routed_issue_comment(delivery=f"d-{i}", body=f"event {i}"))
    assert wait_until(lambda: len(adapter.calls) == 3)
    dispatcher.stop()
    bodies = [prompt for _, prompt in adapter.calls]
    assert [f"event {i}" in body for i, body in enumerate(bodies)] == [True] * 3
    assert adapter.max_in_flight == 1  # same session never dispatches concurrently


def test_dispatcher_dispatches_different_sessions_in_parallel(tmp_path):
    adapter = FakeAdapter(delay=0.2)
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session(ref="github:octo/repo#1", session_id="s1"))
    registry.register(make_session(ref="github:octo/repo#2", session_id="s2"))
    dispatcher.handle(routed_issue_comment(delivery="d-1", number=1))
    dispatcher.handle(routed_issue_comment(delivery="d-2", number=2))
    assert wait_until(lambda: len(adapter.calls) == 2)
    dispatcher.stop()
    assert adapter.max_in_flight == 2  # both sessions were in flight together


def test_dispatcher_drops_unmatched_event_by_default(tmp_path):
    adapter = FakeAdapter()
    _, dispatcher = make_dispatcher(tmp_path, adapter)  # empty registry
    dispatcher.handle(routed_issue_comment())
    dispatcher.stop()
    assert adapter.calls == [] and adapter.spawns == []


def test_dispatcher_spawns_and_registers_when_configured(tmp_path):
    adapter = FakeAdapter(spawn_id="fresh-9")
    registry, dispatcher = make_dispatcher(
        tmp_path, adapter, spawn_on_unmatched="always"
    )
    dispatcher.handle(routed_issue_comment())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "fresh-9"


def routed_labeled_issue(delivery="l-1", number=15, labeled=True):
    payload = {
        "action": "labeled",
        "label": {"name": LABEL if labeled else "bug"},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": number},
    }
    return RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=labeled,
    )


def test_dispatcher_labeled_mode_spawns_only_for_labeled_items(tmp_path):
    adapter = FakeAdapter(spawn_id="auto-1")
    registry, dispatcher = make_dispatcher(
        tmp_path, adapter, spawn_on_unmatched="labeled"
    )
    # An unlabelled unmatched event does nothing (owner scenario 1).
    dispatcher.handle(routed_labeled_issue(delivery="u-1", labeled=False))
    # A labelled one spawns + registers a session (owner scenario 2).
    dispatcher.handle(routed_labeled_issue(delivery="l-1", labeled=True))
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
    assert len(adapter.spawns) == 1  # only the labelled event spawned
    found = registry.find_by_work_item(REF)
    assert found is not None and found.harness_session_id == "auto-1"


def test_dispatcher_labeled_spawn_prompt_kicks_off_work_on(tmp_path):
    adapter = FakeAdapter()
    _, dispatcher = make_dispatcher(tmp_path, adapter, spawn_on_unmatched="labeled")
    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
    _, prompt, _ = adapter.spawns[0]
    assert "/the-loop:work-on" in prompt and REF in prompt


def test_dispatcher_always_mode_still_spawns_regardless_of_label(tmp_path):
    adapter = FakeAdapter()
    _, dispatcher = make_dispatcher(tmp_path, adapter, spawn_on_unmatched="always")
    dispatcher.handle(routed_labeled_issue(labeled=False))  # unlabelled
    assert wait_until(lambda: len(adapter.spawns) == 1)  # 'always' ignores the label
    dispatcher.stop()


def test_dispatcher_processes_duplicate_delivery_at_most_once(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session())
    dispatcher.handle(routed_issue_comment(delivery="dup-1"))
    dispatcher.handle(routed_issue_comment(delivery="dup-1"))
    assert wait_until(lambda: len(adapter.calls) >= 1)
    time.sleep(0.1)  # give a would-be duplicate time to (wrongly) dispatch
    dispatcher.stop()
    assert len(adapter.calls) == 1


def test_dispatcher_skips_session_whose_adapter_is_unknown(tmp_path, caplog):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session(harness="cursor"))  # no cursor adapter wired
    dispatcher.handle(routed_issue_comment())
    dispatcher.stop()
    assert adapter.calls == []


def routed_pr_closed(
    delivery="c-1",
    number=16,
    branch="claude/github-issue-15-x",
    body="Closes #15",
    merged=True,
):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": body,
            "merged": merged,
        },
    }
    return RoutedEvent(
        event="pull_request",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("pull_request", payload),
        payload=payload,
    )


def test_dispatcher_auto_closes_session_on_pr_close(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session())  # session for the issue #15
    dispatcher.handle(routed_pr_closed())  # PR #16 closes, links issue #15
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is None  # auto-closed
    assert registry.list_sessions(status="closed")  # persisted as closed
    assert adapter.calls == []  # closed, not resumed


def test_dispatcher_pr_close_never_spawns(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(
        tmp_path, adapter, spawn_on_unmatched="always"
    )
    dispatcher.handle(routed_pr_closed())  # no session registered
    dispatcher.stop()
    assert adapter.spawns == []  # never spawn a session to handle a close


def test_dispatcher_still_resumes_on_pr_events_that_are_not_close(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(tmp_path, adapter)
    registry.register(make_session())
    open_pr = routed_pr_closed(delivery="o-1", merged=False)
    open_pr.action = "synchronize"  # a non-close PR event still routes normally
    dispatcher.handle(open_pr)
    assert wait_until(lambda: len(adapter.calls) == 1)
    dispatcher.stop()
    assert registry.find_by_work_item(REF) is not None  # not closed


# -- `the-loop sessions` command (R2.2) ----------------------------------------


def run_cli(argv):
    from the_loop.cli import main

    return main(argv)


def test_sessions_command_is_registered():
    from the_loop.commands import iter_commands

    assert "sessions" in {c.name for c in iter_commands()}


def test_sessions_command_register_list_close_roundtrip(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    rc = run_cli(
        [
            "sessions",
            "register",
            "--work-item",
            REF,
            "--harness",
            "claude",
            "--harness-session-id",
            "sess-1",
            "--cwd",
            str(tmp_path),
            "--registry-dir",
            registry_dir,
        ]
    )
    assert rc == 0
    rc = run_cli(
        ["sessions", "list", "--registry-dir", registry_dir, "--format", "json"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out.splitlines()[-1])
    assert payload[0]["workItem"]["ref"] == REF
    assert payload[0]["status"] == "active"
    rc = run_cli(
        ["sessions", "close", "--work-item", REF, "--registry-dir", registry_dir]
    )
    assert rc == 0
    rc = run_cli(
        ["sessions", "list", "--registry-dir", registry_dir, "--format", "json"]
    )
    payload = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert payload[0]["status"] == "closed"


def test_sessions_command_duplicate_register_fails_without_force(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    base = [
        "sessions",
        "register",
        "--work-item",
        REF,
        "--harness",
        "claude",
        "--harness-session-id",
    ]
    tail = ["--cwd", str(tmp_path), "--registry-dir", registry_dir]
    assert run_cli(base + ["one"] + tail) == 0
    assert run_cli(base + ["two"] + tail) != 0  # refused: one item, one session
    assert run_cli(base + ["two"] + tail + ["--force"]) == 0


def test_sessions_command_close_missing_session_errors(tmp_path):
    rc = run_cli(
        [
            "sessions",
            "close",
            "--work-item",
            REF,
            "--registry-dir",
            str(tmp_path / "empty"),
        ]
    )
    assert rc != 0


def test_sessions_command_table_output(tmp_path, capsys):
    registry_dir = str(tmp_path / "sessions")
    run_cli(
        [
            "sessions",
            "register",
            "--work-item",
            REF,
            "--harness",
            "cursor",
            "--harness-session-id",
            "chat-1",
            "--cwd",
            str(tmp_path),
            "--registry-dir",
            registry_dir,
        ]
    )
    capsys.readouterr()
    assert run_cli(["sessions", "list", "--registry-dir", registry_dir]) == 0
    out = capsys.readouterr().out
    assert "Work item" in out and REF in out and "cursor" in out


# -- config hot reload (issue-34 review) --------------------------------------


def test_dispatcher_reload_swaps_policy_and_templates_keeps_dedup(tmp_path):
    adapter = FakeAdapter()
    registry, dispatcher = make_dispatcher(
        tmp_path, adapter, spawn_on_unmatched="never"
    )
    dispatcher.deduper.add("keep-me")  # in-memory dedup must survive a reload
    tmpl = tmp_path / "evt.md"
    tmpl.write_text("RELOADED $work_item")

    dispatcher.reload(
        RoutingConfig(
            spawn_on_unmatched="always",
            registry_dir="ignored-on-reload",
            prompt_template=str(tmpl),
        )
    )
    dispatcher.stop()

    # soft policy took effect
    assert dispatcher.config.spawn_on_unmatched == "always"
    assert dispatcher._should_spawn(routed_labeled_issue(labeled=False)) is True
    # prompt template reloaded
    rendered = dispatcher._render_prompt(
        routed_issue_comment(), WorkItemRef.parse(REF), dispatcher._event_template
    )
    assert rendered.startswith("RELOADED github:octo/repo#15")
    # infrastructure preserved (change needs a restart)
    assert "keep-me" in dispatcher.deduper  # dedup cache kept
    assert dispatcher.registry is registry  # registryDir change ignored
    assert "claude" in dispatcher.adapters  # adapters rebuilt from harnessArgs


def test_read_gh_webhook_config_strict_vs_lenient(tmp_path, monkeypatch):
    from the_loop.commands import gh_webhook

    cfg = tmp_path / "config.yaml"
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cfg)

    # missing file: lenient => {}, strict => raises
    assert gh_webhook._read_gh_webhook_config(strict=False) == {}
    with pytest.raises(FileNotFoundError):
        gh_webhook._read_gh_webhook_config(strict=True)

    # unparseable: lenient => {} (keep defaults), strict => raises (keep previous)
    cfg.write_text("webhooks: [unclosed\n")
    assert gh_webhook._read_gh_webhook_config(strict=False) == {}
    with pytest.raises(Exception):
        gh_webhook._read_gh_webhook_config(strict=True)


def _write_webhook_config(path, policy, sessions_dir):
    path.write_text(
        "webhooks:\n"
        "  ghWebhook:\n"
        "    events: []\n"
        "    routing:\n"
        f"      spawnOnUnmatched: {policy}\n"
        f"      registryDir: {sessions_dir}\n"
    )


def test_webhook_hot_reload_applies_on_next_event(tmp_path, monkeypatch):
    from the_loop.commands import gh_webhook

    cfg = tmp_path / "config.yaml"
    _write_webhook_config(cfg, "never", tmp_path / "sessions")
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cfg)

    on_event, dispatcher, _ = gh_webhook._build_routing(
        gh_webhook._read_gh_webhook_config()
    )
    assert dispatcher.config.spawn_on_unmatched == "never"

    # edit the config while "running"; the next received event applies it
    _write_webhook_config(cfg, "always", tmp_path / "sessions")
    on_event(
        "issues",
        {"repository": {"full_name": "octo/repo"}, "issue": {"number": 1}},
        "d-1",
    )
    dispatcher.stop()

    assert dispatcher.config.spawn_on_unmatched == "always"
