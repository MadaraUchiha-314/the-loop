"""Unit tests for the cleanup domain (issue-186).

``the_loop.cleanup`` owns **what is removed, in which order, and how a partial
failure is reported**; the two acts that need a daemon — ending an endpoint,
removing a checkout — arrive as injected callables. So every branch here is
provable with a real :class:`SessionRegistry` on a tmp path and two recording
fakes: no tmux, no git, no dispatcher. The ingress triggers live in
``test_cleanup_integration.py``, and the graph node in ``test_graph_cleanup.py``.

The load-bearing assertion in this file is the one about the **portable** record.
Cleanup and ``reset`` both remove things, and the difference between them is
exactly which half survives: a reset forgets everything so a work item starts
over, a cleanup releases the machine's resources and keeps the persistence and
tracking. That is asserted here rather than left to review.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from the_loop.cleanup import (
    SESSION,
    TMUX,
    WORKSPACE,
    CleanupOutcome,
    cleanup_work_item,
)
from the_loop.control import (
    CLEANUP,
    COMMANDS,
    DEFAULT_KEYWORDS,
    GRAPH_COMMANDS,
    SPAWN_COMMANDS,
    TEARDOWN_COMMANDS,
    ControlConfig,
    ControlStore,
    parse_command,
)
from the_loop.poller.poller import PollState
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.workitem import CONTROL, POLL, WorkItemStore

REF = "github:octo/repo#15"
PR = "github:octo/repo#16"


@pytest.fixture
def registry(tmp_path: Path) -> SessionRegistry:
    return SessionRegistry(tmp_path / "local")


@pytest.fixture
def store(tmp_path: Path) -> WorkItemStore:
    return WorkItemStore(tmp_path / "portable")


def register(
    registry: SessionRegistry,
    ref: str = REF,
    status: str = "active",
    tmux_target: str = "loop-github-octo-repo-15",
    pull_requests: Optional[List[Session]] = None,
) -> Session:
    session = Session(
        work_item=WorkItemRef.parse(ref),
        harness="claude",
        harness_session_id="sess-0",
        cwd="/tmp/checkout",
        status=status,
        tmux_target=tmux_target,
        pull_requests=list(pull_requests or []),
    )
    registry.register(session, force=True)
    return session


def endpoint(ref: str = PR, tmux_target: str = "loop-github-octo-repo-16") -> Session:
    return Session(
        work_item=WorkItemRef.parse(ref),
        harness="claude",
        harness_session_id="sess-1",
        cwd="/tmp/checkout",
        tmux_target=tmux_target,
    )


class Recorder:
    """A seam that records what it was asked to end/remove, and answers ``found``."""

    def __init__(self, found: bool = True, raises: Optional[Exception] = None):
        self.calls: List[str] = []
        self.found = found
        self.raises = raises

    def __call__(self, subject) -> bool:
        ref = subject.work_item.ref if isinstance(subject, Session) else subject.ref
        self.calls.append(ref)
        if self.raises is not None:
            raise self.raises
        return self.found


# -- the control keyword ---------------------------------------------------------


def test_cleanup_is_a_declared_command_with_its_own_keyword():
    assert CLEANUP in COMMANDS
    assert DEFAULT_KEYWORDS[CLEANUP] == "the-loop cleanup"
    assert TEARDOWN_COMMANDS == (CLEANUP,)


def test_cleanup_neither_arms_nor_spawns_nor_reaches_the_graph_gate():
    """It is a teardown: it may not conjure a session, and it is not forwarded."""
    assert CLEANUP not in SPAWN_COMMANDS
    assert CLEANUP not in GRAPH_COMMANDS


def test_a_comment_carrying_the_keyword_parses_to_cleanup():
    result = parse_command("please tidy up: the-loop cleanup", ControlConfig())
    assert result.command == CLEANUP


def test_the_keyword_still_refuses_an_ambiguous_comment():
    """The new word inherits the two-commands-is-a-refusal rule by construction."""
    result = parse_command("the-loop cleanup and the-loop start", ControlConfig())
    assert result.ambiguous and result.command is None


def test_an_empty_keyword_disables_only_cleanup():
    config = ControlConfig.from_mapping({"keywords": {"cleanup": ""}})
    assert parse_command("the-loop cleanup", config).command is None
    assert parse_command("the-loop start", config).command == "start"


def test_recording_cleanup_disarms_the_work_item(store):
    """A torn-down item must not re-spawn on the next event — the `stop` rule."""
    control = ControlStore(store.root)
    control.record(REF, "start", source="comment", actor="octocat")
    assert control.start_requested(REF) is True
    control.record(REF, CLEANUP, source="comment", actor="octocat")
    assert control.start_requested(REF) is False


# -- ordering and reporting ------------------------------------------------------


def test_it_ends_every_endpoint_removes_the_checkout_and_the_record(registry):
    register(registry, pull_requests=[endpoint()])
    end, remove = Recorder(), Recorder()

    outcome = cleanup_work_item(
        REF, registry=registry, end_session=end, remove_checkout=remove
    )

    assert outcome.removed == (TMUX, WORKSPACE, SESSION)
    assert outcome.endpoints == (PR, REF)
    assert end.calls == [PR, REF]
    assert remove.calls == [REF]
    assert registry.find_by_work_item(REF, include_closed=True) is None


def test_the_work_items_own_session_is_the_last_conversation_ended(registry):
    """It is the one an operator watches; ending it first loses the report."""
    register(
        registry,
        pull_requests=[endpoint(PR), endpoint("github:octo/repo#17", "loop-x-17")],
    )
    end = Recorder()

    cleanup_work_item(REF, registry=registry, end_session=end)

    assert end.calls[-1] == REF


def test_an_endpoint_with_no_tmux_session_is_not_ended(registry):
    """A PR that was linked but never worked has no conversation to end."""
    unworked = endpoint(PR, tmux_target="")
    register(registry, pull_requests=[unworked])
    end = Recorder()

    outcome = cleanup_work_item(REF, registry=registry, end_session=end)

    assert end.calls == [REF]
    assert PR not in outcome.endpoints


def test_a_tmux_session_that_was_already_gone_is_not_reported_as_removed(registry):
    register(registry)
    outcome = cleanup_work_item(
        REF, registry=registry, end_session=Recorder(found=False)
    )
    assert TMUX not in outcome.removed
    assert outcome.endpoints == (REF,)  # it was still a conversation we ended


def test_a_checkout_that_was_not_there_is_not_reported_as_removed(registry):
    register(registry)
    outcome = cleanup_work_item(
        REF, registry=registry, remove_checkout=Recorder(found=False)
    )
    assert WORKSPACE not in outcome.removed


def test_a_closed_record_is_cleaned_up_like_a_live_one(registry):
    """The common case: the session closed when the work item did."""
    register(registry, status="closed")
    outcome = cleanup_work_item(
        REF, registry=registry, end_session=Recorder(), remove_checkout=Recorder()
    )
    assert outcome.removed == (TMUX, WORKSPACE, SESSION)


# -- the retroactive path (R4) ---------------------------------------------------


def test_a_checkout_is_reclaimed_even_with_no_session_record(registry):
    """R4.2 — a crash, or an older version, can leave a worktree with no record."""
    remove = Recorder()
    outcome = cleanup_work_item(REF, registry=registry, remove_checkout=remove)

    assert remove.calls == [REF]
    assert outcome.removed == (WORKSPACE,)
    assert outcome.found is True


def test_nothing_at_all_reports_not_found_rather_than_an_error(registry):
    outcome = cleanup_work_item(
        REF, registry=registry, remove_checkout=Recorder(found=False)
    )
    assert outcome.found is False
    assert outcome.ok is True
    assert outcome.removed == ()


def test_it_accepts_a_parsed_ref_as_readily_as_a_string(registry):
    register(registry)
    outcome = cleanup_work_item(WorkItemRef.parse(REF), registry=registry)
    assert outcome.ref == REF


# -- what cleanup must NOT touch -------------------------------------------------


def test_the_portable_record_survives_a_cleanup(registry, store):
    """The whole difference from `reset`: persistence and tracking are kept."""
    control = ControlStore(store.root)
    control.record(REF, "start", source="comment", actor="octocat")
    poll = PollState(store)
    poll.baseline_comments(REF, ["c1", "c2"], "2026-08-09T00:00:00Z")
    poll.save()
    register(registry)

    cleanup_work_item(
        REF, registry=registry, end_session=Recorder(), remove_checkout=Recorder()
    )

    assert store.section(REF, CONTROL) is not None
    assert store.section(REF, POLL) is not None


def test_the_cleanup_module_never_reaches_the_portable_store():
    """Structural, not behavioural: the import is the thing that cannot creep in."""
    import the_loop.cleanup as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]  # the module docstring names it on purpose
    assert "WorkItemStore" not in body
    assert "write_section" not in body


def test_another_work_items_record_is_left_alone(registry):
    register(registry)
    register(registry, ref="github:octo/repo#21", tmux_target="loop-other")

    cleanup_work_item(REF, registry=registry, end_session=Recorder())

    assert registry.find_by_work_item("github:octo/repo#21") is not None


# -- partial failure -------------------------------------------------------------


def test_one_stuck_endpoint_does_not_strand_the_checkout_and_the_record(registry):
    register(registry)
    remove = Recorder()

    outcome = cleanup_work_item(
        REF,
        registry=registry,
        end_session=Recorder(raises=RuntimeError("tmux wedged")),
        remove_checkout=remove,
    )

    assert remove.calls == [REF]
    assert outcome.removed == (WORKSPACE, SESSION)
    assert outcome.errors and "tmux wedged" in outcome.errors[0]
    assert outcome.ok is False
    assert outcome.found is True


def test_a_failing_checkout_removal_still_removes_the_record(registry):
    register(registry)
    outcome = cleanup_work_item(
        REF,
        registry=registry,
        end_session=Recorder(),
        remove_checkout=Recorder(raises=OSError("device busy")),
    )
    assert SESSION in outcome.removed
    assert "device busy" in outcome.errors[0]


# -- dry run ---------------------------------------------------------------------


def test_a_dry_run_reports_the_pieces_and_touches_nothing(registry):
    register(registry, pull_requests=[endpoint()])
    end, remove = Recorder(), Recorder()

    outcome = cleanup_work_item(
        REF,
        registry=registry,
        end_session=end,
        remove_checkout=remove,
        dry_run=True,
    )

    assert outcome.dry_run is True
    assert outcome.removed == (TMUX, SESSION)
    assert outcome.endpoints == (PR, REF)
    assert end.calls == [] and remove.calls == []
    assert registry.find_by_work_item(REF) is not None


# -- the report ------------------------------------------------------------------


def test_the_outcome_serialises_for_the_api_and_the_event_log():
    outcome = CleanupOutcome(
        ref=REF, removed=(TMUX,), endpoints=(REF,), errors=("boom",)
    )
    assert outcome.to_dict() == {
        "ref": REF,
        "removed": [TMUX],
        "endpoints": [REF],
        "errors": ["boom"],
        "dryRun": False,
    }


def test_a_cleanup_emits_one_event_naming_the_actor_and_the_source(
    registry, tmp_path, monkeypatch
):
    from the_loop import eventlog

    emitted = []
    monkeypatch.setattr(
        eventlog, "emit", lambda name, **fields: emitted.append((name, fields))
    )
    register(registry)

    cleanup_work_item(
        REF,
        registry=registry,
        end_session=Recorder(),
        actor="octocat",
        source="comment",
    )

    cleaned = [f for name, f in emitted if name == "session.cleaned"]
    assert len(cleaned) == 1
    assert cleaned[0]["actor"] == "octocat"
    assert cleaned[0]["source"] == "comment"
    assert cleaned[0]["removed"] == [TMUX, SESSION]


def test_a_dry_run_emits_nothing(registry, monkeypatch):
    from the_loop import eventlog

    emitted = []
    monkeypatch.setattr(eventlog, "emit", lambda name, **fields: emitted.append(name))
    register(registry)

    cleanup_work_item(REF, registry=registry, dry_run=True)

    assert "session.cleaned" not in emitted


# -- upgrade (T10) ---------------------------------------------------------------


def test_legacy_a_record_written_before_this_feature_cleans_up_unchanged(
    registry, tmp_path
):
    """A pre-issue-186 session file has no new fields; nothing needs migrating."""
    path = tmp_path / "local" / "github-octo-repo-15.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"workItem": {"ref": "github:octo/repo#15"}, "harness": "claude", '
        '"harnessSessionId": "old", "cwd": "/tmp/x", "status": "closed", '
        '"tmuxTarget": "loop-github-octo-repo-15"}'
    )

    outcome = cleanup_work_item(REF, registry=registry, end_session=Recorder())

    assert outcome.removed == (TMUX, SESSION)
    assert registry.find_by_work_item(REF, include_closed=True) is None


def test_legacy_a_config_without_the_new_keyword_gets_the_default():
    config = ControlConfig.from_mapping({"keywords": {"start": "go", "stop": "halt"}})
    assert config.keyword(CLEANUP) == "the-loop cleanup"
