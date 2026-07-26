"""Unit tests for the per-work-item pause ledger (issue-98)."""

import json

from the_loop.sessions import PauseStore, WorkItemRef

REF = "github:octo/repo#15"
LABEL = "the-loop: paused"


def store(tmp_path, label=LABEL):
    return PauseStore(tmp_path / "paused.json", paused_label=label)


def test_missing_file_means_nothing_is_paused(tmp_path):
    assert store(tmp_path).is_paused(REF) is False
    assert store(tmp_path).list_paused() == []


def test_pause_is_durable_and_idempotent(tmp_path):
    first = store(tmp_path)
    assert first.pause(REF, reason="waiting on review") is True
    assert first.pause(REF) is False  # already paused

    reopened = store(tmp_path)  # a fresh process reads the same state
    record = reopened.record(REF)
    assert record is not None
    assert record.reason == "waiting on review"
    assert record.paused_at.endswith("Z")


def test_resume_clears_the_record_and_is_idempotent(tmp_path):
    paused = store(tmp_path)
    paused.pause(REF)
    assert paused.resume(REF) is True
    assert paused.resume(REF) is False
    assert store(tmp_path).is_paused(REF) is False


def test_accepts_a_work_item_ref_object(tmp_path):
    paused = store(tmp_path)
    paused.pause(WorkItemRef.parse(REF), reason="parked")
    assert paused.is_paused(REF) is True
    assert paused.state(WorkItemRef.parse(REF)).paused is True


def test_a_label_pause_records_who_did_it(tmp_path):
    """The label writes the ledger (decision-041) — it is never read as state."""
    paused = store(tmp_path)
    paused.pause(REF, reason="label added by @octocat", source="label", by="octocat")
    state = paused.state(REF)
    assert state.paused is True
    assert state.sources == ["label"]
    assert state.by == "octocat"
    assert "octocat" in state.reason


def test_the_ledger_is_the_only_thing_state_consults(tmp_path):
    """Raw label presence is NOT a pause: an unauthorized labeller changes
    nothing, and an unauthorized label *removal* cannot resume a paused item."""
    paused = store(tmp_path)
    assert paused.state(REF).paused is False  # label on the ticket, no record

    paused.pause(REF, source="label", by="octocat")
    assert paused.state(REF).paused is True  # label deleted upstream: still paused


def test_a_cli_pause_records_the_local_source(tmp_path):
    paused = store(tmp_path)
    paused.pause(REF, reason="parked")
    assert paused.state(REF).sources == ["local"]
    assert paused.state(REF).by == ""


def test_corrupt_ledger_degrades_to_nothing_paused(tmp_path, caplog):
    path = tmp_path / "paused.json"
    path.write_text("{not json")
    paused = PauseStore(path, paused_label=LABEL)
    assert paused.is_paused(REF) is False
    assert paused.list_paused() == []
    assert any("unreadable pause ledger" in r.message for r in caplog.records)


def test_ledger_with_a_wrong_shape_is_ignored(tmp_path):
    path = tmp_path / "paused.json"
    path.write_text(json.dumps({"paused": ["not", "a", "mapping"]}))
    assert PauseStore(path).is_paused(REF) is False


def test_out_of_process_write_is_picked_up(tmp_path):
    """The daemon holds a store while `sessions pause` writes from a terminal."""
    daemon = store(tmp_path)
    assert daemon.is_paused(REF) is False

    cli = store(tmp_path)
    cli.pause(REF, reason="from another terminal")

    assert daemon.is_paused(REF) is True  # re-read on the mtime change
    cli.resume(REF)
    assert daemon.is_paused(REF) is False


def test_list_paused_returns_every_record(tmp_path):
    paused = store(tmp_path)
    paused.pause("github:octo/repo#2")
    paused.pause("github:octo/repo#1", reason="later")
    refs = [record.ref for record in paused.list_paused()]
    assert refs == ["github:octo/repo#1", "github:octo/repo#2"]
