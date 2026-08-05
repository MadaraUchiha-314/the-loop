"""Unit tests for the core facade's work-item read surface (issue-161, T1)."""

import pytest

from the_loop.core import workitems
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
