"""Unit tests for the reset domain (issue-137).

``the_loop.reset`` is the composition of the erasure paths that already exist —
close the session, delete its record, clear the portable sections — plus the one
primitive the registry never had (:meth:`SessionRegistry.forget`). These tests
drive it with real stores on tmp paths and an injected ``close`` callable, so
every branch is provable without a dispatcher, tmux or git. The CLI surface
lives in ``test_reset_integration.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop.control import ControlStore
from the_loop.poller.poller import PollState
from the_loop.reset import (
    CONTROL,
    LINK,
    POLL,
    SESSION,
    WORKSPACE,
    ResetOutcome,
    reset_work_item,
    work_items_with_state,
)
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.state import LegacyLayout
from the_loop.workitem import SEALED, WorkItemStore

REF = "github:octo/repo#15"
OTHER = "github:octo/repo#21"


@pytest.fixture
def registry(tmp_path: Path) -> SessionRegistry:
    return SessionRegistry(tmp_path / "local")


@pytest.fixture
def store(tmp_path: Path) -> WorkItemStore:
    return WorkItemStore(tmp_path / "portable")


def register(registry: SessionRegistry, ref: str = REF, status: str = "active") -> None:
    registry.register(
        Session(
            work_item=WorkItemRef.parse(ref),
            harness="claude",
            harness_session_id="sess-0",
            cwd=".",
            status=status,
        ),
        force=True,
    )


def arm(store: WorkItemStore, ref: str = REF) -> None:
    ControlStore(store.root).record(ref, "start", source="cli", actor="octocat")


def baseline(store: WorkItemStore, ref: str = REF) -> None:
    state = PollState(store)
    state.baseline_comments(ref, ["c1", "c2"], "2026-08-04T00:00:00Z")
    state.save()


# -- SessionRegistry.forget ------------------------------------------------------


def test_forget_deletes_the_record_rather_than_closing_it(registry):
    register(registry)
    assert registry.forget(REF) is True
    assert registry.find_by_work_item(REF, include_closed=True) is None
    assert registry.list_sessions() == []


def test_forget_reports_false_when_there_was_no_record(registry):
    assert registry.forget(REF) is False


def test_forget_removes_a_closed_record_too(registry):
    register(registry, status="closed")
    assert registry.forget(REF) is True
    assert registry.list_sessions() == []


# -- reset_work_item -------------------------------------------------------------


def test_every_piece_is_removed(registry, store):
    register(registry)
    arm(store)
    baseline(store)

    outcome = reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=lambda s: False
    )

    assert outcome.removed == (SESSION, CONTROL, POLL)
    assert outcome.ok and outcome.found
    assert registry.find_by_work_item(REF, include_closed=True) is None
    assert store.section(REF, CONTROL) is None
    assert store.section(REF, POLL) is None
    assert not store.path_for(REF).exists()


def test_a_live_session_is_closed_before_its_record_goes(registry, store):
    register(registry)
    seen = []

    def close(session: Session) -> bool:
        # The record must still be readable here: closing runs first.
        seen.append(registry.find_by_work_item(REF, include_closed=True) is not None)
        return True

    outcome = reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=close
    )

    assert seen == [True]
    assert outcome.was_live is True
    assert outcome.removed == (WORKSPACE, SESSION)


def test_a_paused_session_counts_as_live(registry, store):
    register(registry, status="paused")
    closed = []
    reset_work_item(
        WorkItemRef.parse(REF),
        registry=registry,
        store=store,
        close=lambda s: closed.append(s) or False,
    )
    assert len(closed) == 1


def test_a_closed_session_is_removed_without_being_closed_again(registry, store):
    register(registry, status="closed")

    def explode(session):  # pragma: no cover - must not be reached
        raise AssertionError("a closed session must not be closed again")

    outcome = reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=explode
    )
    assert outcome.removed == (SESSION,) and outcome.was_live is False


def test_only_the_pieces_that_exist_are_reported(registry, store):
    arm(store)
    outcome = reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    assert outcome.removed == (CONTROL,)
    assert outcome.found


def test_nothing_recorded_is_reported_as_not_found(registry, store):
    outcome = reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    assert outcome.removed == () and outcome.found is False and outcome.ok is False


def test_clearing_control_disarms_the_work_item(registry, store):
    arm(store)
    assert ControlStore(store.root).start_requested(REF) is True
    reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    assert ControlStore(store.root).start_requested(REF) is False


def test_clearing_poll_makes_the_thread_first_sight_again(registry, store):
    baseline(store)
    assert PollState(store).seen_comments(REF) == {"c1", "c2"}
    reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    state = PollState(store)
    assert state.is_known(REF) is False and state.seen_comments(REF) == set()


def test_resetting_one_work_item_leaves_the_others_alone(registry, store):
    register(registry)
    register(registry, ref=OTHER)
    arm(store)
    arm(store, ref=OTHER)

    reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=lambda s: False
    )

    assert registry.find_by_work_item(OTHER, include_closed=True) is not None
    assert store.section(OTHER, CONTROL) is not None


def test_a_second_reset_is_a_no_op(registry, store):
    register(registry)
    arm(store)
    reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=lambda s: False
    )
    again = reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    assert again.found is False


def test_the_index_no_longer_advertises_the_record(registry, store):
    arm(store)
    arm(store, ref=OTHER)
    reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    index = json.loads((store.root / "index.json").read_text())
    assert [entry["ref"] for entry in index["workItems"]] == [OTHER]


# -- the legacy tree must not resurrect what a reset removed ---------------------


def test_a_legacy_record_leaves_a_seal_rather_than_a_resurrectable_gap(
    tmp_path: Path, registry
):
    """A pre-issue-128 control record on disk is the trap: deleting the new
    record would let ``section()`` fall back and hand the ``start`` back."""
    root = tmp_path / ".the-loop"
    legacy = LegacyLayout(
        sessions_dir=str(root / "sessions"),
        control_dir=str(root / "sessions" / "control"),
        poll_state=str(root / "sessions" / "poll-state.json"),
    )
    Path(legacy.control_dir).mkdir(parents=True)
    slug = WorkItemRef.parse(REF).slug
    (Path(legacy.control_dir) / f"{slug}.json").write_text(
        json.dumps({"ref": REF, "command": "start", "source": "comment"})
    )
    store = WorkItemStore(root / "portable", legacy=legacy)
    assert ControlStore(store.root, legacy=legacy).start_requested(REF) is True

    outcome = reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)

    assert outcome.removed == (CONTROL,)
    record = json.loads(store.path_for(REF).read_text())
    assert record.get(SEALED) is True
    assert ControlStore(store.root, legacy=legacy).start_requested(REF) is False


# -- failures ---------------------------------------------------------------------


def test_a_failing_close_is_collected_and_the_record_still_goes(registry, store):
    register(registry)

    def close(session):
        raise RuntimeError("tmux exploded")

    outcome = reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=close
    )

    assert outcome.errors and "tmux exploded" in outcome.errors[0]
    assert outcome.ok is False and outcome.found is True
    assert registry.find_by_work_item(REF, include_closed=True) is None


def test_an_unwritable_store_is_reported_rather_than_raised(
    registry, store, monkeypatch
):
    arm(store)

    def boom(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(WorkItemStore, "write_section", boom)
    outcome = reset_work_item(WorkItemRef.parse(REF), registry=registry, store=store)
    assert outcome.ok is False and outcome.found is True
    assert "read-only file system" in outcome.errors[0]


# -- dry run ----------------------------------------------------------------------


def test_dry_run_reports_without_removing(registry, store):
    register(registry)
    arm(store)
    baseline(store)

    outcome = reset_work_item(
        WorkItemRef.parse(REF),
        registry=registry,
        store=store,
        close=lambda s: True,
        dry_run=True,
    )

    assert outcome.removed == (SESSION, CONTROL, POLL)
    assert outcome.was_live is True and outcome.dry_run is True
    assert registry.find_by_work_item(REF) is not None
    assert store.section(REF, CONTROL) is not None
    assert store.section(REF, POLL) is not None


def test_dry_run_never_closes_a_session(registry, store):
    register(registry)

    def explode(session):  # pragma: no cover - must not be reached
        raise AssertionError("a dry run must not end a session")

    reset_work_item(
        WorkItemRef.parse(REF),
        registry=registry,
        store=store,
        close=explode,
        dry_run=True,
    )


# -- enumeration for --all ---------------------------------------------------------


# -- session bindings (issue-172) ---------------------------------------------------

PR = "github:octo/repo#16"


def test_reset_removes_bindings_in_both_directions(registry, store):
    """A reset says "forget everything this machine holds about this item".

    Both directions, because a work item is on both ends of the relationship:
    inbound bindings (PRs whose events it owns) and, when the item *is* a PR, its
    own outbound one.
    """
    register(registry)
    registry.link(PR, REF)
    registry.link("github:octo/repo#17", REF)

    outcome = reset_work_item(
        WorkItemRef.parse(REF), registry=registry, store=store, close=lambda s: False
    )

    assert outcome.removed == (SESSION, LINK)
    assert registry.links_to(REF) == []
    assert registry.resolve_link(PR) is None


def test_reset_removes_a_prs_own_binding(registry, store):
    registry.link(PR, REF)
    outcome = reset_work_item(
        WorkItemRef.parse(PR), registry=registry, store=store, close=lambda s: False
    )
    assert outcome.removed == (LINK,) and outcome.ok
    assert registry.resolve_link(PR) is None


def test_a_dry_run_reports_the_binding_without_removing_it(registry, store):
    registry.link(PR, REF)
    outcome = reset_work_item(
        WorkItemRef.parse(PR), registry=registry, store=store, dry_run=True
    )
    assert outcome.removed == (LINK,)
    binding = registry.resolve_link(PR)
    assert binding is not None and binding.ref == REF  # rehearsal, not the thing


def test_work_items_with_state_reaches_a_pr_whose_only_state_is_a_binding(
    registry, store
):
    """`--all` must not leave behind the one file it invented (issue-172).

    Only the binding's **source** is enumerated: its target is already listed if
    it has a session, and claiming it from here would make `--all` report a work
    item whose sole trace is someone else's file.
    """
    registry.link(PR, REF)
    assert [item.ref for item in work_items_with_state(registry, store)] == [PR]


def test_work_items_with_state_unions_both_stores(registry, store):
    register(registry)  # session only
    arm(store, ref=OTHER)  # portable only
    refs = [item.ref for item in work_items_with_state(registry, store)]
    assert refs == sorted([REF, OTHER])


def test_work_items_with_state_deduplicates(registry, store):
    register(registry)
    arm(store)
    assert [item.ref for item in work_items_with_state(registry, store)] == [REF]


def test_work_items_with_state_ignores_strangers(registry, store, tmp_path):
    """A shared state directory holds other people's files; they are not records."""
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / "notes.json").write_text('{"hello": "world"}')
    (tmp_path / "local").mkdir(parents=True, exist_ok=True)
    (tmp_path / "local" / "scratch.json").write_text("{}")
    register(registry)
    assert [item.ref for item in work_items_with_state(registry, store)] == [REF]


def test_work_items_with_state_skips_a_sealed_tombstone(registry, store):
    """A sealed record is a work item the-loop already ended, not state: `--all`
    must not enumerate it and then report 'nothing to reset'."""
    store.root.mkdir(parents=True, exist_ok=True)
    (store.root / f"{WorkItemRef.parse(REF).slug}.json").write_text(
        json.dumps({"ref": REF, SEALED: True})
    )
    assert work_items_with_state(registry, store) == []


def test_work_items_with_state_is_empty_on_a_clean_machine(registry, store):
    assert work_items_with_state(registry, store) == []


# -- the outcome type ---------------------------------------------------------------


def test_found_is_true_when_only_an_error_happened():
    outcome = ResetOutcome(ref=REF, errors=("could not remove …",))
    assert outcome.found is True and outcome.ok is False
