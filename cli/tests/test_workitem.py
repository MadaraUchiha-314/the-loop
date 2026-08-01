"""The portable work-item record: two sections, one file (issue-128).

What these pin, in order of how much they would hurt:

1. **Sections are independent.** Two writers share the record — execution control
   and the poller — so a write must be read-modify-write. A poll cycle clobbering
   a ``start`` recorded a moment earlier by the other ingress would silently
   disarm a work item.
2. **The upgrade shim reads the pre-issue-128 locations.** Missing them would
   re-forward a whole comment thread, or forget what was armed.
3. **An empty record is removed**, so ``portable/`` lists the work items the-loop
   actually knows something about.
"""

import json

from the_loop.control import ControlStore
from the_loop.poller import PollState
from the_loop.state import LegacyLayout, StateLayout, legacy_layout
from the_loop.workitem import CONTROL, INDEX_FILE, POLL, WorkItemStore

REF = "github:octo/repo#15"
SLUG = "github-octo-repo-15.json"


def test_both_halves_of_a_work_item_live_in_one_file(tmp_path):
    store = WorkItemStore(tmp_path / "portable")
    ControlStore(tmp_path / "portable").record(REF, "start", actor="octocat")
    state = PollState(store)
    state.baseline_comments(REF, ["IC_1"], "2026-07-31T00:00:00Z")
    state.save()

    record = json.loads((tmp_path / "portable" / SLUG).read_text())
    assert record["ref"] == REF
    assert record["control"]["command"] == "start"
    assert record["poll"]["seenComments"] == ["IC_1"]
    # One work item, one record — beside the directory's derived index (issue-130).
    records = [
        p.name for p in (tmp_path / "portable").glob("*.json") if p.name != INDEX_FILE
    ]
    assert records == [SLUG]


def test_a_poll_cycle_does_not_clobber_a_concurrent_control_command(tmp_path):
    """The read-modify-write rule, from the direction that would hurt."""
    store = WorkItemStore(tmp_path / "portable")
    state = PollState(store)
    state.baseline_comments(REF, ["IC_1"], "2026-07-31T00:00:00Z")
    state.save()

    # The other ingress records a start *after* the poller loaded its ledger...
    ControlStore(tmp_path / "portable").record(REF, "start", actor="octocat")
    state.note_spawn_attempt(REF, "d-1")
    state.save()  # ...and this flush must not erase it.

    record = json.loads((tmp_path / "portable" / SLUG).read_text())
    assert record["control"]["command"] == "start"
    assert record["poll"]["spawn"]["attempts"] == 1


def test_clearing_control_leaves_the_poll_ledger_alone(tmp_path):
    store = WorkItemStore(tmp_path / "portable")
    control = ControlStore(tmp_path / "portable")
    control.record(REF, "start")
    state = PollState(store)
    state.baseline_comments(REF, ["IC_1"], "2026-07-31T00:00:00Z")
    state.save()

    assert control.clear(REF) is True
    assert control.get(REF) is None
    poll = store.section(REF, POLL)
    assert poll is not None and poll["seenComments"] == ["IC_1"]


def test_a_record_with_neither_section_is_removed(tmp_path):
    control = ControlStore(tmp_path / "portable")
    control.record(REF, "start")
    assert (tmp_path / "portable" / SLUG).is_file()
    control.clear(REF)
    assert not (tmp_path / "portable" / SLUG).exists()


def test_a_corrupt_record_reads_as_nothing_recorded(tmp_path):
    root = tmp_path / "portable"
    root.mkdir()
    (root / SLUG).write_text("{not json")
    store = WorkItemStore(root)
    assert store.section(REF, CONTROL) is None
    assert ControlStore(root).start_requested(REF) is False  # fail closed


def test_refs_lists_what_is_on_disk(tmp_path):
    control = ControlStore(tmp_path / "portable")
    control.record(REF, "start")
    control.record("github:octo/repo#16", "pause")
    assert sorted(WorkItemStore(tmp_path / "portable").refs()) == [
        "github:octo/repo#15",
        "github:octo/repo#16",
    ]


# -- the upgrade shim -----------------------------------------------------------


def _legacy(tmp_path) -> LegacyLayout:
    return legacy_layout(StateLayout(root=str(tmp_path)))


def test_a_pre_128_control_record_is_still_honoured(tmp_path):
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(
        json.dumps({"ref": REF, "command": "start", "actor": "octocat"})
    )

    store = ControlStore(tmp_path / "portable", legacy=legacy)
    assert store.start_requested(REF) is True, (
        "an upgrade that forgot a start would leave a labelled work item armed "
        "but never worked, with no error anywhere"
    )


def test_a_pre_128_poll_ledger_is_still_honoured(tmp_path):
    legacy = _legacy(tmp_path)
    (tmp_path / "sessions").mkdir(parents=True)
    (tmp_path / "sessions" / "poll-state.json").write_text(
        json.dumps({"items": {REF: {"seenComments": ["IC_1", "IC_2"]}}})
    )

    state = PollState(WorkItemStore(tmp_path / "portable", legacy=legacy))
    assert state.is_known(REF) is True, "a re-baselined thread re-forwards its history"
    assert state.seen_comments(REF) == {"IC_1", "IC_2"}


def test_the_pre_106_poll_state_is_still_honoured(tmp_path, monkeypatch):
    # Two layouts ago. Same reason: adopting an empty ledger re-forwards.
    monkeypatch.chdir(tmp_path)
    legacy = legacy_layout(StateLayout())
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "poll-state.json").write_text(
        json.dumps({"items": {REF: {"seenComments": ["IC_9"]}}})
    )

    state = PollState(WorkItemStore(tmp_path / ".the-loop" / "portable", legacy=legacy))
    assert state.seen_comments(REF) == {"IC_9"}


def test_an_adopted_section_is_written_forward_not_left_behind(tmp_path):
    legacy = _legacy(tmp_path)
    (tmp_path / "sessions").mkdir(parents=True)
    old = tmp_path / "sessions" / "poll-state.json"
    old.write_text(json.dumps({"items": {REF: {"seenComments": ["IC_1"]}}}))

    state = PollState(WorkItemStore(tmp_path / "portable", legacy=legacy))
    state.resolve_comment(REF, "IC_2")
    state.save()

    record = json.loads((tmp_path / "portable" / SLUG).read_text())
    assert record["poll"]["seenComments"] == ["IC_1", "IC_2"]
    # The old file is left untouched — this is a read shim, not a destructive move.
    assert json.loads(old.read_text())["items"][REF]["seenComments"] == ["IC_1"]


def test_the_new_record_wins_over_the_legacy_one(tmp_path):
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(json.dumps({"ref": REF, "command": "start"}))

    store = ControlStore(tmp_path / "portable", legacy=legacy)
    store.record(REF, "stop", actor="octocat")
    recorded = store.get(REF)
    assert recorded is not None and recorded.command == "stop"
    assert store.start_requested(REF) is False, (
        "a stop recorded on the new layout must not be overridden by the stale "
        "start still sitting in the old one"
    )


def test_ending_a_work_item_is_not_undone_by_the_old_tree(tmp_path):
    """The shim must not resurrect what a `stop` deliberately removed.

    Found in self-review: the first version consulted the old tree whenever a
    section was absent, so clearing control at the end of a work item read the
    stale `start` straight back out of `sessions/control/` and re-armed an item
    that had just finished — the precise opposite of a durable stop.
    """
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(json.dumps({"ref": REF, "command": "start"}))

    store = ControlStore(tmp_path / "portable", legacy=legacy)
    assert store.start_requested(REF) is True  # adopted, as intended
    store.record(REF, "start")  # written forward
    store.clear(REF)  # ...and the work item ends

    assert store.get(REF) is None
    assert store.start_requested(REF) is False


def test_a_forgotten_ledger_stays_forgotten(tmp_path):
    """Same failure, the poller's side: a reopened item must be first-sight."""
    legacy = _legacy(tmp_path)
    (tmp_path / "sessions").mkdir(parents=True)
    (tmp_path / "sessions" / "poll-state.json").write_text(
        json.dumps({"items": {REF: {"seenComments": ["IC_1"]}}})
    )

    state = PollState(WorkItemStore(tmp_path / "portable", legacy=legacy))
    assert state.is_known(REF) is True
    state.forget(REF)  # the work item ended
    assert state.is_known(REF) is False, (
        "a reopened item would skip re-baselining and never spawn a fresh session"
    )


def test_the_seal_is_per_section_not_per_record(tmp_path):
    """The poller writing first must not orphan the old control record.

    The first fix for the test above sealed the whole record, which read well
    until you notice the ordinary upgrade sequence: the poll cycle usually
    touches a work item before any control command does. Sealing per record
    meant the poller's own write hid the `start` in the old tree, and the item
    silently disarmed — trading one silent failure for another.
    """
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(json.dumps({"ref": REF, "command": "start"}))

    state = PollState(WorkItemStore(tmp_path / "portable", legacy=legacy))
    state.baseline_comments(REF, ["IC_1"], "2026-07-31T00:00:00Z")
    state.save()  # a record now exists, written by the poller alone

    assert ControlStore(tmp_path / "portable", legacy=legacy).start_requested(REF) is (
        True
    )


def test_an_ended_item_stays_ended_across_a_restart(tmp_path):
    """The tombstone is durable, because the old tree outlives the process."""
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(json.dumps({"ref": REF, "command": "start"}))

    ControlStore(tmp_path / "portable", legacy=legacy).clear(REF)

    # A fresh store — as after a daemon restart — reads the same answer.
    restarted = ControlStore(tmp_path / "portable", legacy=legacy)
    assert restarted.get(REF) is None
    assert restarted.start_requested(REF) is False
