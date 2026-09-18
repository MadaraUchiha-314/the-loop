"""Unit tests for the core facade's work-item read surface (issue-161, T1)."""

import pytest

from the_loop.core import workitems
from the_loop.pollclocks import PollClockStore
from the_loop.state import layout_from_config, legacy_layout
from the_loop.workitem import WorkItemStore


REF_A = "github:octo/repo#7"
REF_B = "github:octo/repo#9"


def _seed(root):
    layout = layout_from_config({"state": {"root": str(root / ".the-loop")}})
    store = WorkItemStore(layout.portable_dir, legacy=legacy_layout(layout))
    store.write_section(REF_B, "poll", {"recentDeliveries": []})
    store.write_section(REF_A, "control", {"command": "start-execution"})
    return {"state": {"root": str(root / ".the-loop")}}


def test_list_work_items_returns_records_ordered_by_ref(tmp_path):
    config = _seed(tmp_path)
    records = workitems.list_work_items(config)
    assert [r["ref"] for r in records] == [REF_A, REF_B]
    assert records[0]["control"]["command"] == "start-execution"


def test_get_work_item_returns_the_record(tmp_path):
    config = _seed(tmp_path)
    record = workitems.get_work_item(REF_B, config)
    assert record["ref"] == REF_B
    assert "poll" in record


def test_get_work_item_missing_is_lookup_error(tmp_path):
    config = _seed(tmp_path)
    with pytest.raises(LookupError):
        workitems.get_work_item("github:octo/repo#404", config)


def test_get_work_item_malformed_ref_is_value_error(tmp_path):
    with pytest.raises(ValueError):
        workitems.get_work_item(
            "not-a-ref", {"state": {"root": str(tmp_path / ".the-loop")}}
        )


# -- the two halves, rejoined (issue-382) -------------------------------------


def test_the_served_record_carries_this_machines_poll_clocks(tmp_path):
    """R2.4 — the split is about storage, not about what a local reader sees.

    `lastPolledAt` left the tracked record in issue-382, and the dashboard's
    *last activity* has no other fallback for an item with no session — so the
    read surface joins the machine's clocks back onto the record it serves.
    """
    config = _seed(tmp_path)
    layout = layout_from_config(config)
    clocks = PollClockStore(layout.poll_clocks)
    clocks.put(REF_B, {"lastPolledAt": "2026-09-18T10:00:00Z"})

    assert workitems.get_work_item(REF_B, config)["poll"] == {
        "recentDeliveries": [],
        "lastPolledAt": "2026-09-18T10:00:00Z",
    }
    served = {r["ref"]: r for r in workitems.list_work_items(config)}
    assert served[REF_B]["poll"]["lastPolledAt"] == "2026-09-18T10:00:00Z"
    # The record itself still holds none of it.
    store = WorkItemStore(layout.portable_dir)
    assert "lastPolledAt" not in (store.section(REF_B, "poll") or {})


def test_each_pull_requests_ledger_gets_its_own_clock(tmp_path):
    """R2.4 — a pull request's ledger is keyed under its owner; its clock is not."""
    config = _seed(tmp_path)
    layout = layout_from_config(config)
    pr = "github:octo/lib#3"
    store = WorkItemStore(layout.portable_dir)
    store.write_pull_request_ledger(REF_A, pr, {"seenComments": ["IC_1"]})
    PollClockStore(layout.poll_clocks).put(pr, {"lastPolledAt": "2026-09-18T11:00:00Z"})

    record = workitems.get_work_item(REF_A, config)
    assert record["pullRequests"][pr] == {
        "seenComments": ["IC_1"],
        "lastPolledAt": "2026-09-18T11:00:00Z",
    }


def test_a_clock_never_invents_a_section(tmp_path):
    """A record with no `poll` does not grow one because a clock lingers."""
    config = _seed(tmp_path)
    PollClockStore(layout_from_config(config).poll_clocks).put(
        REF_A, {"lastPolledAt": "2026-09-18T10:00:00Z"}
    )
    assert workitems.get_work_item(REF_A, config).get("poll") is None
