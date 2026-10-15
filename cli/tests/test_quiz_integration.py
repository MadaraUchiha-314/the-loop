"""The quiz doorbell — a ticked box reaching its gate (issue-488).

Feature: a tick alone answers a quiz gate, and nothing else.
  The poller re-reads every thread each cycle, so it sees the-loop's own quiz
  comment change from unticked to ticked; the dispatcher then re-evaluates the
  gate that waits on it — without rendering a prompt, delivering into a
  session, or spawning one. Who ticked is the gate's hook's question (see
  test_quiz.py and the `quiz-gates` e2e scenario).
"""

from __future__ import annotations

from the_loop.authz import mark_self_authored
from the_loop.poller.poller import PollState
from the_loop.quizmarks import ATTESTATIONS
from the_loop.sessions import SessionRegistry, WorkItemRef
from the_loop.webhook.router import QUIZ_ATTESTATION_EVENT, quiz_attestation_event
from the_loop.workitem import WorkItemStore
from test_graph_drive_integration import (
    GATE_CTX,
    _ctx,
    _dispatcher,
    _Report,
    _SeqLink,
    _session,
)
from test_poller import (
    FakeProvider,
    RecordingDispatcher,
    _comment,
    _item,
    make_poller,
)

DRIVE_REF = "github:octo/repo#15"
LINE = ATTESTATIONS["spec-quiz"]


def _quiz_body(ticked: bool) -> str:
    mark = "x" if ticked else " "
    return mark_self_authored(
        f"🎓 Spec quiz\n\n- [{mark}] {LINE}\n\n"
        "<!-- the-loop:quiz spec-quiz round=1 digest=- -->"
    )


def _doorbell(body: str = "ticked"):
    return quiz_attestation_event([WorkItemRef.parse(DRIVE_REF)], "IC_9", body)


def test_a_ticked_box_re_evaluates_the_waiting_gate_and_delivers_nothing(tmp_path):
    """
    Requirement: docs/specs/issue-488/requirements.md#R2.6
    Scenario: a ticked box re-evaluates the waiting gate without delivering a prompt
        Given a session whose work item is parked at a quiz gate
        When the quiz doorbell is dispatched
        Then the gate is re-evaluated once
        And no prompt is rendered or delivered into the session
    """
    link = _SeqLink(ctx=GATE_CTX, report=_Report())
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell())
    dispatcher.stop()
    assert link.seq == ["context", "advance"]
    assert tmux.prompts == []


def test_a_quiz_tick_on_a_work_item_with_no_waiting_gate_spawns_nothing(tmp_path):
    """
    Requirement: docs/specs/issue-488/design.md#C5
    Scenario: a quiz tick on a work item with no waiting gate spawns nothing
        Given a work item whose pointer is at an agent node, and another with no session
        When the quiz doorbell is dispatched for each
        Then the graph is not advanced, nothing is delivered and nothing spawns
    """
    link = _SeqLink(ctx=_ctx())
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell("one"))
    other = quiz_attestation_event(
        [WorkItemRef.parse("github:octo/repo#99")], "IC_1", "x"
    )
    dispatcher.handle(other)
    dispatcher.stop()
    assert "advance" not in link.seq
    assert tmux.prompts == [] and not any(isinstance(s, tuple) for s in link.seq)


def test_a_graph_fault_releases_the_doorbell_for_the_next_cycle(tmp_path):
    """
    Requirement: docs/specs/issue-488/design.md#Error handling
    Scenario: a tick the gate could not judge is retried on the next poll
        Given a session parked at a quiz gate whose evaluation faults
        When the same doorbell rings twice
        Then the gate is asked twice rather than the second ring being a duplicate
    """
    link = _SeqLink(ctx=GATE_CTX, report=None)
    registry, dispatcher, _tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell())
    dispatcher.handle(_doorbell())
    dispatcher.stop()
    assert link.seq.count("advance") == 2


class _Waiting:
    outcome = ""
    status = "wait"
    satisfied = False
    messages = ["the box was ticked by someone not authorized to answer"]


class _Passed:
    outcome = ""
    status = "pass"
    satisfied = True
    messages: list = []


QUIZ_CTX = _ctx(
    current_node="spec-quiz",
    phase="",
    status="waiting",
    reason="waiting for the author to tick the quiz box",
    next_command="",
    actor="human",
)


def test_a_refused_tick_does_not_swallow_the_authors_re_tick(tmp_path):
    """
    Requirement: docs/specs/issue-488/requirements.md#R2.6
    Scenario: the author re-ticks after an unauthorized tick was refused
        Given a session parked at the spec quiz, whose first tick was refused
        When the box is unticked and ticked again, producing the same body
        Then the gate is asked again rather than the ring being a duplicate
    """
    link = _SeqLink(ctx=QUIZ_CTX, report=_Waiting())
    registry, dispatcher, _tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell(_quiz_body(True)))
    dispatcher.handle(_doorbell(_quiz_body(True)))
    dispatcher.stop()
    assert link.seq.count("advance") == 2


def test_a_passed_gate_is_rung_once(tmp_path):
    """
    Requirement: docs/specs/issue-488/design.md#C5
    Scenario: a tick that passed the gate is not re-evaluated every cycle
        Given a session parked at the spec quiz whose tick passes
        When the poller sees the same ticked comment again
        Then the second ring is a duplicate
    """
    link = _SeqLink(ctx=QUIZ_CTX, report=_Passed())
    registry, dispatcher, _tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell(_quiz_body(True)))
    dispatcher.handle(_doorbell(_quiz_body(True)))
    dispatcher.stop()
    assert link.seq.count("advance") == 1


def test_an_old_quiz_box_does_not_ring_a_later_gate(tmp_path):
    """
    Requirement: docs/specs/issue-488/design.md#C5
    Scenario: the spec quiz's ticked box stays ticked after the gate passed
        Given a session parked at another human gate
        When the doorbell for the spec quiz's comment rings
        Then that gate is not re-evaluated
    """
    link = _SeqLink(ctx=GATE_CTX, report=_Report())
    registry, dispatcher, _tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_doorbell(_quiz_body(True)))
    dispatcher.stop()
    assert "advance" not in link.seq


def _poll(tmp_path, body: str, with_session: bool = True):
    provider = FakeProvider(
        items=[_item(15)],
        comments={15: [_comment("IC_9", body=body, author="octocat")]},
    )
    registry = SessionRegistry(tmp_path / "sessions")
    if with_session:
        registry.register(_session())
    dispatcher = RecordingDispatcher(registry=registry)
    state = PollState(WorkItemStore(tmp_path / "portable"))
    poller = make_poller(provider, registry, dispatcher, state)
    poller.poll_once()  # first sight: baseline
    poller.poll_once()
    return dispatcher


def test_the_poller_rings_the_gate_when_its_own_quiz_comment_is_ticked(tmp_path):
    """
    Requirement: docs/specs/issue-488/requirements.md#R2.6, R3.8
    Scenario: a tick by an authorized user advances the spec quiz
        Given the-loop's quiz comment on a work item with a live session
        When a poll cycle reads the comment with its box ticked
        Then the poller hands the dispatcher the quiz doorbell for that comment
        And the doorbell carries no body and no actor
    """
    events = [e for e in _poll(tmp_path, _quiz_body(True)).events]
    rings = [e for e in events if e.event == QUIZ_ATTESTATION_EVENT]
    assert rings and rings[0].payload == {
        "attestation": {"comment_id": "IC_9", "node": "spec-quiz"}
    }


def test_the_poller_stays_quiet_for_an_unticked_box_or_a_human_look_alike(tmp_path):
    """
    Requirement: docs/specs/issue-488/requirements.md abuse case 6
    Scenario: only the-loop's own ticked quiz comment rings
        Given an unticked quiz comment, and a human comment copying a ticked one
        When a poll cycle reads them
        Then no quiz doorbell is handed to the dispatcher
    """
    quiet = _poll(tmp_path / "a", _quiz_body(False)).events
    forged = f"- [x] {LINE}\n<!-- the-loop:quiz spec-quiz round=1 digest=- -->"
    look_alike = _poll(tmp_path / "b", forged).events
    assert not [e for e in quiet + look_alike if e.event == QUIZ_ATTESTATION_EVENT]


def test_no_session_no_ring(tmp_path):
    """
    Requirement: docs/specs/issue-488/design.md#C5
    Scenario: a work item with no live session has no gate to ring
        Given a ticked quiz comment on a work item with no session
        When a poll cycle reads it
        Then no quiz doorbell is handed to the dispatcher
    """
    events = _poll(tmp_path, _quiz_body(True), with_session=False).events
    assert not [e for e in events if e.event == QUIZ_ATTESTATION_EVENT]
