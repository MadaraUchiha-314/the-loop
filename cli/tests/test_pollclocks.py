"""The machine's poll clocks (issue-382).

`lastPolledAt` and `closureCheckedAt` used to be keys of the tracked work-item
record, rewritten every cycle — which is what put a repository holding
`state.root` in permanent uncommitted-change. They are clock readings from one
machine's poller, so they live in a machine-local file now, and this suite pins
the two properties that make that safe: the store round-trips what the poller
writes, and **every** fault degrades to "no clock" rather than to an exception,
because a missing clock costs one provider question while a raised one would
cost a poll cycle.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from the_loop.pollclocks import CLOCK_KEYS, PollClockStore
from the_loop.state import StateLayout

REF = "github:octo/repo#15"
PR = "github:octo/lib#7"


def _store(tmp_path: Path) -> PollClockStore:
    return PollClockStore(tmp_path / "local" / "poll-clocks.json")


# -- the shape of the thing ---------------------------------------------------


def test_the_two_clocks_are_the_only_ones():
    assert CLOCK_KEYS == ("lastPolledAt", "closureCheckedAt")


def test_it_sits_beside_the_portable_records_where_the_layout_declares_it(tmp_path):
    layout = StateLayout(root=str(tmp_path))
    assert PollClockStore.beside(layout.portable_dir).path == Path(layout.poll_clocks)


# -- round trips --------------------------------------------------------------


def test_a_clock_survives_a_new_process(tmp_path):
    _store(tmp_path).put(REF, {"lastPolledAt": "2026-09-18T10:00:00Z"})
    assert _store(tmp_path).get(REF) == {"lastPolledAt": "2026-09-18T10:00:00Z"}


def test_each_ref_keeps_its_own_clocks(tmp_path):
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "2026-09-18T10:00:00Z"})
    store.put(PR, {"lastPolledAt": "2026-09-18T10:05:00Z"})
    # A pull request's ledger lives under its owner's record, but its clock is
    # keyed by its own ref: refs are globally unique, so the map needs no owner
    # relation (issue-382, R1.4).
    assert _store(tmp_path).all() == {
        REF: {"lastPolledAt": "2026-09-18T10:00:00Z"},
        PR: {"lastPolledAt": "2026-09-18T10:05:00Z"},
    }


def test_a_put_replaces_the_refs_clocks_wholesale(tmp_path):
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "10:00", "closureCheckedAt": "11:00"})
    store.put(REF, {"lastPolledAt": "12:00"})
    assert store.get(REF) == {"lastPolledAt": "12:00"}


def test_an_empty_put_drops_the_entry(tmp_path):
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "10:00"})
    store.put(REF, {})
    assert store.get(REF) == {} and store.all() == {}


def test_forget_removes_only_that_ref(tmp_path):
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "10:00"})
    store.put(PR, {"lastPolledAt": "10:05"})
    store.forget(REF)
    store.forget("github:octo/repo#404")  # never recorded: a no-op, not an error
    assert _store(tmp_path).all() == {PR: {"lastPolledAt": "10:05"}}


def test_the_file_is_written_where_it_was_asked_for(tmp_path):
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "10:00"})
    payload = json.loads(store.path.read_text())
    assert payload == {"clocks": {REF: {"lastPolledAt": "10:00"}}}


# -- every fault is "no clock" ------------------------------------------------


def test_an_absent_file_reads_as_no_clock(tmp_path):
    assert _store(tmp_path).get(REF) == {} and _store(tmp_path).all() == {}


def test_a_malformed_file_reads_as_no_clock(tmp_path):
    store = _store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("{not json at all")
    assert store.get(REF) == {}


def test_a_malformed_clock_reads_as_no_clock(tmp_path):
    """A value that is not a string is dropped entry by entry, not wholesale."""
    store = _store(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(
        json.dumps(
            {
                "clocks": {
                    REF: {"lastPolledAt": ["not", "a", "stamp"], "closureCheckedAt": 7},
                    PR: {"lastPolledAt": "2026-09-18T10:00:00Z"},
                    "github:octo/repo#1": "not a mapping",
                }
            }
        )
    )
    assert store.get(REF) == {}
    assert store.get("github:octo/repo#1") == {}
    assert store.get(PR) == {"lastPolledAt": "2026-09-18T10:00:00Z"}


def test_a_future_clock_is_kept_verbatim_for_the_schedule_to_judge(tmp_path):
    """Forging a clock forward defers a question; it can never act (abuse 1).

    The store is not where a future stamp is judged — the closure schedule
    already treats *not yet due* as *do nothing*, and no path writes `ended`
    from a timestamp. What matters here is that the store does not invent a
    behaviour of its own: it hands back what it was given.
    """
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "2099-01-01T00:00:00Z"})
    assert store.get(REF) == {"lastPolledAt": "2099-01-01T00:00:00Z"}


def test_an_unwritable_file_never_raises(tmp_path):
    store = PollClockStore(tmp_path / "local" / "poll-clocks.json")
    store.path.parent.mkdir(parents=True)
    os.chmod(store.path.parent, stat.S_IRUSR | stat.S_IXUSR)
    try:
        store.put(REF, {"lastPolledAt": "10:00"})  # logged, swallowed
    finally:
        os.chmod(store.path.parent, stat.S_IRWXU)
    # ...and the in-memory map still answers, so the cycle that wrote it is
    # consistent with itself even when the disk refused.
    assert store.get(REF) == {"lastPolledAt": "10:00"}


def test_an_unknown_key_in_a_refs_entry_is_dropped(tmp_path):
    """Only the two declared clocks live here — the file is not a second ledger."""
    store = _store(tmp_path)
    store.put(REF, {"lastPolledAt": "10:00", "seenComments": "c1"})
    assert _store(tmp_path).get(REF) == {"lastPolledAt": "10:00"}
