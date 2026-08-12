"""Unit tests for the core facade's session surface (issue-161, T3)."""

import pytest

from the_loop.core import sessions as core_sessions
from the_loop.sessions.registry import Session, SessionRegistry
from the_loop.state import layout_from_config
from the_loop.workitem import WorkItemRef


REF = "github:octo/repo#5"


def _config(tmp_path):
    return {"state": {"root": str(tmp_path / ".the-loop")}}


def _register(tmp_path):
    layout = layout_from_config(_config(tmp_path))
    registry = SessionRegistry(layout.local_dir)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )


def test_list_sessions_reports_registered_sessions(tmp_path):
    _register(tmp_path)
    sessions = core_sessions.list_sessions(config=_config(tmp_path))
    assert len(sessions) == 1
    # ``ref`` is the flat string every caller keys on; ``workItem`` stays the
    # registry's own object, so nothing is projected away.
    assert sessions[0]["ref"] == REF
    assert sessions[0]["workItem"]["ref"] == REF
    assert sessions[0]["status"] == "active"
    assert sessions[0]["control"] is None


def test_get_session_missing_is_lookup_error(tmp_path):
    with pytest.raises(LookupError):
        core_sessions.get_session(REF, config=_config(tmp_path))


def test_control_session_rejects_unknown_verb_before_spawning(tmp_path):
    with pytest.raises(ValueError):
        core_sessions.control_session(REF, "detonate")


def test_control_session_rejects_malformed_ref_before_spawning(tmp_path):
    with pytest.raises(ValueError):
        core_sessions.control_session("not-a-ref", "start")


# -- cleanup (issue-186) ---------------------------------------------------------


def test_cleanup_is_one_of_the_control_verbs():
    """So the CLI, the HTTP route and the MCP tool all reach one implementation."""
    assert "cleanup" in core_sessions.CONTROL_VERBS


def test_cleanup_reports_each_irreversible_fact_on_its_own_line(tmp_path, monkeypatch):
    """Losing a checkout means losing what was uncommitted in it — say so."""
    from the_loop.cleanup import SESSION, TMUX, WORKSPACE, CleanupOutcome

    class FakeDispatcher:
        def __init__(self):
            self.asked = None

        def cleanup_work_item(self, ref, **kwargs):
            self.asked = (ref, kwargs)
            return CleanupOutcome(
                ref=ref.ref,
                removed=(TMUX, WORKSPACE, SESSION),
                endpoints=(REF, "github:octo/repo#6"),
            )

        def stop(self, timeout=None):
            pass

    class FakeRouting:
        workspace = type("W", (), {"root": "/ws"})()

    fake = FakeDispatcher()
    monkeypatch.setattr(
        core_sessions, "_dispatcher_for", lambda *a, **k: (fake, FakeRouting())
    )

    result = core_sessions.control_session(
        REF, "cleanup", comment=False, config=_config(tmp_path)
    )

    text = "\n".join(m["text"] for m in result["messages"])
    assert result["effect"] == "cleaned" and result["exitCode"] == 0
    assert "github:octo/repo#6" in text
    assert "uncommitted work in it is gone" in text
    assert "machine-local session record" in text
    assert "portable record" in text
    assert fake.asked is not None and fake.asked[1]["source"] == "cli"


def test_cleanup_with_nothing_left_is_not_an_error(tmp_path, monkeypatch):
    from the_loop.cleanup import CleanupOutcome

    class FakeDispatcher:
        def cleanup_work_item(self, ref, **kwargs):
            return CleanupOutcome(ref=ref.ref)

        def stop(self, timeout=None):
            pass

    monkeypatch.setattr(
        core_sessions,
        "_dispatcher_for",
        lambda *a, **k: (
            FakeDispatcher(),
            type("R", (), {"workspace": type("W", (), {"root": ""})()})(),
        ),
    )

    result = core_sessions.control_session(
        REF, "cleanup", comment=False, config=_config(tmp_path)
    )

    assert result["effect"] == "nothing-to-clean"
    assert result["exitCode"] == 0


def test_cleanup_is_recorded_whether_or_not_it_found_anything(tmp_path, monkeypatch):
    """A disarming verb: a torn-down item must not re-spawn on the next event."""
    from the_loop.cleanup import CleanupOutcome
    from the_loop.control import ControlStore

    class FakeDispatcher:
        def cleanup_work_item(self, ref, **kwargs):
            return CleanupOutcome(ref=ref.ref)

        def stop(self, timeout=None):
            pass

    monkeypatch.setattr(
        core_sessions,
        "_dispatcher_for",
        lambda *a, **k: (
            FakeDispatcher(),
            type("R", (), {"workspace": type("W", (), {"root": ""})()})(),
        ),
    )
    config = _config(tmp_path)
    layout = layout_from_config(config)
    store = ControlStore(layout.portable_dir)
    store.record(REF, "start", source="cli", actor="octocat")

    core_sessions.control_session(REF, "cleanup", comment=False, config=config)

    record = store.get(REF)
    assert record is not None and record.command == "cleanup"
    assert store.start_requested(REF) is False


# -- ask & reply (issue-208) -----------------------------------------------------


def _events(monkeypatch):
    """Capture module-level eventlog.emit calls as (event, level, fields)."""
    from the_loop import eventlog

    captured = []

    def fake_emit(event, level="info", **fields):
        captured.append((event, level, fields))

    monkeypatch.setattr(eventlog, "emit", fake_emit)
    return captured


def test_ask_stamps_the_marker_centrally_and_records_the_wait(tmp_path, monkeypatch):
    """The substantive change of issue-208: no agent memory involved."""
    from the_loop.authz import SELF_COMMENT_ATTRIBUTION, SELF_COMMENT_MARKER

    posted = {}

    def fake_post(item, body, gh_binary="gh"):
        posted["ref"], posted["body"] = item.ref, body
        return True, "", "https://github.com/octo/repo/issues/5#issuecomment-1"

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    events = _events(monkeypatch)

    result = core_sessions.ask_session(
        REF, "Which auth mode?", config=_config(tmp_path)
    )

    assert posted["ref"] == REF
    assert posted["body"].startswith("Which auth mode?")
    assert SELF_COMMENT_MARKER in posted["body"]
    assert SELF_COMMENT_ATTRIBUTION in posted["body"]
    assert result["exitCode"] == 0 and result["asked"] is True
    assert result["commentUrl"].endswith("#issuecomment-1")
    event, level, fields = events[0]
    assert event == "session.awaiting_input" and level == "info"
    assert fields["work_item"] == REF
    assert fields["question"] == "Which auth mode?"
    assert fields["comment_posted"] is True
    assert fields["comment_url"].endswith("#issuecomment-1")


def test_ask_does_not_double_stamp_an_already_marked_question(tmp_path, monkeypatch):
    from the_loop.authz import SELF_COMMENT_MARKER, mark_self_authored

    posted = {}

    def fake_post(item, body, gh_binary="gh"):
        posted["body"] = body
        return True, "", ""

    monkeypatch.setattr(core_sessions, "post_issue_comment_with_url", fake_post)
    _events(monkeypatch)

    core_sessions.ask_session(
        REF, mark_self_authored("Which auth mode?"), config=_config(tmp_path)
    )

    assert posted["body"].count(SELF_COMMENT_MARKER) == 1


def test_ask_still_records_the_wait_when_gh_fails(tmp_path, monkeypatch):
    """R1.3: the agent is waiting whether or not GitHub was reachable."""
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda item, body, gh_binary="gh": (False, "gh exited 1: boom", ""),
    )
    events = _events(monkeypatch)

    result = core_sessions.ask_session(
        REF, "Which auth mode?", config=_config(tmp_path)
    )

    assert result["exitCode"] == 1 and result["asked"] is False
    event, level, fields = events[0]
    assert event == "session.awaiting_input" and level == "warning"
    assert fields["comment_posted"] is False
    # Passed as None, which the real emit drops from the record.
    assert fields.get("comment_url") is None
    assert any("boom" in m["text"] for m in result["messages"] if m["stream"] == "err")


def test_ask_refuses_an_empty_question_posting_and_emitting_nothing(
    tmp_path, monkeypatch
):
    called = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment_with_url",
        lambda *a, **k: called.append(a) or (True, "", ""),
    )
    events = _events(monkeypatch)
    with pytest.raises(ValueError):
        core_sessions.ask_session(REF, "   \n", config=_config(tmp_path))
    with pytest.raises(ValueError):
        core_sessions.ask_session("not-a-ref", "Question?", config=_config(tmp_path))
    assert not called and not events


class _FakeRunner:
    """A TmuxRunner whose deliveries are recorded instead of pasted."""

    delivered: "list[tuple[str, str]]" = []
    result: "object | None" = None

    def __init__(self, *args, **kwargs):
        pass

    def deliver(self, session, prompt, timeout=None):
        from the_loop.runner import TmuxResult

        _FakeRunner.delivered.append((session.work_item.ref, prompt))
        return _FakeRunner.result or TmuxResult(ok=True)


@pytest.fixture
def fake_runner(monkeypatch):
    _FakeRunner.delivered = []
    _FakeRunner.result = None
    monkeypatch.setattr(core_sessions, "TmuxRunner", _FakeRunner)
    return _FakeRunner


def test_reply_delivers_with_provenance_and_emits(tmp_path, monkeypatch, fake_runner):
    _register(tmp_path)
    monkeypatch.setattr(core_sessions, "post_issue_comment", lambda *a, **k: (True, ""))
    events = _events(monkeypatch)

    result = core_sessions.reply_session(
        REF, "Use OAuth.", actor="onika", config=_config(tmp_path)
    )

    assert result["exitCode"] == 0 and result["delivered"] is True
    ref, prompt = fake_runner.delivered[0]
    assert ref == REF
    assert prompt.startswith(
        "Reply from the operator via the-loop control plane (onika)"
    )
    assert prompt.endswith("Use OAuth.")
    assert events[0][0] == "session.reply_sent"
    assert events[0][2] == {"work_item": REF, "actor": "onika"}


def test_reply_report_comment_is_marked_and_quotes_the_reply(
    tmp_path, monkeypatch, fake_runner
):
    """Abuse case 4: an unmarked copy would be poller-forwarded — delivered twice."""
    from the_loop.authz import SELF_COMMENT_MARKER

    _register(tmp_path)
    posted = {}
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda item, body, gh_binary="gh": posted.update(body=body) or (True, ""),
    )
    _events(monkeypatch)

    core_sessions.reply_session(REF, "Use OAuth.\nNot keys.", config=_config(tmp_path))

    assert SELF_COMMENT_MARKER in posted["body"]
    assert "> Use OAuth." in posted["body"] and "> Not keys." in posted["body"]


def test_reply_comment_false_posts_nothing(tmp_path, monkeypatch, fake_runner):
    _register(tmp_path)
    called = []
    monkeypatch.setattr(
        core_sessions,
        "post_issue_comment",
        lambda *a, **k: called.append(a) or (True, ""),
    )
    _events(monkeypatch)
    core_sessions.reply_session(
        REF, "Use OAuth.", comment=False, config=_config(tmp_path)
    )
    assert not called


def test_reply_without_a_session_is_lookup_error_and_never_spawns(
    tmp_path, fake_runner, monkeypatch
):
    """R2.3 / abuse case 2: a reply answers an agent; it must never create one."""
    _events(monkeypatch)
    with pytest.raises(LookupError):
        core_sessions.reply_session(REF, "Use OAuth.", config=_config(tmp_path))
    assert not fake_runner.delivered


def test_reply_to_a_dead_pane_is_lookup_error_not_a_respawn(
    tmp_path, monkeypatch, fake_runner
):
    from the_loop.runner import TmuxResult

    _register(tmp_path)
    _FakeRunner.result = TmuxResult(ok=False, session_missing=True, error="gone")
    events = _events(monkeypatch)
    with pytest.raises(LookupError):
        core_sessions.reply_session(REF, "Use OAuth.", config=_config(tmp_path))
    assert not events  # no reply_sent for an undelivered reply


def test_reply_to_a_paused_session_is_refused(tmp_path, monkeypatch, fake_runner):
    """R2.4 / abuse case 3: pause means 'deliver nothing', this route included."""
    _register(tmp_path)
    layout = layout_from_config(_config(tmp_path))
    SessionRegistry(layout.local_dir).pause(WorkItemRef.parse(REF))
    _events(monkeypatch)
    with pytest.raises(ValueError, match="paused"):
        core_sessions.reply_session(REF, "Use OAuth.", config=_config(tmp_path))
    assert not fake_runner.delivered


def test_reply_refuses_empty_text(tmp_path, fake_runner):
    with pytest.raises(ValueError):
        core_sessions.reply_session(REF, "  \n", config=_config(tmp_path))
    assert not fake_runner.delivered


def test_reply_transient_tmux_failure_is_exit_1_not_an_event(
    tmp_path, monkeypatch, fake_runner
):
    from the_loop.runner import TmuxResult

    _register(tmp_path)
    _FakeRunner.result = TmuxResult(ok=False, error="tmux paste-buffer timed out")
    events = _events(monkeypatch)
    result = core_sessions.reply_session(REF, "Use OAuth.", config=_config(tmp_path))
    assert result["exitCode"] == 1 and result["delivered"] is False
    assert not events
