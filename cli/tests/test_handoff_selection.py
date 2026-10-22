"""Phase selection for a handed-off item (issue-517, task 6, design §C7).

A handoff pre-fills phase selection; it never bypasses it. The checklist unticks
every phase before the record's ``enter`` node, says so in one line naming the
developer and the record, and the replier's ``the-loop execute`` is still what
authorizes the walk. The skips that reply produces before ``enter`` carry the
record's URL, so ``the-loop check`` reports them as *skipped by handoff*, never
as passed and never as a bare declaration.

Golden files under ``tests/fixtures/handoff/`` hold the checklist with and
without a handoff (``.txt``, so markdownlint leaves them alone). The no-handoff
one was captured before this change: an item without a record must see the
same comment, byte for byte. Regenerate the handoff one with
``THE_LOOP_REGEN_HANDOFF_GOLDEN=1`` and review the diff.

Requirement: docs/specs/issue-517/requirements.md R6.3, R6.4, R6 table, R7.1
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pytest

from the_loop.core.handoff import (
    HandoffArtifact,
    HandoffRecord,
    sha256_text,
    stage_entry,
)
from the_loop.graph import hooks  # noqa: F401 — registers the built-ins
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks import selection
from the_loop.graph.model import load_graph
from the_loop.graph.runtime import Runtime
from the_loop.graph.state import WorkItemState

FIXTURES = Path(__file__).parent / "fixtures" / "handoff"
REGEN = os.environ.get("THE_LOOP_REGEN_HANDOFF_GOLDEN") == "1"

WORK_ITEM = "issue-1"
REF = "github:o/r#1"
COMMENT_URL = "https://github.com/o/r/issues/1#issuecomment-9"
SPEC_ARTIFACT = "https://claude.ai/artifact/abc"

#: The checklist the golden files render: the shipped outer loop, one harness.
CONFIG = {"authorizedUsers": ["owner"], "harness": "claude"}

BRAINSTORM = (
    "# Brainstorm\n\n## Problem / opportunity\n\nPeople retype chats.\n\n"
    "## Open questions\n\nNone left.\n"
)
REQUIREMENTS = (
    "# Requirements\n\n## Requirements\n\n1. The system SHALL hand off.\n\n"
    "## Security considerations\n\nThe record is untrusted input.\n"
)
DESIGN = (
    "# Design\n\n## Overview\n\nA record.\n\n## Architecture\n\nOne node.\n\n"
    "## Components & interfaces\n\nC1.\n\n## Data models\n\nNone.\n\n"
    "## Error handling\n\nDemote.\n\n## Security design\n\nUntrusted.\n\n"
    "## Testing strategy\n\nPytest.\n"
)
TESTING_PLAN = (
    "# Testing plan\n\n## Test matrix\n\nT1.\n\n## Scenarios & requirement trace\n\n"
    "R1.\n\n## Verification environment\n\nCI.\n\n## Evidence plan\n\nLogs.\n\n"
    "## Verification results\n\nPending.\n"
)

#: Each R6-table row: (stage, files carried, the node the walk lands on).
ROWS = {
    "exploring": ({"brainstorm.md": BRAINSTORM}, "brainstorming"),
    "brainstorm-settled": ({"brainstorm.md": BRAINSTORM}, "brainstorm-approval"),
    "requirements-settled": (
        {"brainstorm.md": BRAINSTORM, "requirements.md": REQUIREMENTS},
        "requirements-approval",
    ),
    "design-settled+plan": (
        {
            "requirements.md": REQUIREMENTS,
            "design.md": DESIGN,
            "testing-plan.md": TESTING_PLAN,
        },
        "design-approval",
    ),
    "design-settled": (
        {"requirements.md": REQUIREMENTS, "design.md": DESIGN},
        "test-planning",
    ),
}


def _record(
    stage: str,
    files: Mapping[str, str],
    spec_artifact: str = "",
    author: str = "dev",
    comment_url: str = COMMENT_URL,
) -> HandoffRecord:
    stage = stage.split("+", 1)[0]
    return HandoffRecord(
        version=1,
        stage=stage,
        enter=stage_entry(stage, files),
        artifacts=tuple(HandoffArtifact(n, sha256_text(t)) for n, t in files.items()),
        carried_by="artifact" if spec_artifact else "branch",
        branch="the-loop/issue-1-x",
        spec_artifact=spec_artifact,
        spec_artifact_sha256="0" * 64 if spec_artifact else "",
        author=author,
        comment_url=comment_url,
    )


def _ctx(handoff: Optional[HandoffRecord] = None) -> HookContext:
    return HookContext(
        work_item=WorkItem(ref="github:o/r#7", id="issue-7", spec_dir=Path(".")),
        node={"id": "phase-selection"},
        boundary="entry",
        repo=Path("."),
        config=dict(CONFIG),
        graph=load_graph(),
        handoff=handoff.as_dict() if handoff else {},
    )


def _rows(body: str) -> Dict[str, bool]:
    """Phase rows only: ``{node: ticked}`` under the Phases heading."""
    out: Dict[str, bool] = {}
    section = body.split("### 🧩 Phases", 1)[1].split("####", 1)[0]
    for line in section.splitlines():
        if line.startswith("- ["):
            out[line[6:].strip()] = line[3] == "x"
    return out


def _golden(name: str, body: str) -> str:
    path = FIXTURES / name
    if REGEN:
        path.write_text(body, encoding="utf-8")
    return path.read_text(encoding="utf-8")


# -- the checklist (T6) ---------------------------------------------------------


def test_the_checklist_for_a_requirements_settled_handoff_matches_its_snapshot():
    """
    Feature: phase selection for a handed-off item
      Scenario: the checklist for a requirements-settled handoff
        Given a handoff record by @dev at requirements settled
        When the phase-selection checklist is rendered
        Then it matches the reviewed golden file byte for byte

    Requirement: R6.4 (T6)
    """
    files, _ = ROWS["requirements-settled"]
    body = selection._checklist_body(_ctx(_record("requirements-settled", files)))
    assert body == _golden("checklist_requirements_settled.txt", body)


def test_the_phases_before_enter_are_unticked_and_the_rest_ticked():
    files, _ = ROWS["requirements-settled"]
    rows = _rows(
        selection._checklist_body(_ctx(_record("requirements-settled", files)))
    )
    assert rows["brainstorming"] is False
    assert rows["brainstorm-approval"] is False
    assert rows["requirements-definition"] is False
    assert rows["requirements-approval"] is True
    assert rows["design"] is True
    assert rows["human-approval"] is True


def test_an_exploring_handoff_ticks_brainstorming_back_on():
    """The default unticks brainstorming; a handoff entering it must not."""
    files, _ = ROWS["exploring"]
    rows = _rows(selection._checklist_body(_ctx(_record("exploring", files))))
    assert rows["brainstorming"] is True
    assert rows["brainstorm-approval"] is True


def test_the_handoff_line_names_the_developer_the_stage_and_the_record():
    files, _ = ROWS["requirements-settled"]
    body = selection._checklist_body(_ctx(_record("requirements-settled", files)))
    line = (
        f"Handed off by @dev at *requirements settled* ([record]({COMMENT_URL}))"
        " — earlier phases are unticked."
    )
    assert line in body
    heading = body.index("### 🧩 Phases")
    assert heading < body.index(line) < body.index("- [", heading)


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://github.com/o/r/issues/1#issuecomment-9",
        "https://evil.example/o/r/issues/1",
        "https://github.com/o/r/issues/1) [click](https://evil.example",
    ],
)
def test_a_record_url_that_is_not_a_github_https_link_is_not_linked(url):
    files, _ = ROWS["requirements-settled"]
    body = selection._checklist_body(
        _ctx(_record("requirements-settled", files, comment_url=url))
    )
    assert "Handed off by @dev at *requirements settled* — earlier" in body
    assert "[record]" not in body
    assert url not in body


def test_an_author_that_is_not_a_login_is_not_rendered_as_a_mention():
    files, _ = ROWS["requirements-settled"]
    record = _record("requirements-settled", files, author="dev *bold* [x](y)")
    body = selection._checklist_body(_ctx(record))
    assert "Handed off by a developer at" in body
    assert "*bold*" not in body


def test_a_named_spec_artifact_leaves_the_claude_artifact_row_ticked():
    files, _ = ROWS["requirements-settled"]
    record = _record("requirements-settled", files, spec_artifact=SPEC_ARTIFACT)
    body = selection._checklist_body(_ctx(record))
    assert f"- [x] `{selection.CLAUDE_ARTIFACT_TOKEN}`" in body


def test_an_item_with_no_handoff_gets_todays_checklist_byte_for_byte():
    """
    Feature: phase selection for a handed-off item
      Scenario: an item with no handoff walks exactly as before
        Given a work item without a handoff record
        When the phase-selection checklist is rendered
        Then it is byte-identical to the checklist captured before issue-517

    Requirement: R7.1, compatibility NFR
    """
    body = selection._checklist_body(_ctx())
    assert body == (FIXTURES / "checklist_no_handoff.txt").read_text(encoding="utf-8")
    assert "Handed off" not in body


# -- the walk (T2) --------------------------------------------------------------


class _FakeGitHub:
    """Serves the ticket's comments and records what the-loop posts."""

    def __init__(self) -> None:
        self.comments: List[Dict[str, Any]] = []
        self.posted: List[str] = []

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op == "list-comments":
            return {"comments": list(self.comments)}
        if op == "add-comment":
            self.posted.append(str(params.get("body") or ""))
        return {}


@pytest.fixture()
def fake_github(monkeypatch):
    provider = _FakeGitHub()
    monkeypatch.setattr(
        "the_loop.graph.integrations.resolve", lambda target, config: provider
    )
    return provider


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    return tmp_path


def _spec(repo: Path) -> Path:
    return repo / "docs" / "specs" / WORK_ITEM


def _runtime(repo: Path) -> Runtime:
    return Runtime(repo, config={"authorizedUsers": ["@dev"]})


def _walk(
    repo: Path, fake: _FakeGitHub, record: Optional[HandoffRecord], files
) -> WorkItemState:
    """Start → checklist → an untouched `the-loop execute` → import-handoff."""
    runtime = _runtime(repo)
    runtime.start(WORK_ITEM, ref=REF, handoff=record)
    checklist = next(p for p in fake.posted if selection.SELECTION_MARKER in p)
    fake.comments = [{"author": "the-loop", "body": checklist}]
    reply = {"comments": [{"author": "@dev", "body": "the-loop execute"}]}
    runtime.advance(WORK_ITEM, ref=REF, event=reply)
    for name, text in files.items():
        (_spec(repo) / name).write_text(text, encoding="utf-8")
    if record is not None:
        state = WorkItemState.load(_spec(repo), WORK_ITEM)
        assert state.current_node == "import-handoff"
        runtime.advance(WORK_ITEM, ref=REF)
    return WorkItemState.load(_spec(repo), WORK_ITEM)


def _assert_row_walk(repo, fake, row: str) -> WorkItemState:
    files, landing = ROWS[row]
    record = _record(row, files)
    after = _walk(repo, fake, record, files)
    assert after.current_node == landing
    assert after.handoff_demoted == []
    graph = load_graph()
    order = [n.id for n in graph.ordered()]
    before = order[: order.index(landing)]
    for node, decl in after.skips.items():
        if decl.get("via") != "selection":
            continue
        # Every selection skip is before the starting step, stamped with the
        # record, and signed by the replier.
        assert node in before
        assert decl["handoff"] == COMMENT_URL
        assert decl["by"] == "@dev"
    return after


def test_an_exploring_handoff_walks_to_brainstorming(repo, fake_github):
    """
    Feature: a handed-off item starts at the right step
      Scenario: an exploring handoff walks to brainstorming
        Given a handoff record at still exploring carrying a partial brainstorm.md
        And the replier says the-loop execute with the boxes untouched
        When the walk passes import-handoff
        Then the current node is brainstorming

    Requirement: R6 table, R6.4
    """
    after = _assert_row_walk(repo, fake_github, "exploring")
    assert "brainstorming" not in after.skips


def test_a_brainstorm_settled_handoff_walks_to_brainstorm_approval(repo, fake_github):
    """
    Feature: a handed-off item starts at the right step
      Scenario: a brainstorm-settled handoff walks to brainstorm-approval
        Given a handoff record at brainstorm settled carrying brainstorm.md
        And the replier says the-loop execute with the boxes untouched
        When the walk passes import-handoff
        Then the current node is brainstorm-approval
        And brainstorming is skipped by handoff

    Requirement: R6 table, R6.3, R6.4
    """
    after = _assert_row_walk(repo, fake_github, "brainstorm-settled")
    assert after.skips["brainstorming"]["handoff"] == COMMENT_URL


def test_a_requirements_settled_handoff_walks_to_requirements_approval(
    repo, fake_github
):
    """
    Feature: a handed-off item starts at the right step
      Scenario: a requirements-settled handoff walks to requirements-approval
        Given a handoff record by @dev at requirements settled
        And the checklist unticks brainstorming through requirements-definition
        And @dev says the-loop execute with the boxes untouched
        When the walk passes import-handoff
        Then the current node is requirements-approval
        And each earlier phase is declared skipped by @dev, citing the record

    Requirement: R6.1, R6.3, R6.4
    """
    after = _assert_row_walk(repo, fake_github, "requirements-settled")
    assert {n for n, d in after.skips.items() if d.get("via") == "selection"} == {
        "brainstorming",
        "brainstorm-approval",
        "requirements-definition",
    }


def test_a_design_settled_handoff_with_a_testing_plan_walks_to_design_approval(
    repo, fake_github
):
    """
    Feature: a handed-off item starts at the right step
      Scenario: a design-settled handoff with a testing plan walks to design-approval
        Given a handoff record at design settled carrying design.md and testing-plan.md
        And the replier says the-loop execute with the boxes untouched
        When the walk passes import-handoff
        Then the current node is design-approval

    Requirement: R6 table
    """
    after = _assert_row_walk(repo, fake_github, "design-settled+plan")
    assert after.skips["test-planning"]["handoff"] == COMMENT_URL


def test_a_design_settled_handoff_without_a_testing_plan_walks_to_test_planning(
    repo, fake_github
):
    """
    Feature: a handed-off item starts at the right step
      Scenario: a design-settled handoff without a testing plan walks to test-planning
        Given a handoff record at design settled carrying design.md only
        And the replier says the-loop execute with the boxes untouched
        When the walk passes import-handoff
        Then the current node is test-planning

    Requirement: R6 table
    """
    after = _assert_row_walk(repo, fake_github, "design-settled")
    assert "test-planning" not in after.skips
    assert after.skips["design"]["handoff"] == COMMENT_URL


def test_check_reports_a_handed_off_phase_as_skipped_by_handoff(repo, fake_github):
    """
    Feature: a handed-off item starts at the right step
      Scenario: check reports the phases before the starting step as skipped by handoff
        Given a requirements-settled handoff walked to requirements-approval
        When the-loop check reports the work item
        Then requirements-definition reads skipped by handoff, declared by @dev
        And it is never reported as passed

    Requirement: R6.3
    """
    _assert_row_walk(repo, fake_github, "requirements-settled")
    report = _runtime(repo).status(WORK_ITEM)
    node = next(n for n in report.nodes if n.node == "requirements-definition")
    assert node.status == "skip"
    text = " ".join(node.messages)
    assert "skipped by handoff (declared by @dev)" in text
    assert COMMENT_URL in text
    assert "skipped by declaration" not in text


def test_an_item_with_no_handoff_walks_exactly_as_before(repo, fake_github):
    """
    Feature: a handed-off item starts at the right step
      Scenario: an item with no handoff walks exactly as before
        Given a work item without a handoff record
        When the replier says the-loop execute with the boxes untouched
        Then the checklist is today's, import-handoff is skipped via no-handoff
        And the default skips carry no handoff and read skipped by declaration

    Requirement: R7.1, compatibility NFR
    """
    after = _walk(repo, fake_github, None, {})
    checklist = next(p for p in fake_github.posted if selection.SELECTION_MARKER in p)
    assert "Handed off" not in checklist
    assert after.nodes["import-handoff"].outcome == "skipped"
    assert after.current_node == "requirements-definition"
    assert set(after.skips) >= {"brainstorming", "brainstorm-approval"}
    assert all("handoff" not in d for d in after.skips.values())
    report = _runtime(repo).status(WORK_ITEM)
    node = next(n for n in report.nodes if n.node == "brainstorming")
    assert "skipped by declaration" in " ".join(node.messages)


def test_the_confirmation_names_the_phases_skipped_by_handoff(repo, fake_github):
    _assert_row_walk(repo, fake_github, "requirements-settled")
    confirmation = next(p for p in fake_github.posted if "selection recorded" in p)
    assert "*skipped by handoff*" in confirmation
    assert "`requirements-definition`" in confirmation
