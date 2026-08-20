"""Standing sessions end to end, at the tmux seam (issue-277, T2).

The four behaviours that *are* the feature. tmux is faked at ``TmuxRunner`` — the
boundary every other session test in this repository fakes at — and the harness at
``build_adapters``: no tmux server, no ``claude`` binary and no Slack workspace is
contacted.
"""

from __future__ import annotations

from typing import List

import pytest

from the_loop.core import lifecycle as core_lifecycle
from the_loop.core import standing as core_standing
from the_loop.harness.base import HarnessAdapter
from the_loop.runner import (
    SESSION_ABSENT,
    SESSION_DEAD,
    SESSION_LIVE,
    SESSION_UNKNOWN,
    TmuxResult,
)
from the_loop.standing import StandingRecord, StandingRegistry, standing_ref
from the_loop.state import layout_from_config
from the_loop.trust import TrustResult


class _Adapter(HarnessAdapter):
    name = "claude"
    default_binary = "claude-stub"
    available = True

    def is_available(self) -> bool:
        return self.available

    def prepare_environment(self, cwd, root=None):
        return TrustResult()

    def interactive_argv(self, prompt, session_id):
        return ["--session-id", session_id, prompt]

    def interactive_resume_argv(self, prompt, session_id):
        return ["--resume", session_id, prompt]


class _Tmux:
    """A tmux server this test owns: which targets exist, and what was asked of it."""

    def __init__(self, remain_on_exit: bool = True):
        self.state = {}  # target -> SESSION_LIVE | SESSION_DEAD
        self.spawns: List[dict] = []
        self.delivered: List[tuple] = []
        self.killed: List[str] = []
        self.terminated: List[tuple] = []
        self.survives = True
        self.deliver_ok = True

    # -- reads
    def session_state(self, target):
        return self.state.get(target, SESSION_ABSENT)

    def has_session(self, target):
        return target in self.state

    def has_live_session(self, target):
        return self.state.get(target) == SESSION_LIVE

    def survived(self, target, delay, sleeper=None):
        if not self.survives:
            self.state.pop(target, None)
            return False
        return self.has_live_session(target)

    # -- writes
    def spawn_in(
        self, target, adapter, prompt, cwd, session_id, timeout=None, resume=False
    ):
        self.spawns.append(
            {
                "target": target,
                "prompt": prompt,
                "cwd": cwd,
                "session_id": session_id,
                "resume": resume,
            }
        )
        self.state[target] = SESSION_LIVE
        return TmuxResult(ok=True)

    def deliver_to(self, target, prompt, timeout=None):
        if not self.deliver_ok:
            return TmuxResult(ok=False, error="tmux is busy")
        self.delivered.append((target, prompt))
        return TmuxResult(ok=True)

    def kill_target(self, target, timeout=None):
        self.killed.append(target)
        self.state.pop(target, None)
        return TmuxResult(ok=True)

    def terminate_harness_in(self, target, label, grace=5.0, **kwargs):
        self.terminated.append((target, label))
        return TmuxResult(ok=True)


@pytest.fixture
def tmux(monkeypatch):
    server = _Tmux()
    monkeypatch.setattr(core_standing, "TmuxRunner", lambda **kwargs: server)
    monkeypatch.setattr(
        core_standing, "build_adapters", lambda **kwargs: {"claude": _Adapter()}
    )
    return server


def _config(tmp_path, **entry):
    session = {"name": "supervisor"}
    session.update(entry)
    return {
        "state": {"root": str(tmp_path / ".the-loop")},
        "routing": {"defaultHarness": "claude", "spawnWorkdir": str(tmp_path)},
        "standingSessions": {"enabled": True, "sessions": [session]},
    }


def _registry(config):
    return StandingRegistry(layout_from_config(config).standing_dir)


# -- scenarios -------------------------------------------------------------------


def test_a_stopped_standing_session_is_resumed_not_restarted_from_nothing(
    tmp_path, tmux
):
    """
    Feature: standing sessions
      Scenario: a stopped standing session is resumed, not restarted from nothing
        Given a standing session that has been started and then stopped
        When it is started again
        Then the harness is asked to CONTINUE its recorded conversation
        And the record still carries the same conversation id

    Requirement: docs/specs/issue-277/requirements.md R2.3, R2.4, R2.6, R2.7
    """
    config = _config(tmp_path)

    first = core_standing.start_standing(config=config)
    assert [row["outcome"] for row in first["sessions"]] == ["started"]
    conversation = tmux.spawns[0]["session_id"]
    assert tmux.spawns[0]["resume"] is False

    stopped = core_standing.stop_standing(config=config)
    assert [row["outcome"] for row in stopped["sessions"]] == ["stopped"]
    # The harness is ended gracefully BEFORE the tmux session is killed, so the
    # conversation is flushed and stays resumable (design D4).
    assert tmux.terminated == [("loop-standing-supervisor", standing_ref("supervisor"))]
    assert tmux.killed == ["loop-standing-supervisor"]
    record = _registry(config).read("supervisor")
    assert record is not None
    assert record.status == "stopped"
    assert record.harness_session_id == conversation

    again = core_standing.start_standing(config=config)
    assert [row["outcome"] for row in again["sessions"]] == ["resumed"]
    assert tmux.spawns[1]["resume"] is True
    assert tmux.spawns[1]["session_id"] == conversation


def test_a_resume_that_does_not_survive_falls_back_to_a_fresh_conversation(
    tmp_path, tmux
):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    conversation = tmux.spawns[0]["session_id"]
    core_standing.stop_standing(config=config)

    tmux.survives = False  # `claude --resume <unknown-id>` exits at once
    report = core_standing.start_standing(config=config)

    assert [row["outcome"] for row in report["sessions"]] == ["started"]
    assert tmux.spawns[1]["resume"] is True
    assert tmux.spawns[2]["resume"] is False
    record = _registry(config).read("supervisor")
    assert record is not None and record.harness_session_id != conversation


def test_a_start_never_touches_a_live_session(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    report = core_standing.start_standing(config=config)
    assert [row["outcome"] for row in report["sessions"]] == ["already-running"]
    assert len(tmux.spawns) == 1


def test_a_live_tmux_session_the_loop_cannot_account_for_is_never_spawned_over(
    tmp_path, tmux
):
    """
    Feature: standing sessions
      Scenario: a live tmux session the-loop cannot account for is never spawned over
        Given a live tmux session named loop-standing-supervisor and no record of it
        When the standing session is started
        Then the start is refused, naming how to inspect the session
        And nothing is spawned and nothing is killed

    Requirement: docs/specs/issue-277/requirements.md R2.9
    """
    config = _config(tmp_path)
    tmux.state["loop-standing-supervisor"] = SESSION_LIVE

    report = core_standing.start_standing(config=config)

    row = report["sessions"][0]
    assert row["outcome"] == "failed"
    assert "tmux attach -r -t loop-standing-supervisor" in row["detail"]
    assert tmux.spawns == [] and tmux.killed == []


@pytest.mark.parametrize("with_record", [True, False])
def test_a_retained_dead_pane_is_cleared_and_respawned(tmp_path, tmux, with_record):
    """Only a LIVE occupant is refused. A dead pane holds no agent, so clearing it
    costs nothing but the scrollback — with or without a record."""
    config = _config(tmp_path)
    if with_record:
        _registry(config).write(
            StandingRecord(name="supervisor", harness="claude", harness_session_id="")
        )
    tmux.state["loop-standing-supervisor"] = SESSION_DEAD

    report = core_standing.start_standing(config=config)

    assert report["sessions"][0]["outcome"] == "started"
    assert tmux.killed == ["loop-standing-supervisor"]
    assert len(tmux.spawns) == 1


def test_an_unknown_tmux_answer_never_becomes_a_spawn(tmp_path, tmux, monkeypatch):
    """A probe tmux did not answer is not absence (issue-146's rule): spawning on
    it is how a live session gets collided with."""
    monkeypatch.setattr(tmux, "session_state", lambda target: SESSION_UNKNOWN)

    report = core_standing.start_standing(config=_config(tmp_path))

    assert report["sessions"][0]["outcome"] == "failed"
    assert tmux.spawns == []


def test_stop_never_signals_a_tmux_session_the_loop_has_no_record_of(tmp_path, tmux):
    """The mirror of the start refusal: the-loop releases what it started, and a
    session it cannot account for is the operator's `tmux kill-session`."""
    config = _config(tmp_path)
    tmux.state["loop-standing-supervisor"] = SESSION_LIVE  # nobody recorded it

    report = core_standing.stop_standing("supervisor", config=config)

    row = report["sessions"][0]
    assert row["outcome"] == "not-running"
    assert "no record" in row["detail"]
    assert tmux.killed == [] and tmux.terminated == []


def test_stop_with_no_name_touches_only_what_was_started(tmp_path, tmux):
    config = _config(tmp_path)
    config["standingSessions"]["sessions"] = [{"name": "started"}, {"name": "never"}]
    core_standing.start_standing("started", config=config)

    report = core_standing.stop_standing(config=config)

    assert [row["name"] for row in report["sessions"]] == ["started"]


def test_a_standing_session_is_told_what_it_is_not(tmp_path, tmux):
    """
    Feature: standing sessions
      Scenario: a standing session is told what it is not
        Given a standing session with an operator's own brief
        When it is spawned
        Then the-loop's directive precedes that brief in the boot prompt
        And the directive states that it owns no work item

    Requirement: docs/specs/issue-277/requirements.md R5.1, R5.2
    """
    config = _config(tmp_path, prompt="Watch the work items and report what is stuck.")

    core_standing.start_standing(config=config)

    prompt = tmux.spawns[0]["prompt"]
    flat = " ".join(prompt.split())
    assert prompt.index("you own no") < prompt.index("Watch the work items")
    assert "Do not answer a phase-selection gate" in flat
    assert "post a control keyword" in flat
    assert flat.startswith("You are **supervisor**, a the-loop *standing session*.")


def test_a_cwd_that_is_not_there_fails_that_session_and_no_other(tmp_path, tmux):
    config = _config(tmp_path)
    config["standingSessions"]["sessions"] = [
        {"name": "broken", "cwd": str(tmp_path / "gone")},
        {"name": "fine"},
    ]

    report = core_standing.start_standing(config=config)

    outcomes = {row["name"]: row["outcome"] for row in report["sessions"]}
    assert outcomes == {"broken": "failed", "fine": "started"}
    assert report["ok"] is False
    assert [spawn["target"] for spawn in tmux.spawns] == ["loop-standing-fine"]


def test_an_unreadable_prompt_file_fails_that_session_and_no_other(tmp_path, tmux):
    config = _config(tmp_path)
    config["standingSessions"]["sessions"] = [
        {"name": "broken", "promptFile": str(tmp_path / "gone.md")},
        {"name": "fine"},
    ]

    report = core_standing.start_standing(config=config)

    outcomes = {row["name"]: row["outcome"] for row in report["sessions"]}
    assert outcomes == {"broken": "failed", "fine": "started"}


def test_a_missing_harness_binary_fails_honestly(tmp_path, tmux, monkeypatch):
    absent = _Adapter()
    absent.available = False
    monkeypatch.setattr(
        core_standing, "build_adapters", lambda **kwargs: {"claude": absent}
    )
    report = core_standing.start_standing(config=_config(tmp_path))
    row = report["sessions"][0]
    assert row["outcome"] == "failed"
    assert "claude-stub" in row["detail"]


# -- lifecycle -------------------------------------------------------------------


def test_the_lifecycle_verbs_carry_the_standing_sessions(tmp_path, tmux, monkeypatch):
    """
    Feature: standing sessions
      Scenario: the-loop start, stop and status carry the standing sessions
        Given a declared, auto-starting standing session
        When the-loop start, then status, then stop are composed
        Then each reports the session in its own standingSessions section
        And status is not ok while a session start would have started is down

    Requirement: docs/specs/issue-277/requirements.md R2.1, R2.2, R2.5, R2.8
    """
    config = _config(tmp_path)
    # The services are not what this asserts; keep them out of the report.
    config["service"] = {"enabled": False}
    monkeypatch.setattr(core_lifecycle, "_healthy", lambda config=None: False)

    started = core_lifecycle.start_all(config)
    assert [row["outcome"] for row in started["standingSessions"]] == ["started"]

    status = core_lifecycle.status_all(config)
    assert status["standingSessions"][0]["running"] is True

    stopped = core_lifecycle.stop_all(config)
    assert [row["outcome"] for row in stopped["standingSessions"]] == ["stopped"]

    # …and a session that `start` would have started, now down, is not ok.
    down = core_lifecycle.status_all(config)
    assert down["standingSessions"][0]["running"] is False
    assert down["ok"] is False


def test_a_session_that_start_would_not_have_started_does_not_decide_status(
    tmp_path, tmux, monkeypatch
):
    config = _config(tmp_path, autoStart=False)
    config["service"] = {"enabled": False}
    monkeypatch.setattr(core_lifecycle, "_healthy", lambda config=None: False)

    started = core_lifecycle.start_all(config)
    assert started["standingSessions"] == []
    assert core_lifecycle.status_all(config)["ok"] is True


def test_stop_reaches_a_session_that_is_no_longer_declared(tmp_path, tmux):
    """R2.6 falls out of reading the REGISTRY rather than the config."""
    config = _config(tmp_path)
    core_standing.start_standing(config=config)

    undeclared = dict(config)
    undeclared["standingSessions"] = {"enabled": False, "sessions": []}
    report = core_standing.stop_standing(config=undeclared)

    assert [row["outcome"] for row in report["sessions"]] == ["stopped"]


def test_a_malformed_block_refuses_the_reads_and_the_start(tmp_path, tmux):
    """A read that answered "no standing sessions" for a config with a typo in it
    would be a wrong answer that looks like a fact."""
    config = _config(tmp_path)
    config["standingSessions"]["sessions"] = [{"name": "a"}, {"name": "a"}]

    with pytest.raises(ValueError) as excinfo:
        core_standing.start_standing(config=config)
    assert "already declared" in str(excinfo.value)
    with pytest.raises(ValueError):
        core_standing.list_standing(config=config)
    assert tmux.spawns == []


def test_stop_is_the_one_verb_that_survives_a_config_it_cannot_parse(tmp_path, tmux):
    """The recovery path: an operator whose config broke after a start must
    still be able to stop what is running. `stop` works off the registry."""
    config = _config(tmp_path)
    core_standing.start_standing(config=config)

    config["standingSessions"]["sessions"] = [
        {"name": "supervisor"},
        {"name": "supervisor"},
    ]
    report = core_standing.stop_standing(config=config)

    assert [row["outcome"] for row in report["sessions"]] == ["stopped"]


def test_a_malformed_block_becomes_one_misconfigured_row_in_the_lifecycle(
    tmp_path, tmux, monkeypatch
):
    config = _config(tmp_path)
    config["service"] = {"enabled": False}
    config["standingSessions"]["sessions"] = [{"name": "a"}, {"name": "a"}]
    monkeypatch.setattr(core_lifecycle, "_healthy", lambda config=None: False)

    report = core_lifecycle.start_all(config)

    assert [row["outcome"] for row in report["standingSessions"]] == ["misconfigured"]
    assert report["ok"] is False
    assert core_lifecycle.status_all(config)["ok"] is False


# -- say -------------------------------------------------------------------------


def test_a_message_is_pasted_into_a_running_session_and_posted_nowhere(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)

    result = core_standing.say_standing(
        "supervisor", "what is stuck?", actor="ops", config=config
    )

    assert result["delivered"] is True
    target, prompt = tmux.delivered[0]
    assert target == "loop-standing-supervisor"
    assert "what is stuck?" in prompt and "ops" in prompt
    record = _registry(config).read("supervisor")
    assert record is not None and record.last_message_at


def test_a_message_into_a_stopped_session_refuses_instead_of_spawning(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    core_standing.stop_standing(config=config)

    with pytest.raises(LookupError) as excinfo:
        core_standing.say_standing("supervisor", "hello", config=config)

    assert "the-loop standing start supervisor" in str(excinfo.value)
    assert len(tmux.spawns) == 1


def test_a_message_to_an_unknown_name_refuses(tmp_path, tmux):
    with pytest.raises(LookupError):
        core_standing.say_standing("nobody", "hello", config=_config(tmp_path))


def test_an_empty_message_is_a_caller_mistake(tmp_path, tmux):
    with pytest.raises(ValueError):
        core_standing.say_standing("supervisor", "   ", config=_config(tmp_path))


def test_a_transient_tmux_failure_reports_rather_than_raises(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    tmux.deliver_ok = False

    result = core_standing.say_standing("supervisor", "hello", config=config)

    assert result["delivered"] is False and result["exitCode"] == 1


# -- reads -----------------------------------------------------------------------


def test_list_merges_declared_and_recorded_sessions(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    _registry(config).write(StandingRecord(name="orphan", harness="claude"))

    rows = {row["name"]: row for row in core_standing.list_standing(config=config)}

    assert rows["supervisor"]["declared"] is True
    assert rows["orphan"]["declared"] is False
    assert rows["supervisor"]["running"] is True
    assert rows["orphan"]["running"] is False


def test_get_on_an_unknown_name_is_a_lookup_error(tmp_path, tmux):
    with pytest.raises(LookupError):
        core_standing.get_standing("nobody", config=_config(tmp_path))


def test_control_rejects_an_unknown_verb(tmp_path, tmux):
    with pytest.raises(ValueError):
        core_standing.control_standing(
            "supervisor", "detonate", config=_config(tmp_path)
        )


def test_restart_has_no_all_form(tmp_path, tmux):
    with pytest.raises(ValueError):
        core_standing.restart_standing("", config=_config(tmp_path))


def test_restart_stops_then_starts_keeping_the_conversation(tmp_path, tmux):
    config = _config(tmp_path)
    core_standing.start_standing(config=config)
    conversation = tmux.spawns[0]["session_id"]

    report = core_standing.restart_standing("supervisor", config=config)

    assert report["ok"] is True
    assert tmux.spawns[1]["resume"] is True
    assert tmux.spawns[1]["session_id"] == conversation
