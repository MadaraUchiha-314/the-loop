"""The index of ``portable/``, and the URL a ref now carries (issue-130).

``portable/`` is generated state with an unusual property: it is *tracked*, so a
person reads it — in a pull-request diff, or with ``jq``. Issue #130 is about that
reader. Two things they were missing: a list of what the directory holds, and a
link to the work item each record is about.

What these pin, in order of how much they would hurt:

1. **The index is derived, never trusted.** It is rebuilt from the directory on
   every write and read by nothing. That is what makes a stale index cosmetic —
   and what makes a *forged* one inert, which matters because this file is
   tracked in git and therefore proposable by anyone who can open a pull request.
2. **A failed index write never fails the record write.** The record is a fact
   about the work item; the index is a convenience. Losing an arming ``start``
   because a convenience could not be written would be a silent disarm.
3. **A URL is derived or omitted, never guessed.** A ref's owner/repo come from
   webhook payloads. A link built from an unchecked name can point somewhere
   other than the work item it claims to be.
"""

import json

import pytest

from the_loop.control import ControlStore
from the_loop.poller import PollState
from the_loop.sessions import WorkItemRef
from the_loop.state import LegacyLayout, StateLayout, legacy_layout
from the_loop.workitem import INDEX_FILE, WorkItemStore

REF = "github:octo/repo#15"
SLUG = "github-octo-repo-15.json"
URL = "https://github.com/octo/repo/issues/15"


def _index(portable) -> list:
    return json.loads((portable / INDEX_FILE).read_text())["workItems"]


def _legacy(tmp_path) -> LegacyLayout:
    return legacy_layout(StateLayout(root=str(tmp_path)))


# -- the URL ---------------------------------------------------------------------


def test_a_record_carries_the_work_items_url(tmp_path):
    """R3.1/R3.2 — the link is added beside the ref, not instead of it."""
    ControlStore(tmp_path / "portable").record(REF, "start", actor="octocat")

    record = json.loads((tmp_path / "portable" / SLUG).read_text())
    assert record["ref"] == REF, "the machine identity keeps its form"
    assert record["url"] == URL


def test_a_record_written_by_an_older_version_gains_the_url(tmp_path):
    """R3.4 — convergence on the next write, rather than a migration."""
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / SLUG).write_text(
        json.dumps({"ref": REF, "control": {"command": "stop"}})
    )

    ControlStore(portable).record(REF, "start")
    assert json.loads((portable / SLUG).read_text())["url"] == URL


def test_a_work_item_on_another_host_links_to_that_host(tmp_path):
    """R5 — a GitHub Enterprise work item is not on github.com, and says so.

    The host is identified where the work item enters the-loop (see
    `test_routing.py` / `test_poller.py`) and carried on the ref, so everything
    downstream — this record, this index, `sessions list` — is right about it
    without knowing anything about hosts.
    """
    ref = "github:ghe.corp.example/octo/repo#15"
    ControlStore(tmp_path / "portable").record(ref, "start")

    record = json.loads(
        (
            tmp_path / "portable" / "github-ghe.corp.example-octo-repo-15.json"
        ).read_text()
    )
    assert record["ref"] == ref
    assert record["url"] == "https://ghe.corp.example/octo/repo/issues/15"
    assert _index(tmp_path / "portable")[0]["url"] == record["url"]


@pytest.mark.parametrize(
    "ref",
    [
        "jira:octo/repo#15",  # no URL layout is known for a reserved provider
        "github:oc to/repo#15",  # whitespace in the owner
        "github:octo/re po#15",  # ...and in the repo
    ],
)
def test_a_ref_that_is_not_github_shaped_gets_no_url(tmp_path, ref):
    """R3.3 — fail closed. No link beats a link somewhere else."""
    assert WorkItemRef.parse(ref).url == ""

    ControlStore(tmp_path / "portable").record(ref, "start")
    record = json.loads(WorkItemStore(tmp_path / "portable").path_for(ref).read_text())
    assert "url" not in record
    assert _index(tmp_path / "portable")[0].keys() >= {"ref", "file", "sections"}
    assert "url" not in _index(tmp_path / "portable")[0]


@pytest.mark.parametrize(
    "ref",
    [
        "github:octo/repo/../../evil#15",  # extra segments: a path injection
        "github:octo/repo/sub#15",  # three segments whose first is not a host
        "github:ev il.com/octo/repo#15",  # a host that is not a host
    ],
)
def test_a_ref_with_an_unreadable_path_is_rejected_outright(ref):
    """R5.4 — `[<host>/]<owner>/<repo>` is the whole grammar; nothing else parses.

    Before the host existed, `parse` split the path at the *first* slash and let
    the remainder be the "repo", so these produced a work item whose identity was
    a path fragment. Rejecting them is the stronger guarantee, and it is what
    makes interpolating the parts into a URL safe rather than merely guarded.
    """
    with pytest.raises(ValueError):
        WorkItemRef.parse(ref)


# -- the index -------------------------------------------------------------------


def test_the_index_lists_every_record_with_its_url(tmp_path):
    """R1.1/R2.1/R2.2 — the question `portable/` could not answer before."""
    portable = tmp_path / "portable"
    control = ControlStore(portable)
    control.record(REF, "start", actor="octocat")
    control.record("github:octo/repo#16", "pause")
    state = PollState(WorkItemStore(portable))
    state.baseline_comments(REF, ["IC_1"], "2026-07-31T00:00:00Z")
    state.save()

    assert _index(portable) == [
        {
            "ref": REF,
            "url": URL,
            "file": SLUG,
            "sections": ["control", "poll"],
        },
        {
            "ref": "github:octo/repo#16",
            "url": "https://github.com/octo/repo/issues/16",
            "file": "github-octo-repo-16.json",
            "sections": ["control"],
        },
    ]


def test_the_index_drops_a_record_that_is_removed(tmp_path):
    """R1.2 — the directory and its index end a work item together."""
    portable = tmp_path / "portable"
    control = ControlStore(portable)
    control.record(REF, "start")
    control.record("github:octo/repo#16", "start")

    control.clear(REF)
    assert [entry["ref"] for entry in _index(portable)] == ["github:octo/repo#16"]


def test_entries_are_ordered_by_ref(tmp_path):
    """R1.5 — a stable order, so a diff shows only what changed."""
    portable = tmp_path / "portable"
    control = ControlStore(portable)
    for number in (30, 4, 100, 4_000):
        control.record(f"github:octo/repo#{number}", "start")

    refs = [entry["ref"] for entry in _index(portable)]
    assert refs == sorted(refs)


def test_the_index_goes_when_the_last_record_goes(tmp_path):
    """R1.3 — an empty `portable/` holds nothing, not an empty husk."""
    portable = tmp_path / "portable"
    control = ControlStore(portable)
    control.record(REF, "start")
    assert (portable / INDEX_FILE).is_file()

    control.clear(REF)
    assert not (portable / INDEX_FILE).exists()
    assert list(portable.iterdir()) == []


def test_the_index_is_rebuilt_not_trusted(tmp_path):
    """R1.4 — derived from the directory, so a forged index cannot survive.

    This file is tracked in git, which makes it proposable by anyone who can open
    a pull request. Nothing reads it, and the next write overwrites it wholesale —
    the two properties that keep "a stranger can edit it" uninteresting.
    """
    portable = tmp_path / "portable"
    control = ControlStore(portable)
    control.record(REF, "start")
    (portable / INDEX_FILE).write_text(
        json.dumps({"workItems": [{"ref": "github:octo/repo#999", "file": "made-up"}]})
    )

    control.record(REF, "stop")  # any write at all
    assert [entry["ref"] for entry in _index(portable)] == [REF]


def test_a_sealed_record_is_indexed_as_sealed(tmp_path):
    """R2.3 — a record with no sections is explained, not merely empty."""
    legacy = _legacy(tmp_path)
    control_dir = tmp_path / "sessions" / "control"
    control_dir.mkdir(parents=True)
    (control_dir / SLUG).write_text(json.dumps({"ref": REF, "command": "start"}))

    ControlStore(tmp_path / "portable", legacy=legacy).clear(REF)

    assert _index(tmp_path / "portable") == [
        {"ref": REF, "url": URL, "file": SLUG, "sections": [], "sealed": True}
    ]


def test_a_corrupt_neighbour_is_left_out_of_the_index(tmp_path):
    """R2.4 — a stray file is skipped, and cannot fail the write beside it."""
    portable = tmp_path / "portable"
    ControlStore(portable).record(REF, "start")
    (portable / "github-octo-repo-16.json").write_text("{not json")
    (portable / "notes.json").write_text(json.dumps({"hello": "world"}))

    ControlStore(portable).record(REF, "stop")
    assert [entry["ref"] for entry in _index(portable)] == [REF]


def test_the_index_is_not_read_as_a_work_item_record(tmp_path):
    """R1.7 — the index lives among the records without being one."""
    portable = tmp_path / "portable"
    ControlStore(portable).record(REF, "start")

    assert list(WorkItemStore(portable).refs()) == [REF]


def test_an_unwritable_index_does_not_fail_the_record_write(tmp_path, caplog):
    """R1.6 — the convenience may fail; the fact may not.

    A `start` that raised because a *derived* file could not be written would
    leave a work item unarmed with the error attributed to the wrong thing. The
    index path is made unwritable here by putting a directory where the file
    goes, which is what `os.replace` (and `unlink`) refuse.
    """
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / INDEX_FILE).mkdir()

    ControlStore(portable).record(REF, "start")
    assert json.loads((portable / SLUG).read_text())["control"]["command"] == "start"
    assert "index" in caplog.text.lower()

    # ...and the same on the way out: removing the last record still works.
    assert ControlStore(portable).clear(REF) is True
    assert not (portable / SLUG).exists()
