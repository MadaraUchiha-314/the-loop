"""Unit tests for the stop check and the declared wait (issue-551, R3, R4.7, R4.8).

One test per step of the order in docs/specs/issue-551/design.md § "The stop
check", against the pure decision. Then the operation around it: what it
records, what a refusal carries, and whom it answers at all.
"""

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from the_loop import eventlog
from the_loop.api.app import create_app
from the_loop.cli import main
from the_loop.core import sessionstate, stopcheck
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.watchconfig import AsksConfig, WatchdogConfig
from the_loop.workitem import WorkItemRef

REF = "github:octo/repo#7"
FOREIGN = "github:octo/repo#8"
T0 = datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc)

#: A small graph in declaration order: a human gate, two agent nodes, the end.
NODES = {
    "spec": {"actor": "agent", "command": "create-design", "terminal": False},
    "gate": {"actor": "human", "command": "", "terminal": False},
    "build": {"actor": "agent", "command": "execute-tasks", "terminal": False},
    "done": {"actor": "agent", "command": "finish-tasks", "terminal": True},
    "sweep": {"actor": "code", "command": "", "terminal": True},
}


def report(pointer, **statuses):
    """A recomputed check report: every node passes unless ``statuses`` says so."""
    return {
        "workItem": "issue-7",
        "pointer": pointer,
        "nodes": [
            {
                "node": node,
                "status": statuses.get(node, "pass"),
                "messages": [f"{node} is unmet"] if node in statuses else [],
            }
            for node in NODES
        ],
    }


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def ev(minutes: float, event: str, **fields) -> dict:
    return {
        "ts": at(minutes).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "event": event,
        "work_item": REF,
        **fields,
    }


def session(*events, minutes: float = 10):
    return sessionstate.derive(
        events,
        now=at(minutes),
        watchdog=WatchdogConfig(),
        asks=AsksConfig(),
        work_item=REF,
    )


def decide(rep, *events, background_work=False, minutes: float = 10):
    return stopcheck.decide(
        rep, NODES, session(*events, minutes=minutes), background_work
    )


# -- step 1: the position cannot be resolved ---------------------------------------


@pytest.mark.parametrize(
    "rep", [None, {}, report(""), report("nowhere"), {"repoResolved": False}]
)
def test_an_unresolvable_position_is_allowed_as_inconclusive(rep):
    decision = decide(rep)
    assert (decision.verdict, decision.reason) == ("allow", "inconclusive")


# -- step 2: nobody owes agent work at the pointer ---------------------------------


def test_a_pointer_on_a_human_owned_node_is_allowed():
    decision = decide(report("gate", gate="wait"))
    assert (decision.verdict, decision.reason) == ("allow", "human-gate")
    assert (decision.node, decision.node_status) == ("gate", "wait")


@pytest.mark.parametrize("pointer", ["done", "sweep"])
def test_a_terminal_or_code_node_is_allowed_as_complete(pointer):
    decision = decide(report(pointer, **{pointer: "block"}))
    assert (decision.verdict, decision.reason) == ("allow", "complete")


# -- step 3: the nodes before the pointer ------------------------------------------


def test_an_agent_node_blocking_before_the_pointer_refuses_and_is_named():
    decision = decide(report("build", spec="block"))
    assert decision.verdict == "refuse"
    assert decision.node == "spec"
    assert decision.messages == ("spec is unmet",)


def test_a_human_gate_reporting_wait_before_the_pointer_counts_as_passed():
    """The P3 fix: an approved gate recomputes as `wait`, and disarmed the gate."""
    decision = decide(report("build", gate="wait", build="block"))
    assert decision.verdict == "refuse"
    assert decision.node == "build"


def test_a_human_gate_before_the_pointer_passes_whatever_it_reports():
    decision = decide(report("build", gate="block"))
    assert (decision.verdict, decision.reason) == ("allow", "exit-met")


def test_an_agent_node_past_the_pointer_is_not_judged():
    decision = decide(report("spec", build="block"))
    assert (decision.verdict, decision.reason) == ("allow", "exit-met")


# -- steps 4 and 5: the pointer's node passes, or waits ----------------------------


def test_a_passing_node_is_allowed_as_exit_met():
    decision = decide(report("build"))
    assert (decision.verdict, decision.reason) == ("allow", "exit-met")
    assert (decision.node, decision.node_status) == ("build", "pass")


def test_a_pointer_on_a_declared_skip_is_allowed_as_exit_met():
    decision = decide(report("build", build="skip"))
    assert (decision.verdict, decision.reason) == ("allow", "exit-met")


def test_a_waiting_node_is_allowed_as_graph_wait():
    decision = decide(report("build", build="wait"))
    assert (decision.verdict, decision.reason) == ("allow", "graph-wait")


# -- step 6: the pointer's node blocks ---------------------------------------------


def test_a_blocking_node_with_nothing_to_wait_on_is_refused():
    decision = decide(report("build", build="block"), ev(0, "session.turn_started"))
    assert decision.verdict == "refuse"
    assert (decision.node, decision.messages) == ("build", ("build is unmet",))


def test_an_open_ask_allows_the_stop():
    decision = decide(
        report("build", build="block"),
        ev(0, "session.turn_started"),
        ev(1, "session.awaiting_input", question="Which one?"),
    )
    assert (decision.verdict, decision.reason) == ("allow", "open-ask")


def test_an_answered_ask_no_longer_allows_the_stop():
    decision = decide(
        report("build", build="block"),
        ev(1, "session.awaiting_input", question="Which one?"),
        ev(2, "session.reply_sent"),
        ev(3, "session.turn_started"),
    )
    assert decision.verdict == "refuse"


def test_background_work_the_harness_reports_allows_the_stop():
    decision = decide(report("build", build="block"), background_work=True)
    assert (decision.verdict, decision.reason) == ("allow", "background-work")


def test_background_work_does_not_excuse_a_node_before_the_pointer():
    decision = decide(report("build", spec="block"), background_work=True)
    assert decision.verdict == "refuse" and decision.node == "spec"


# -- the operation: what is recorded, what a refusal carries -----------------------


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


@pytest.fixture
def bound(tmp_path, monkeypatch):
    """A registered session for REF, and the event log both sides use."""
    config = _config(tmp_path)
    layout = layout_from_config(config)
    SessionRegistry(layout.local_dir).register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    eventlog.configure("test", path=layout.event_log)
    monkeypatch.setattr(
        eventlog,
        "configure_from_file",
        lambda source: eventlog.configure(source, path=layout.event_log),
    )
    monkeypatch.setattr(
        "the_loop.commands.sessions_cmd._cli_config", lambda: config, raising=True
    )
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    return config


def standing(monkeypatch, rep):
    monkeypatch.setattr(stopcheck, "_standing", lambda session, work_item: (rep, NODES))


def recorded(config, event):
    path = layout_from_config(config).event_log
    return [e for e in eventlog.read_events(path) if e["event"] == event]


def test_an_allowed_stop_records_the_turns_end(bound, monkeypatch):
    standing(monkeypatch, report("build", build="wait"))
    answer = stopcheck.stop_check(REF, config=bound)
    assert answer["verdict"] == "allow" and answer["reason"] == "graph-wait"
    (ended,) = recorded(bound, "session.turn_ended")
    assert ended["work_item"] == REF
    assert (ended["node"], ended["node_status"], ended["reason"]) == (
        "build",
        "wait",
        "graph-wait",
    )


def test_a_refused_stop_records_nothing_and_says_how_to_go_on(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    answer = stopcheck.stop_check(REF, config=bound)
    assert answer["verdict"] == "refuse"
    assert answer["node"] == "build"
    assert answer["messages"] == ["build is unmet"]
    assert answer["command"] == "/the-loop:execute-tasks issue-7"
    assert recorded(bound, "session.turn_ended") == []
    text = answer["text"]
    assert "`build`" in text and "build is unmet" in text
    assert "/the-loop:execute-tasks issue-7" in text
    assert f"the-loop ask --work-item {REF}" in text
    assert f'the-loop wait --work-item {REF} --for "<what>" --until 30m' in text
    assert "background work" in text


def test_the_refusal_text_is_pinned(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    assert stopcheck.stop_check(REF, config=bound)["text"] == (
        "the-loop: do not end this turn. Node `build` still owes work:\n"
        "  · build is unmet\n"
        "Resume it with: `/the-loop:execute-tasks issue-7`\n"
        "Do one of these now:\n"
        "  1. Continue the work in this turn.\n"
        f'  2. Ask a person: `the-loop ask --work-item {REF} --question "<question>"`'
        ", then end the turn.\n"
        "  3. If you wait on something that is not a person (CI, another session),"
        f' declare it: `the-loop wait --work-item {REF} --for "<what>" --until 30m`,'
        " then end the turn. The wait covers this one stop.\n"
        "A harness that reports no background work to the-loop needs option 3 to"
        " wait on background work too."
    )


def test_a_node_without_a_command_gets_no_resume_line(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    monkeypatch.setitem(NODES, "build", {**NODES["build"], "command": ""})
    answer = stopcheck.stop_check(REF, config=bound)
    assert answer["command"] == "" and "Resume it with" not in answer["text"]


def test_an_unreadable_checkout_is_allowed_as_inconclusive(bound, tmp_path):
    """The real gather over a checkout with no state file: no pointer, so allow."""
    answer = stopcheck.stop_check(REF, config=bound)
    assert (answer["verdict"], answer["reason"]) == ("allow", "inconclusive")
    (ended,) = recorded(bound, "session.turn_ended")
    assert ended["reason"] == "inconclusive" and "node" not in ended


def test_gave_up_is_recorded_without_judging(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    answer = stopcheck.stop_check(REF, config=bound, gave_up=True)
    assert (answer["verdict"], answer["reason"]) == ("allow", "gate-gave-up")
    (ended,) = recorded(bound, "session.turn_ended")
    assert (ended["node"], ended["node_status"], ended["reason"]) == (
        "build",
        "block",
        "gate-gave-up",
    )


def test_the_open_ask_is_read_from_the_event_log(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    eventlog.emit("session.awaiting_input", work_item=REF, question="Which one?")
    assert stopcheck.stop_check(REF, config=bound)["reason"] == "open-ask"


# -- whom it answers: the session bound to the work item ---------------------------


def test_a_foreign_work_item_is_refused_and_nothing_is_recorded(bound, monkeypatch):
    """Abuse: a session names a work item no session is registered for."""
    standing(monkeypatch, report("build"))
    with pytest.raises(LookupError):
        stopcheck.stop_check(FOREIGN, config=bound)
    with pytest.raises(LookupError):
        stopcheck.stop_check(FOREIGN, config=bound, gave_up=True)
    assert recorded(bound, "session.turn_ended") == []


def test_a_closed_session_is_a_foreign_work_item(bound, monkeypatch):
    standing(monkeypatch, report("build"))
    SessionRegistry(layout_from_config(bound).local_dir).close(REF)
    with pytest.raises(LookupError):
        stopcheck.stop_check(REF, config=bound)
    assert recorded(bound, "session.turn_ended") == []


def test_the_route_answers_404_for_a_foreign_work_item(bound, monkeypatch):
    standing(monkeypatch, report("build"))
    client = TestClient(create_app(bound))
    response = client.post("/api/v1/sessions/stop-check", json={"ref": FOREIGN})
    assert response.status_code == 404
    assert FOREIGN in response.json()["detail"]
    assert recorded(bound, "session.turn_ended") == []
    assert (
        client.post("/api/v1/sessions/stop-check", json={"ref": "nope"}).status_code
        == 400
    )


def test_the_route_decides_for_the_bound_work_item(bound, monkeypatch):
    standing(monkeypatch, report("build", build="block"))
    client = TestClient(create_app(bound))
    refused = client.post("/api/v1/sessions/stop-check", json={"ref": REF}).json()
    assert refused["verdict"] == "refuse" and refused["node"] == "build"
    allowed = client.post(
        "/api/v1/sessions/stop-check", json={"ref": REF, "backgroundWork": True}
    ).json()
    assert (allowed["verdict"], allowed["reason"]) == ("allow", "background-work")


def test_the_verb_refuses_a_foreign_work_item_before_any_call(
    bound, monkeypatch, capsys
):
    """The session's own environment names its work item; another ref goes nowhere."""
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    called = []
    monkeypatch.setattr(stopcheck, "stop_check", lambda *a, **k: called.append(a))
    assert main(["sessions", "stop-check", "--work-item", FOREIGN]) == 2
    captured = capsys.readouterr()
    assert called == [] and captured.out == ""
    assert FOREIGN in captured.err and REF in captured.err


# -- the verb: the harness's payload, the JSON answer ------------------------------


def run_verb(monkeypatch, capsys, payload, *flags):
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    code = main(["sessions", "stop-check", "--work-item", REF, *flags])
    return code, capsys.readouterr()


def test_the_verb_prints_the_answer_as_json(bound, monkeypatch, capsys):
    standing(monkeypatch, report("build", build="block"))
    code, captured = run_verb(monkeypatch, capsys, "")
    answer = json.loads(captured.out)
    assert code == 0 and answer["verdict"] == "refuse" and answer["node"] == "build"


def test_the_verb_forwards_running_background_tasks(bound, monkeypatch, capsys):
    standing(monkeypatch, report("build", build="block"))
    payload = {
        "hook_event_name": "Stop",
        "background_tasks": [
            {"id": "b1", "type": "shell", "status": "completed", "description": "x"},
            {"id": "b2", "type": "shell", "status": "running", "description": "y"},
        ],
    }
    code, captured = run_verb(monkeypatch, capsys, json.dumps(payload))
    assert code == 0 and json.loads(captured.out)["reason"] == "background-work"


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        '{"background_tasks": []}',
        '{"background_tasks": "running"}',
        '{"background_tasks": ["running"]}',
        '{"background_tasks": [{"id": "b1"}]}',
        '{"background_tasks": [{"id": "b1", "status": "completed"}]}',
        '{"background_tasks": [{"id": "b1", "status": "failed"}]}',
    ],
)
def test_an_unreadable_payload_reports_no_background_work(
    bound, monkeypatch, capsys, payload
):
    standing(monkeypatch, report("build", build="block"))
    code, captured = run_verb(monkeypatch, capsys, payload)
    assert code == 0 and json.loads(captured.out)["verdict"] == "refuse"


def test_the_verb_never_reads_a_terminal(bound, monkeypatch, capsys):
    class Terminal(io.StringIO):
        def isatty(self):
            return True

        def read(self, *args):
            raise AssertionError("a terminal was read")

    standing(monkeypatch, report("build", build="block"))
    monkeypatch.setattr("sys.stdin", Terminal())
    assert main(["sessions", "stop-check", "--work-item", REF]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "refuse"


def test_the_verb_reports_a_give_up(bound, monkeypatch, capsys):
    standing(monkeypatch, report("build", build="block"))
    code, captured = run_verb(monkeypatch, capsys, "", "--gave-up")
    assert code == 0 and json.loads(captured.out)["reason"] == "gate-gave-up"


# -- the turn's start (R4.5, R4.6) -------------------------------------------------


def at_node(monkeypatch, node):
    facts = {"node": node, **NODES[node]} if node else {}
    monkeypatch.setattr(stopcheck, "_pointer", lambda session, work_item: facts)


def test_turn_start_records_the_pointers_node(bound, monkeypatch):
    at_node(monkeypatch, "build")
    answer = stopcheck.turn_start(REF, config=bound)
    assert answer["node"] == "build"
    (started,) = recorded(bound, "session.turn_started")
    assert (started["work_item"], started["node"]) == (REF, "build")


def test_turn_start_with_no_readable_pointer_records_an_empty_node(bound):
    """The real read over a checkout with no state file."""
    assert stopcheck.turn_start(REF, config=bound)["node"] == ""
    (started,) = recorded(bound, "session.turn_started")
    assert started["work_item"] == REF and "node" not in started


def test_turn_start_makes_the_session_working(bound, monkeypatch):
    at_node(monkeypatch, "build")
    stopcheck.turn_start(REF, config=bound)
    state = stopcheck._session_state(WorkItemRef.parse(REF), bound)
    assert (state.state, state.node) == ("working", "build")


def test_turn_start_for_a_foreign_work_item_records_nothing(bound, monkeypatch):
    at_node(monkeypatch, "build")
    with pytest.raises(LookupError):
        stopcheck.turn_start(FOREIGN, config=bound)
    client = TestClient(create_app(bound))
    response = client.post("/api/v1/sessions/turn-start", json={"ref": FOREIGN})
    assert response.status_code == 404
    assert recorded(bound, "session.turn_started") == []


def test_the_turn_start_route_records_the_turn(bound, monkeypatch):
    at_node(monkeypatch, "build")
    client = TestClient(create_app(bound))
    response = client.post("/api/v1/sessions/turn-start", json={"ref": REF})
    assert response.status_code == 200 and response.json()["node"] == "build"
    assert len(recorded(bound, "session.turn_started")) == 1


def test_the_turn_start_verb_records_and_prints_nothing(bound, monkeypatch, capsys):
    at_node(monkeypatch, "build")
    assert main(["sessions", "turn-start", "--work-item", REF]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")
    assert len(recorded(bound, "session.turn_started")) == 1


@pytest.mark.parametrize(
    "failure", [LookupError("no session"), ValueError("bad"), RuntimeError("boom")]
)
def test_the_turn_start_verb_always_exits_zero_in_silence(
    bound, monkeypatch, capsys, failure
):
    """It runs in a hook on every turn: it must never break one."""

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(stopcheck, "turn_start", fail)
    assert main(["sessions", "turn-start", "--work-item", REF]) == 0
    assert main(["sessions", "turn-start", "--work-item", "not a ref"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("", "")


def test_the_turn_start_verb_skips_a_foreign_work_item_in_silence(
    bound, monkeypatch, capsys
):
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    called = []
    monkeypatch.setattr(stopcheck, "turn_start", lambda *a, **k: called.append(a))
    assert main(["sessions", "turn-start", "--work-item", FOREIGN]) == 0
    captured = capsys.readouterr()
    assert called == [] and (captured.out, captured.err) == ("", "")


# -- the declared wait (R3.2.3, R4.7, R4.8) ----------------------------------------


def declared(config):
    return recorded(config, "session.wait_declared")


def working_on(monkeypatch, node="build", status="block"):
    """A session mid-turn on ``node``, whose exit gate reports ``status``."""
    standing(monkeypatch, report(node, **{node: status}))
    at_node(monkeypatch, node)


def test_declared_wait_records_the_condition_and_when_it_ends(bound, monkeypatch):
    working_on(monkeypatch)
    before = datetime.now(timezone.utc)
    answer = stopcheck.declare_wait(REF, "CI on PR 12", 1800, config=bound)
    (wait,) = declared(bound)
    assert (wait["work_item"], wait["condition"]) == (REF, "CI on PR 12")
    assert answer["until"] == wait["until"] and answer["exitCode"] == 0
    until = sessionstate.parse_ts(wait["until"])
    assert until is not None, "the stored form is the one the derivation reads"
    assert timedelta(seconds=1799) <= until - before <= timedelta(seconds=1802)


def test_a_declared_wait_made_in_this_turn_allows_one_stop(bound, monkeypatch):
    working_on(monkeypatch)
    stopcheck.turn_start(REF, config=bound)
    assert stopcheck.stop_check(REF, config=bound)["verdict"] == "refuse"
    stopcheck.declare_wait(REF, "CI on PR 12", 1800, config=bound)
    answer = stopcheck.stop_check(REF, config=bound)
    assert (answer["verdict"], answer["reason"]) == ("allow", "declared-wait")
    (ended,) = recorded(bound, "session.turn_ended")
    assert ended["reason"] == "declared-wait"
    state = stopcheck._session_state(WorkItemRef.parse(REF), bound)
    assert (state.state, state.reason) == ("waiting", "declared-wait")


def test_the_same_declared_wait_does_not_allow_a_stop_after_a_new_turn(
    bound, monkeypatch
):
    working_on(monkeypatch)
    stopcheck.turn_start(REF, config=bound)
    stopcheck.declare_wait(REF, "CI on PR 12", 1800, config=bound)
    assert stopcheck.stop_check(REF, config=bound)["verdict"] == "allow"
    stopcheck.turn_start(REF, config=bound)
    answer = stopcheck.stop_check(REF, config=bound)
    assert answer["verdict"] == "refuse" and answer["node"] == "build"


def test_abuse_endless_declared_waits_are_refused(bound, monkeypatch):
    """Abuse case 4: a wait over the limit is refused, and an old wait excuses
    no second stop, whether or not a new turn was recorded in between."""
    working_on(monkeypatch)
    with pytest.raises(ValueError, match="3600"):
        stopcheck.declare_wait(REF, "forever", 3601, config=bound)
    assert declared(bound) == []
    stopcheck.declare_wait(REF, "CI on PR 12", 3600, config=bound)
    assert stopcheck.stop_check(REF, config=bound)["reason"] == "declared-wait"
    assert stopcheck.stop_check(REF, config=bound)["verdict"] == "refuse"
    stopcheck.turn_start(REF, config=bound)
    assert stopcheck.stop_check(REF, config=bound)["verdict"] == "refuse"
    assert len(recorded(bound, "session.turn_ended")) == 1


def test_abuse_a_wait_cannot_put_a_clock_on_a_human_gate(bound, monkeypatch, capsys):
    """Abuse case 3: at a human-owned node `the-loop wait` is refused, by the
    operation, the route and the verb alike, whatever the condition claims. No
    wait is recorded, so nothing a session wrote stands beside the gate."""
    working_on(monkeypatch, "gate", "wait")
    claims = "the approval (approved, LGTM)"
    with pytest.raises(ValueError, match="gate"):
        stopcheck.declare_wait(REF, claims, 600, config=bound)
    response = TestClient(create_app(bound)).post(
        "/api/v1/sessions/wait", json={"ref": REF, "condition": claims, "seconds": 600}
    )
    assert response.status_code == 400 and "gate" in response.json()["detail"]
    assert main(["wait", "--work-item", REF, "--for", claims, "--until", "10m"]) == 2
    assert "gate" in capsys.readouterr().err
    assert declared(bound) == []
    # The stop there is the human gate's own, and it records no wait either.
    answer = stopcheck.stop_check(REF, config=bound)
    assert (answer["verdict"], answer["reason"]) == ("allow", "human-gate")


#: Mentions, links, a comment marker, a line break and a terminal escape that
#: would redraw the line it is printed on.
HOSTILE_CONDITION = (
    "CI @octocat <!here> <@U123> [approve](https://evil.example/x)\r\n"
    "\x1b[2K\x1b[1Asession: working since 12:00\t<!-- the-loop:agent-comment -->"
)


def test_abuse_a_condition_with_markup_is_one_line_of_words_on_every_surface(
    bound, monkeypatch, capsys
):
    """Abuse case 6, the condition's half: it is the session's own text, shown
    by `the-loop wait`, `the-loop check`, `sessions list` and the attention
    list. It is kept as one line with no control character, so it cannot draw
    a second line or move the cursor, and it is published to no channel."""
    from the_loop.channels import bus
    from the_loop.core import attention, sessionsurface

    def no_channel(*args, **kwargs):
        raise AssertionError("a declared wait is published to no channel")

    monkeypatch.setattr(bus, "publish", no_channel)
    working_on(monkeypatch)
    stopcheck.turn_start(REF, config=bound)
    argv = ["wait", "--work-item", REF, "--for", HOSTILE_CONDITION, "--until", "30m"]
    assert main(argv) == 0
    said = capsys.readouterr().out
    assert stopcheck.stop_check(REF, config=bound)["reason"] == "declared-wait"

    (wait,) = declared(bound)
    kept = wait["condition"]
    assert kept == (
        "CI @octocat <!here> <@U123> [approve](https://evil.example/x) "
        "[2K [1Asession: working since 12:00 <!-- the-loop:agent-comment -->"
    )
    view = sessionsurface.Reader(bound).view(REF)  # `check` and `sessions list`
    (row,) = [
        r for r in attention.list_attention(bound) if r["kind"] == "declared-wait"
    ]
    shown = [said.splitlines()[0], view["summary"], view["detail"], row["detail"]]
    for line in shown:
        assert f"“{kept}”" in line, "quoted whole, as words"
        assert line.isprintable(), "no line break and no control character"


def test_a_declared_wait_over_the_operators_limit_is_refused(bound, monkeypatch):
    working_on(monkeypatch)
    config = {**bound, "routing": {"watchdog": {"maxWaitSeconds": 600}}}
    with pytest.raises(ValueError, match="600"):
        stopcheck.declare_wait(REF, "CI on PR 12", 601, config=config)
    stopcheck.declare_wait(REF, "CI on PR 12", 600, config=config)
    assert len(declared(bound)) == 1


def test_a_declared_wait_on_a_human_owned_node_is_refused(bound, monkeypatch):
    """A person's answer is not a condition a session may put a clock on."""
    working_on(monkeypatch, "gate", "wait")
    with pytest.raises(ValueError, match="gate"):
        stopcheck.declare_wait(REF, "the approval", 600, config=bound)
    assert declared(bound) == []


@pytest.mark.parametrize("condition", ["", "   \n", "x" * 201])
def test_a_declared_wait_needs_a_short_condition(bound, monkeypatch, condition):
    working_on(monkeypatch)
    with pytest.raises(ValueError):
        stopcheck.declare_wait(REF, condition, 600, config=bound)
    assert declared(bound) == []


@pytest.mark.parametrize("seconds", [0, -5])
def test_a_declared_wait_needs_a_positive_time(bound, monkeypatch, seconds):
    working_on(monkeypatch)
    with pytest.raises(ValueError):
        stopcheck.declare_wait(REF, "CI on PR 12", seconds, config=bound)
    assert declared(bound) == []


def test_a_declared_wait_for_a_foreign_work_item_records_nothing(bound, monkeypatch):
    working_on(monkeypatch)
    with pytest.raises(LookupError):
        stopcheck.declare_wait(FOREIGN, "CI on PR 12", 600, config=bound)
    client = TestClient(create_app(bound))
    response = client.post(
        "/api/v1/sessions/wait",
        json={"ref": FOREIGN, "condition": "CI on PR 12", "seconds": 600},
    )
    assert response.status_code == 404
    assert declared(bound) == []


def test_the_declared_wait_route_records_and_refuses(bound, monkeypatch):
    working_on(monkeypatch)
    client = TestClient(create_app(bound))
    body = {"ref": REF, "condition": "CI on PR 12", "seconds": 600}
    response = client.post("/api/v1/sessions/wait", json=body)
    assert response.status_code == 200
    assert response.json()["until"] == declared(bound)[0]["until"]
    over = client.post("/api/v1/sessions/wait", json={**body, "seconds": 3601})
    assert over.status_code == 400 and "3600" in over.json()["detail"]
    assert len(declared(bound)) == 1


def test_the_declared_wait_verb_says_when_it_ends_and_what_it_covers(
    bound, monkeypatch, capsys
):
    working_on(monkeypatch)
    code = main(["wait", "--work-item", REF, "--for", "CI on PR 12", "--until", "30m"])
    out = capsys.readouterr().out
    (wait,) = declared(bound)
    assert code == 0
    assert wait["until"] in out and "CI on PR 12" in out
    assert "only the stop that ends this turn" in out
    assert stopcheck.stop_check(REF, config=bound)["reason"] == "declared-wait"


@pytest.mark.parametrize(
    "argv, said",
    [
        (["--for", "CI", "--until", "2h"], "3600"),
        (["--for", "CI", "--until", "soon"], "not a duration"),
        (["--for", "CI", "--until", "30"], "not a duration"),
        (["--for", "  ", "--until", "30m"], "what"),
        (["--for", "x" * 201, "--until", "30m"], "200"),
    ],
)
def test_the_declared_wait_verb_refuses_and_says_why(
    bound, monkeypatch, capsys, argv, said
):
    working_on(monkeypatch)
    assert main(["wait", "--work-item", REF, *argv]) == 2
    captured = capsys.readouterr()
    assert said in captured.err and captured.out == ""
    assert declared(bound) == []


def test_the_declared_wait_verb_refuses_a_human_owned_node(bound, monkeypatch, capsys):
    working_on(monkeypatch, "gate", "wait")
    assert main(["wait", "--work-item", REF, "--for", "CI", "--until", "30m"]) == 2
    assert "gate" in capsys.readouterr().err and declared(bound) == []


def test_the_declared_wait_verb_refuses_a_foreign_work_item(bound, monkeypatch, capsys):
    monkeypatch.setenv("THE_LOOP_WORK_ITEM", REF)
    code = main(["wait", "--work-item", FOREIGN, "--for", "CI", "--until", "30m"])
    assert code == 2 and FOREIGN in capsys.readouterr().err
    monkeypatch.delenv("THE_LOOP_WORK_ITEM")
    code = main(["wait", "--work-item", FOREIGN, "--for", "CI", "--until", "30m"])
    assert code == 1 and FOREIGN in capsys.readouterr().err
    assert declared(bound) == []
