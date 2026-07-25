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


def test_label_alone_pauses_and_records_its_source(tmp_path):
    state = store(tmp_path).state(REF, labels=["bug", LABEL])
    assert state.paused is True
    assert state.sources == ["label"]
    assert state.reason == ""


def test_local_and_label_compose_as_or(tmp_path):
    paused = store(tmp_path)
    paused.pause(REF, reason="parked")
    both = paused.state(REF, labels=[LABEL])
    assert both.paused is True
    assert both.sources == ["local", "label"]
    # Removing the label leaves the local pause standing (neither overrides).
    assert paused.state(REF, labels=[]).sources == ["local"]


def test_unrelated_labels_do_not_pause(tmp_path):
    assert store(tmp_path).state(REF, labels=["the-loop: auto-execute"]).paused is False


def test_empty_label_config_never_matches(tmp_path):
    assert store(tmp_path, label="").state(REF, labels=[""]).paused is False


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
