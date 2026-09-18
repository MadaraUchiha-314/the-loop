"""Integration: a closed work item is announced on every channel (issue-378 R3).

The real :class:`Dispatcher` handling a routed close event, with a lifecycle
publisher that records what it was handed **and** what the declaration store
still said at that moment — the ordering is the requirement (R3.1, A7): the
announcement has to reach the room the item was worked in, and the room is
forgotten by the same closure.

Spec: docs/specs/issue-378/testing-plan.md T6.
"""

from __future__ import annotations

from conftest import FakeTmux
from test_reactions_integration import REF, make_control_dispatcher, wait_until
from the_loop.sessions import Session, WorkItemRef
from the_loop.webhook.dispatcher import RoutedEvent
from the_loop.webhook.router import extract_work_items

PR_REF = "github:octo/repo#16"
ROOM = "slack@C0TMP378"


class Recorder:
    """The `lifecycle` callable the daemons build; here it also snapshots the
    declaration store so the test can prove the publish came before the clear."""

    def __init__(self, dispatcher):
        self.dispatcher = dispatcher
        self.events = []

    def __call__(self, event_type, work_item, text, detail):
        declared = [r.ref for r in self.dispatcher.channel_store.list(work_item)]
        self.events.append((event_type, work_item, text, dict(detail), declared))


def routed_close(kind="issues", number=15, merged=False, delivery="close-1"):
    payload = {
        "action": "closed",
        "repository": {"full_name": "octo/repo"},
        "sender": {"login": "octocat"},
    }
    if kind == "issues":
        payload["issue"] = {"number": number, "state_reason": "completed"}
    else:
        payload["pull_request"] = {
            "number": number,
            "merged": merged,
            "head": {"ref": "topic"},
        }
    return RoutedEvent(
        event=kind,
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items(kind, payload),
        payload=payload,
    )


def _dispatcher(tmp_path, monkeypatch):
    tmux = FakeTmux()
    dispatcher, runner = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    recorder = Recorder(dispatcher)
    dispatcher.lifecycle = recorder
    return dispatcher, recorder, tmux


def test_a_closed_issue_is_announced_before_its_room_is_forgotten(
    tmp_path, monkeypatch
):
    """
    Feature: a closed work item is announced on every channel
      Scenario: the ticket is closed on GitHub
        Given work item 15 is armed and declared into a room
        When an issues `closed` event for it arrives
        Then `work-item.closed` is published with state, reason and the closer
        And at that moment the room is still the work item's
        And afterwards the declaration is cleared

    Requirement: docs/specs/issue-378/requirements.md R3.1, R3.2
    """
    dispatcher, recorder, _ = _dispatcher(tmp_path, monkeypatch)
    ref = WorkItemRef.parse(REF)
    dispatcher.control_store.record(ref, "start", actor="octocat")
    dispatcher.channel_store.add(ref, ROOM, actor="octocat", source="cli")

    dispatcher.handle(routed_close())
    assert wait_until(lambda: dispatcher.control_store.ended(ref) is not None)
    dispatcher.stop()

    ((event_type, work_item, text, detail, declared),) = recorder.events
    assert event_type == "work-item.closed"
    assert work_item == REF
    assert detail["state"] == "closed"
    assert detail["reason"] == "issue-closed"
    assert detail["actor"] == "octocat"
    assert detail["kind"] == "issue"
    assert declared == [ROOM], "published while the room was still the item's"
    assert dispatcher.channel_store.list(ref) == []
    assert "closed" in text and REF in text


def test_a_merged_pull_request_that_is_the_work_item_is_announced_as_merged(
    tmp_path, monkeypatch
):
    """R3.2: the state is `merged` and the kind a pull request."""
    dispatcher, recorder, _ = _dispatcher(tmp_path, monkeypatch)
    pr = WorkItemRef.parse(PR_REF)
    dispatcher.control_store.record(pr, "start", actor="octocat")

    dispatcher.handle(routed_close(kind="pull_request", number=16, merged=True))
    assert wait_until(lambda: dispatcher.control_store.ended(pr) is not None)
    dispatcher.stop()

    ((event_type, work_item, _, detail, _),) = recorder.events
    assert (event_type, work_item) == ("work-item.closed", PR_REF)
    assert detail["state"] == "merged"
    assert detail["reason"] == "pr-merged"
    assert detail["kind"] == "pull-request"


def test_a_delivering_pull_requests_end_announces_nothing(tmp_path, monkeypatch):
    """R3.3: the pull request delivers work item 15; its end is not a closure."""
    dispatcher, recorder, _ = _dispatcher(tmp_path, monkeypatch)
    ref = WorkItemRef.parse(REF)
    dispatcher.registry.register(
        Session(
            work_item=ref,
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
            tmux_target="loop-github-octo-repo-15",
        )
    )
    endpoint = dispatcher.registry.link_pull_request(ref, PR_REF)
    assert endpoint is not None

    dispatcher.handle(routed_close(kind="pull_request", number=16, merged=True))
    assert wait_until(
        lambda: all(
            not pr.is_live
            for pr in (
                dispatcher.registry.find_by_work_item(ref)
                or Session(
                    work_item=ref, harness="claude", harness_session_id="", cwd=""
                )
            ).pull_requests
        )
    )
    dispatcher.stop()

    assert recorder.events == []


def test_a_dispatcher_without_a_publisher_closes_as_before(tmp_path, monkeypatch):
    """R3.5: `None` publishes nothing and the closure is still stamped."""
    tmux = FakeTmux()
    dispatcher, _ = make_control_dispatcher(tmp_path, tmux, monkeypatch)
    assert dispatcher.lifecycle is None
    ref = WorkItemRef.parse(REF)
    dispatcher.control_store.record(ref, "start", actor="octocat")

    dispatcher.handle(routed_close())
    assert wait_until(lambda: dispatcher.control_store.ended(ref) is not None)
    dispatcher.stop()


def test_an_untracked_issue_closing_announces_nothing(tmp_path, monkeypatch):
    """The closure is stamped only for a tracked item (issue-329); so is the event."""
    dispatcher, recorder, _ = _dispatcher(tmp_path, monkeypatch)

    dispatcher.handle(routed_close(number=99))
    dispatcher.stop()

    assert recorder.events == []
