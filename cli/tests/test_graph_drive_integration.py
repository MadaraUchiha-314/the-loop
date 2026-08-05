"""The graph runs the PDLC — dispatcher integration (issue-148).

Feature: graph state is resolved before anything is delivered, and a human
gate classifies an event before the session reacts to it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path


from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.control import ControlConfig
from the_loop.graphlink import GraphContext
from the_loop.sessions import SessionRegistry, Session, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#15"


def _ctx(
    current_node="implementation",
    phase="implementation",
    status="in-progress",
    reason="",
    messages=(),
    next_command="execute-tasks",
    actor="agent",
):
    return GraphContext(
        current_node=current_node,
        phase=phase,
        status=status,
        reason=reason,
        messages=tuple(messages),
        next_command=next_command,
        actor=actor,
    )


GATE_CTX = _ctx(
    current_node="design-approval",
    phase="",
    status="waiting",
    reason="awaiting a human",
    next_command="",
    actor="human",
)


class _SeqLink:
    """A graph link that records call order — the seam under test is *when*
    the dispatcher talks to the graph relative to the harness."""

    def __init__(self, ctx=None, report=None):
        self.ctx = ctx
        self.report = report
        self.seq = []

    def context(self, work_item, cwd):
        self.seq.append("context")
        return self.ctx

    def on_event(self, work_item, cwd, routed):
        self.seq.append("advance")
        return self.report

    def on_spawn(self, work_item, cwd, session_id="", runner=""):
        self.seq.append(("spawn", session_id, runner))

    def on_close(self, work_item, cwd):
        self.seq.append("close")


class _Report:
    outcome = "approved"
    status = "pass"


class _SeqTmux(FakeTmux):
    """The tmux runner hosts every delivery and spawn (issue-156), so *it* is
    the harness side of the ordering under test: both count as "deliver"."""

    def __init__(self, seq):
        super().__init__()
        self.seq = seq
        self.prompts = []

    def deliver(self, session, prompt, timeout=None):
        self.seq.append("deliver")
        self.prompts.append(prompt)
        return super().deliver(session, prompt, timeout)

    def spawn(
        self, work_item, adapter, prompt, cwd, session_id, timeout=None, resume=False
    ):
        self.seq.append("deliver")
        self.prompts.append(prompt)
        return super().spawn(
            work_item, adapter, prompt, cwd, session_id, timeout=timeout, resume=resume
        )


def _wait(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _dispatcher(tmp_path, link, **overrides):
    registry = SessionRegistry(tmp_path / "sessions")
    overrides.setdefault("control", ControlConfig(require_start_command=False))
    tmux = _SeqTmux(link.seq)
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(**overrides),
        tmux_runner=tmux,
    )
    dispatcher.graphlink = link
    return registry, dispatcher, tmux


def _session(cwd="."):
    return Session(
        work_item=WorkItemRef.parse(REF),
        harness="claude",
        harness_session_id="sess-1",
        cwd=str(Path(cwd).resolve()),
    )


def _comment(delivery="d-1", body="looks good"):
    payload = {
        "action": "created",
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
        "comment": {"body": body, "user": {"login": "octo"}},
    }
    return RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id=delivery,
        work_items=extract_work_items("issue_comment", payload),
        payload=payload,
    )


def test_an_ordinary_event_is_delivered_then_advanced(tmp_path):
    """Feature: consult-before-deliver (issue-148)

    Scenario: an event reaches an item that is NOT at a human gate
      Given a session working an item whose current node is agent-owned
      When a comment event is dispatched to it
      Then the graph context is resolved before delivery
      And the prompt carries the process-state block
      And the graph advances only AFTER the delivery succeeded

    Requirement: docs/specs/issue-148/requirements.md R3.1, R4.3
    """
    link = _SeqLink(ctx=_ctx())
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_comment())
    assert _wait(lambda: "advance" in link.seq)
    dispatcher.stop()
    assert link.seq == ["context", "deliver", "advance"]
    prompt = tmux.prompts[0]
    assert "the-loop process state for issue-15" in prompt
    assert "node: implementation" in prompt
    assert "`the-loop graph complete issue-15`" in prompt


def test_a_human_gate_classifies_the_event_before_delivery(tmp_path):
    """Feature: gate-first event routing (issue-148, D4)

    Scenario: a comment arrives while the item waits at a human gate
      Given a session whose item is parked at a human-approval node
      When a comment event is dispatched to it
      Then the graph advances (classifies) BEFORE the delivery
      And the delivered prompt carries the gate's verdict
      And the graph is not advanced a second time after delivery

    Requirement: docs/specs/issue-148/requirements.md R4.1
    """
    link = _SeqLink(ctx=GATE_CTX, report=_Report())
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_comment(body="approved, ship it"))
    assert _wait(lambda: "deliver" in link.seq)
    dispatcher.stop()
    assert link.seq == ["context", "advance", "context", "deliver"]
    assert "classified by the gate first: approved" in tmux.prompts[0]


def test_an_unclassifiable_event_at_a_gate_is_still_delivered(tmp_path):
    """Feature: gate-first never becomes an event filter (issue-148, R4.2)

    Scenario: a comment the gate cannot classify arrives at a human gate
      Given an item parked at a human gate
      And the gate's classification resolves nothing (unauthorized/indecisive)
      When the event is dispatched
      Then it is still delivered, with the gate still waiting
      And the prompt carries no verdict line

    Requirement: docs/specs/issue-148/requirements.md R4.2, abuse case 1
    """
    link = _SeqLink(ctx=GATE_CTX, report=None)  # advance ran, nothing resolved
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_comment(body="lgtm from a stranger"))
    assert _wait(lambda: "deliver" in link.seq)
    dispatcher.stop()
    assert "deliver" in link.seq and link.seq.index("advance") < link.seq.index(
        "deliver"
    )
    assert "classified by the gate first" not in tmux.prompts[0]
    assert "status: waiting" in tmux.prompts[0]


def test_a_graph_fault_never_costs_a_delivery(tmp_path):
    """Feature: fail-open delivery (issue-148, R3.3/R7.3)

    Scenario: the graph cannot be consulted at all
      Given a graph link whose context resolution yields nothing
      When an event is dispatched
      Then the event is still delivered, with no process-state block

    Requirement: docs/specs/issue-148/requirements.md R3.3
    """
    link = _SeqLink(ctx=None)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    registry.register(_session())
    dispatcher.handle(_comment())
    assert _wait(lambda: "deliver" in link.seq)
    dispatcher.stop()
    assert "the-loop process state" not in tmux.prompts[0]
    assert "looks good" in tmux.prompts[0]


def test_a_spawn_reads_context_before_render_and_enters_after(tmp_path):
    """Feature: spawn resumes at the current node (issue-148, D5)

    Scenario: a session is respawned for an item already mid-graph
      Given an unmatched labelled item whose graph pointer is mid-flight
      When the dispatcher spawns a session for it
      Then the spawn prompt tells the session to resume at the current node
      And the graph is entered (on_spawn) only after the spawn succeeded
      And the session id is recorded with the binding

    Requirement: docs/specs/issue-148/requirements.md R3.2, R7.2
    """
    link = _SeqLink(ctx=_ctx())
    registry, dispatcher, tmux = _dispatcher(
        tmp_path, link, spawn_on_unmatched="always"
    )
    dispatcher.handle(_comment())
    assert _wait(lambda: any(isinstance(s, tuple) for s in link.seq))
    dispatcher.stop()
    deliver_at = link.seq.index("deliver")
    spawn_at = next(i for i, s in enumerate(link.seq) if isinstance(s, tuple))
    assert deliver_at < spawn_at  # writes only after the spawn succeeded
    verb, bound_id, runner = link.seq[spawn_at]
    assert verb == "spawn" and runner == "tmux"
    # The dispatcher pre-assigns the session id (a uuid4, issue-156): the id
    # recorded with the binding is the one the registered session carries.
    session = registry.find_by_work_item(REF)
    assert session is not None and bound_id == session.harness_session_id
    assert bound_id  # a real pre-assigned id, not an empty default
    prompt = tmux.prompts[0]
    assert "resume with: `/the-loop:execute-tasks issue-15`" in prompt
    assert "requirements → design → tasks" not in prompt  # R6.3: no prose flow


def test_a_fresh_spawn_gets_the_start_prompt_unchanged(tmp_path):
    """Feature: out-of-graph and fresh items degrade cleanly (issue-148, R3.4)

    Scenario: a spawn for an item with no graph state
      Given the graph has no context for the item
      When the dispatcher spawns a session for it
      Then the prompt says to start the loop and carries no process-state block

    Requirement: docs/specs/issue-148/requirements.md R3.4
    """
    link = _SeqLink(ctx=None)
    registry, dispatcher, tmux = _dispatcher(
        tmp_path, link, spawn_on_unmatched="always"
    )
    dispatcher.handle(_comment())
    assert _wait(lambda: tmux.prompts)
    dispatcher.stop()
    prompt = tmux.prompts[0]
    assert "/the-loop:work-on" in prompt
    assert "the-loop process state" not in prompt


def test_closing_a_session_marks_the_graph_binding(tmp_path):
    """Feature: the session binding follows the session (issue-148, D6)

    Scenario: a session is closed
      Given a registered session for a work item
      When the dispatcher closes it
      Then the graph link is told, so `session: inherit` gates fall back

    Requirement: docs/specs/issue-148/requirements.md R5.2
    """
    link = _SeqLink(ctx=None)
    registry, dispatcher, tmux = _dispatcher(tmp_path, link)
    session = _session()
    registry.register(session)
    dispatcher.close_session(session)
    assert "close" in link.seq


def test_the_complete_verb_emits_one_json_envelope(tmp_path):
    """Feature: the completion claim is a CLI verb (issue-148, D1)

    Scenario: a session claims its node's work is done
      Given a work item mid-graph in a checkout
      When `the-loop graph complete <id>` runs in that checkout
      Then stdout is one JSON envelope naming the node, outcome and pointer
      And the exit code is 0 whether or not the pointer moved

    Requirement: docs/specs/issue-148/requirements.md R1.3
    """
    import subprocess
    import sys

    spec = tmp_path / "docs" / "specs" / "issue-9"
    spec.mkdir(parents=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "the_loop",
            "graph",
            "--repo",
            str(tmp_path),
            "complete",
            "issue-9",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    envelope = json.loads(proc.stdout)
    assert envelope["reason"] == "not-started" and envelope["moved"] is False
