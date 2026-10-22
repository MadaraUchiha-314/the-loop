"""The handoff's state and graph schema (issue-517, task 3).

* ``WorkItemState`` carries ``handoff``, ``handoffDemoted`` and
  ``claudeArtifactUrl`` — loaded, saved and archived, and **absent** from every
  item that never had them, so a legacy file saves byte-identical (T10).
* A node may be ``requiresHandoff: true``; it must be skippable, and
  ``declared_skips`` routes around it with ``via: no-handoff`` unless the state
  carries a handoff (T1, R7.1).

Requirement: docs/specs/issue-517/requirements.md R6.1, R7.1, R7.4
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_loop import archive
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.model import GraphConfigError, compile_graph
from the_loop.graph.runtime import NO_HANDOFF, Runtime
from the_loop.graph.state import STATE_FILENAME, WorkItemState

WORK_ITEM = "issue-1"

HANDOFF = {
    "version": 1,
    "stage": "requirements-settled",
    "enter": "requirements-approval",
    "artifacts": [{"name": "requirements.md", "sha256": "ab" * 32}],
    "carriedBy": "branch",
    "branch": "the-loop/issue-1-x",
    "author": "dev",
    "commentUrl": "https://github.com/octo/repo/issues/1#issuecomment-9",
    "recordedAt": "2026-10-21T10:00:00+00:00",
}
DEMOTED = [
    {
        "node": "requirements-definition",
        "artifact": "requirements.md",
        "reason": "missing section Security considerations",
    }
]
ARTIFACT_URL = "https://claude.ai/artifact/0123abcd"


def _graph(**import_node):
    node = {"id": "import-handoff", "requiresHandoff": True, "skippable": True}
    node.update(import_node)
    return {
        "start": "import-handoff",
        "nodes": [
            node,
            {"id": "design"},
            {"id": "done", "terminal": True},
        ],
        "edges": [
            {"from": "import-handoff", "to": "design", "on": "pass"},
            {"from": "import-handoff", "to": "design", "on": "skipped"},
            {"from": "design", "to": "done", "on": "pass"},
        ],
    }


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


# -- graph schema ----------------------------------------------------------------


def test_requires_handoff_is_parsed():
    graph = compile_graph(_graph())
    node = graph.nodes["import-handoff"]
    assert node.requires_handoff is True
    assert node.as_mapping()["requiresHandoff"] is True
    assert graph.nodes["design"].requires_handoff is False


def test_requires_handoff_without_skippable_is_a_compile_error():
    raw = _graph(skippable=False)
    with pytest.raises(GraphConfigError, match="requiresHandoff"):
        compile_graph(raw)


# -- declared_skips --------------------------------------------------------------


def test_a_requires_handoff_node_is_skipped_without_a_handoff(repo):
    """
    Feature: import-handoff stays out of every other item's walk
      Scenario: a work item with no handoff
        Given a node marked requiresHandoff
        When the declared skips are read for a state with no handoff
        Then the node is skipped via no-handoff

    Requirement: R7.1
    """
    rt = Runtime(repo, graph=compile_graph(_graph()))
    skips = rt.declared_skips(WorkItemState(work_item=WORK_ITEM))
    assert skips["import-handoff"] == {"via": NO_HANDOFF}
    assert NO_HANDOFF == "no-handoff"
    assert "design" not in skips


def test_a_requires_handoff_node_runs_with_a_handoff(repo):
    rt = Runtime(repo, graph=compile_graph(_graph()))
    state = WorkItemState(work_item=WORK_ITEM, handoff=dict(HANDOFF))
    assert "import-handoff" not in rt.declared_skips(state)


def test_an_empty_handoff_is_no_handoff(repo):
    rt = Runtime(repo, graph=compile_graph(_graph()))
    state = WorkItemState(work_item=WORK_ITEM, handoff={})
    assert rt.declared_skips(state)["import-handoff"] == {"via": NO_HANDOFF}


def test_the_walk_routes_around_the_node_without_a_handoff(repo):
    rt = Runtime(repo, graph=compile_graph(_graph()))
    rt.advance(WORK_ITEM)
    state = WorkItemState.load(repo / "docs" / "specs" / WORK_ITEM, WORK_ITEM)
    assert state.current_node != "import-handoff"
    assert state.nodes["import-handoff"].outcome == "skipped"


# -- state round trip ------------------------------------------------------------


def test_the_three_keys_round_trip(repo):
    spec = repo / "docs" / "specs" / WORK_ITEM
    WorkItemState(
        work_item=WORK_ITEM,
        handoff=dict(HANDOFF),
        handoff_demoted=[dict(d) for d in DEMOTED],
        claude_artifact_url=ARTIFACT_URL,
    ).save(spec)
    data = json.loads((spec / STATE_FILENAME).read_text())
    assert data["handoff"] == HANDOFF
    assert data["handoffDemoted"] == DEMOTED
    assert data["claudeArtifactUrl"] == ARTIFACT_URL
    loaded = WorkItemState.load(spec, WORK_ITEM)
    assert loaded.handoff == HANDOFF
    assert loaded.handoff_demoted == DEMOTED
    assert loaded.claude_artifact_url == ARTIFACT_URL


def test_malformed_values_load_as_absent(repo):
    """The file is agent-writable: only the documented shapes are read."""
    spec = repo / "docs" / "specs" / WORK_ITEM
    (spec / STATE_FILENAME).write_text(
        json.dumps(
            {
                "workItem": WORK_ITEM,
                "handoff": "yes",
                "handoffDemoted": [{"node": "x"}, "junk", 3],
                "claudeArtifactUrl": ["x"],
            }
        )
    )
    loaded = WorkItemState.load(spec, WORK_ITEM)
    assert loaded.handoff == {}
    assert loaded.handoff_demoted == [{"node": "x"}]
    assert loaded.claude_artifact_url == ""


# -- T10: a legacy state is unchanged --------------------------------------------

LEGACY = {
    "version": 1,
    "workItem": WORK_ITEM,
    "currentNode": "design",
    "nodes": {},
    "decisions": {},
    "forced": [],
    "parked": None,
    "completions": {},
    "skips": {},
    "optIns": {},
    "surface": "",
    "sessionPerPr": "",
    "harness": "",
    "model": "",
    "effort": "",
    "claudeArtifact": False,
    "repos": [],
    "pullRequests": [],
    "loop": "",
    "phase": "",
}


def test_a_legacy_state_saves_byte_identical(repo):
    """
    Feature: compatibility
      Scenario: a work-item-state.json with none of the new keys
        Given a state file written before issue-517
        When it is loaded and saved again
        Then the bytes are unchanged and no new key appears

    Requirement: compatibility NFR (testing-plan T10)
    """
    spec = repo / "docs" / "specs" / WORK_ITEM
    path = spec / STATE_FILENAME
    original = json.dumps(LEGACY, indent=2) + "\n"
    path.write_text(original, encoding="utf-8")
    state = WorkItemState.load(spec, WORK_ITEM)
    assert state.handoff == {} and state.handoff_demoted == []
    assert state.claude_artifact_url == ""
    state.save(spec)
    assert path.read_text(encoding="utf-8") == original
    for key in ("handoff", "handoffDemoted", "claudeArtifactUrl"):
        assert key not in WorkItemState(work_item=WORK_ITEM).as_dict()


def _archive_runtime(root: Path):
    return build_runtime(root, spec_root="docs/specs", origin_repo="octo/repo")


def test_a_legacy_state_archives_without_the_new_keys(repo):
    spec = repo / "docs" / "specs" / WORK_ITEM
    (spec / STATE_FILENAME).write_text(json.dumps(LEGACY), encoding="utf-8")
    record = archive.terminal_record(_archive_runtime(repo), WORK_ITEM)
    assert record is not None
    for key in ("handoff", "handoffDemoted", "claudeArtifactUrl"):
        assert key not in record


def test_the_archive_carries_a_filtered_copy_of_the_three_keys(repo):
    spec = repo / "docs" / "specs" / WORK_ITEM
    data = dict(LEGACY)
    data["handoff"] = dict(HANDOFF, source="Claude chat\x1b[2J", junk={"a": 1})
    data["handoffDemoted"] = DEMOTED + [
        {"node": "made-up", "artifact": "x.md", "reason": "r"}
    ]
    data["claudeArtifactUrl"] = ARTIFACT_URL
    (spec / STATE_FILENAME).write_text(json.dumps(data), encoding="utf-8")

    record = archive.terminal_record(_archive_runtime(repo), WORK_ITEM)

    assert record is not None
    handoff = record["handoff"]
    assert handoff["stage"] == "requirements-settled"
    assert handoff["enter"] == "requirements-approval"
    assert handoff["author"] == "dev"
    assert handoff["commentUrl"] == HANDOFF["commentUrl"]
    assert "source" not in handoff and "junk" not in handoff
    assert record["handoffDemoted"] == [
        {"node": "requirements-definition", "artifact": "requirements.md"}
    ]
    assert record["claudeArtifactUrl"] == ARTIFACT_URL
