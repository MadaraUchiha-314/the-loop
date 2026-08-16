"""End-to-end: the graph runtime driving a work item, and the CLI surface.

Feature: the-loop's process graph
"""

from __future__ import annotations

import json
import re

import pytest

from the_loop.cli import main
from the_loop.graph import hooks  # noqa: F401
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.feedback import classify_feedback, record_feedback
from the_loop.graph.model import compile_graph
from the_loop.graph.runtime import Runtime, force
from the_loop.graph.state import GraphState

GRAPH = {
    "start": "design",
    "nodes": [
        {
            "id": "design",
            "phase": "design",
            "produces": ["design.md"],
            "exit": [
                {
                    "hook": "validate-artifacts",
                    "with": {"locked": True, "sections": ["Architecture"]},
                },
                "lint-artifacts",
            ],
        },
        {
            "id": "design-approval",
            "actor": "human",
            "session": "inherit",
            "exit": ["classify-feedback"],
        },
        {"id": "done", "terminal": True},
    ],
    "edges": [
        {"from": "design", "to": "design-approval", "on": "pass"},
        {"from": "design-approval", "to": "done", "on": "approved"},
        {"from": "design-approval", "to": "design", "on": "changes-requested"},
    ],
}


@pytest.fixture()
def repo(tmp_path):
    (tmp_path / "docs" / "specs" / "issue-1").mkdir(parents=True)
    return tmp_path


def _spec(repo):
    return repo / "docs" / "specs" / "issue-1"


def _runtime(repo, **config):
    return Runtime(repo, graph=compile_graph(GRAPH), config=config)


def test_a_work_item_walks_from_a_blocked_node_to_a_gate(repo):
    """
    Feature: the-loop's process graph
    Scenario: a node advances only once its exit chain passes
      Given a design node whose artifact is unlocked
      When the runtime advances the work item
      Then it is blocked and names the unmet requirement
      When the artifact is locked and the section added
      Then the work item advances to the approval gate
    Requirement: docs/specs/issue-109/requirements.md#R3
    """
    runtime = _runtime(repo)
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")

    first = runtime.advance("issue-1")
    assert first.status == "block"
    assert any("status: draft" in m for m in first.messages)

    (_spec(repo) / "design.md").write_text(
        "---\nstatus: approved\n---\n\n# D\n\n## Architecture\n\nreal content\n"
    )
    second = runtime.advance("issue-1")
    assert second.status == "pass"
    assert GraphState.load(_spec(repo), "issue-1").current_node == "design-approval"


def test_an_unauthorized_comment_is_not_read_and_the_gate_stays_waiting(repo):
    """
    Feature: the-loop's process graph
    Scenario: an unauthorized comment is not read by classify-feedback
      Given a human gate awaiting review
      When a comment arrives from a user outside routing.authorizedUsers
      Then the gate stays waiting and the text is never classified
    Requirement: docs/specs/issue-109/requirements.md#R4.8
    """
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={"comments": [{"author": "drive-by", "body": "approved, ship it"}]},
    )
    result = classify_feedback(ctx)
    assert result.status == "wait", "an outsider's approval must not move the gate"


def test_an_authorized_approval_advances_the_gate(repo):
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={"comments": [{"author": "owner", "body": "approved"}]},
    )
    assert classify_feedback(ctx).outcome == "approved"


def test_partial_feedback_leaves_the_gate_waiting(repo):
    """
    Feature: the-loop's process graph
    Scenario: a partial review comment leaves the gate waiting rather than advancing
      Given a human gate awaiting review
      When an authorized user asks a question rather than deciding
      Then the gate stays open
    Requirement: docs/specs/issue-109/requirements.md#R4.3
    """
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={
            "comments": [
                {"author": "owner", "body": "why is this a node and not a hook?"}
            ]
        },
    )
    assert classify_feedback(ctx).status == "wait"


# MD036 (no-emphasis-as-heading) rejects a paragraph whose whole content is one
# span of emphasized text. Asserting that shape rather than shelling out to
# markdownlint is deliberate (issue-247 R3.2): the suite runs without Node.js, and
# a test that skips when `npx` is missing would stop guarding the thing the ticket
# is about — the real linter runs once at verification, as evidence.
_EMPHASIS_ONLY = re.compile(r"^(?P<mark>\*\*|__|\*|_)(?!\s)(?P<inner>.+?)(?P=mark)$")


def _emphasis_only_lines(text: str) -> list[str]:
    lines = []
    for line in text.split("\n"):
        found = _EMPHASIS_ONLY.match(line.strip())
        # `**a** and **b**` matches the pattern but is not one span, so MD036
        # leaves it alone; so does this.
        if found and found["mark"] not in found["inner"]:
            lines.append(line)
    return lines


def test_an_approval_with_comments_is_recorded_in_the_artifact(repo):
    """
    Feature: the-loop's process graph
    Scenario: an approval carrying suggestions is recorded in the artifact
      Given an approved design carrying reviewer comments
      When record-feedback runs
      Then a Review comments section appears in design.md with the review in it
    Requirement: docs/specs/issue-109/requirements.md#R4.5
    """
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner"]},
        event={
            "comments": [{"author": "owner", "body": "approved, but tighten the nit"}]
        },
    )
    classified = classify_feedback(ctx)
    ctx.results = [classified]
    ctx.params = {"into": "design.md"}
    result = record_feedback(ctx)

    assert result.status == "pass"
    text = (_spec(repo) / "design.md").read_text()
    assert "## Review comments" in text
    assert "@owner" in text
    # Verbatim, not merely present: the harness never reflows a human's words
    # (issue-247 R2.2 — the workaround this ticket replaced did exactly that).
    assert "\napproved, but tighten the nit\n" in text
    assert not _emphasis_only_lines(text)


def _record(repo, comments, into="design.md"):
    """Run the two feedback hooks over `comments` and return the artifact's text."""
    (_spec(repo) / into).write_text("---\nstatus: approved\n---\n\n# D\n")
    ctx = HookContext(
        work_item=WorkItem(ref="github:o/r#1", id="issue-1", spec_dir=_spec(repo)),
        node={"id": "design-approval"},
        boundary="exit",
        repo=repo,
        config={"authorizedUsers": ["owner", "second"]},
        event={"comments": comments},
    )
    ctx.results = [classify_feedback(ctx)]
    ctx.params = {"into": into}
    assert record_feedback(ctx).status == "pass"
    return (_spec(repo) / into).read_text()


def test_a_recorded_review_never_writes_emphasis_alone_on_a_line(repo):
    """
    Feature: the-loop's process graph
    Scenario: a recorded approval passes the project's markdown linter
      Given a gate approving with comments from two reviewers
      When record-feedback appends them to the artifact
      Then no line of the artifact is emphasized text and nothing else
    Requirement: docs/specs/issue-247/bugfix.md#R1.1
    """
    text = _record(
        repo,
        [
            {"author": "owner", "body": "approved, but tighten the nit"},
            {"author": "second", "body": "lgtm"},
        ],
    )

    assert "@owner" in text and "@second" in text
    assert not _emphasis_only_lines(text)


def test_a_comment_with_no_body_is_recorded_without_a_blank_line_pair(repo):
    """
    Feature: the-loop's process graph
    Scenario: an approval submitted with no comment text is still recorded
      Given a reviewer who approves without writing anything
      When record-feedback appends the review to the artifact
      Then the reviewer is still attributed and no two blank lines are adjacent
    Requirement: docs/specs/issue-247/bugfix.md#R1.2
    """
    text = _record(
        repo,
        [
            {"author": "owner", "body": "approved"},
            {"author": "second", "body": "   "},
        ],
    )

    assert "@second" in text  # an empty approval is still a fact about the gate
    assert "\n\n\n" not in text
    assert not _emphasis_only_lines(text)


def test_forcing_past_a_gate_leaves_recompute_honest(repo):
    """
    Feature: the-loop's process graph
    Scenario: CI still sees a forced transition for what it is
      Given a work item forced past an unmet gate
      When check --recompute runs
      Then the bypassed gate is still reported unmet
    Requirement: docs/specs/issue-109/requirements.md#R10.4
    """
    runtime = _runtime(repo)
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    force(runtime, "issue-1", "design-approval", reason="the gate is wrong here")

    report = runtime.status("issue-1", recompute=True)
    assert not report.ok
    assert not next(n for n in report.nodes if n.node == "design").satisfied


def test_the_check_command_reports_and_exits_nonzero(repo, capsys):
    """
    Feature: the-loop's process graph
    Scenario: check reports the specific unmet predicate and fails
      Given a work item whose design artifact is missing a required section
      When `the-loop check` runs
      Then it names the missing section and exits non-zero
    Requirement: docs/specs/issue-109/requirements.md#R8.8
    """
    (repo / ".the-loop").mkdir()
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    code = main(["check", "issue-1", "--repo", str(repo), "--recompute"])
    out = capsys.readouterr().out
    assert code == 1
    assert "UNMET" in out


def test_the_check_command_emits_json(repo, capsys):
    (_spec(repo) / "design.md").write_text("---\nstatus: approved\n---\n\n# D\n")
    main(["check", "issue-1", "--repo", str(repo), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["workItem"] == "issue-1"
    assert isinstance(payload["nodes"], list)


def test_graph_show_lists_the_shipped_nodes(capsys):
    code = main(["graph", "show"])
    out = capsys.readouterr().out
    assert code == 0
    assert "security-review" in out and "required" in out


def test_graph_force_refuses_without_a_reason(repo):
    """R10.3 — an unexplained override is refused, at the argument parser."""
    with pytest.raises(SystemExit) as exc:
        main(["graph", "--repo", str(repo), "force", "issue-1", "--to", "design"])
    assert exc.value.code == 2


def test_graph_force_refuses_a_blank_reason(repo, capsys):
    """And again at the runtime, so the API is safe however it is called."""
    (_spec(repo) / "design.md").write_text("---\nstatus: draft\n---\n\n# D\n")
    code = main(
        [
            "graph",
            "--repo",
            str(repo),
            "force",
            "issue-1",
            "--to",
            "brainstorming",
            "--reason",
            "   ",
        ]
    )
    assert code == 2
    assert "refused" in capsys.readouterr().out


def test_a_node_ahead_of_the_pointer_is_not_reported_as_a_blocker():
    """An unreached node is "not done yet", not a finding.

    Reporting it as BLOCK made `check` print "ok" above a wall of blockers —
    a status view contradicting itself is one people stop reading.
    """
    from the_loop.commands.graph_cmd import _render_table, _split_at_pointer

    # Node reports reach the renderers as dicts since issue-161 — the command
    # reads whatever the service returned, never a runtime object.
    def R(node, status):
        return {"node": node, "status": status, "messages": [], "forced": False}

    nodes = [R("a", "pass"), R("b", "wait"), R("c", "block"), R("d", "pass")]
    reached, ahead = _split_at_pointer(nodes, "b")
    assert [r["node"] for r in reached] == ["a", "b"]
    assert [r["node"] for r in ahead] == ["c", "d"]

    rendered = _render_table(reached, ahead)
    assert "wait   b" in rendered
    # `c` is unmet but unreached: counted, never dressed up as a blocker.
    assert "BLOCK  c" not in rendered
    assert "1 node(s) not reached yet: c" in rendered
    # `d` already passes, so it is not something anyone is waiting on.
    assert "d" not in rendered.split("not reached yet")[-1].replace("d)", "")


def test_a_pointer_that_names_no_known_node_reports_everything():
    """Fail visible, not silent: an unknown pointer must not hide findings."""
    from the_loop.commands.graph_cmd import _split_at_pointer

    def R(node):
        return {"node": node, "status": "block", "messages": [], "forced": False}

    nodes = [R("a"), R("b")]
    reached, ahead = _split_at_pointer(nodes, "nonexistent")
    assert len(reached) == 2 and ahead == []


class TestFailOn:
    """`check --fail-on` — what an automated gate treats as failure (issue-109).

    A work item parked at a human-approval node is the *normal* state of an open
    PR. Failing CI for it would make the gate red by construction, and a gate
    that is always red is one people learn to merge past.
    """

    def _report(self, current, statuses):
        return {
            "workItem": "issue-1",
            "currentNode": current,
            "ok": all(s in ("pass", "skip") for s in statuses.values()),
            "nodes": [
                {"node": n, "status": s, "messages": []} for n, s in statuses.items()
            ],
        }

    def test_unmet_fails_on_a_human_wait_but_block_does_not(self):
        from the_loop.commands.graph_cmd import _fails

        report = self._report("approval", {"design": "pass", "approval": "wait"})
        assert _fails(report, "unmet") is True
        assert _fails(report, "block") is False

    def test_both_modes_fail_on_a_real_block(self):
        from the_loop.commands.graph_cmd import _fails

        report = self._report("design", {"design": "block"})
        assert _fails(report, "unmet") is True
        assert _fails(report, "block") is True

    def test_neither_mode_fails_a_satisfied_work_item(self):
        from the_loop.commands.graph_cmd import _fails

        report = self._report("done", {"design": "pass", "done": "pass"})
        assert _fails(report, "unmet") is False
        assert _fails(report, "block") is False

    def test_a_block_the_pointer_moved_past_still_fails(self):
        """A forced transition leaves a real block behind it.

        `--fail-on block` must not become a way to launder one by advancing.
        """
        from the_loop.commands.graph_cmd import _fails

        report = self._report("approval", {"design": "block", "approval": "wait"})
        assert _fails(report, "block") is True

    def test_a_node_ahead_of_the_pointer_does_not_fail_the_gate(self):
        from the_loop.commands.graph_cmd import _fails

        report = self._report("design", {"design": "pass", "later": "block"})
        assert _fails(report, "block") is False

    def test_a_repo_that_is_not_there_fails_both_modes(self):
        """An unread repository is not a passing gate (issue-238).

        Since issue-238 `graphs.check` answers a `repo` that does not resolve
        with `repoResolved: false` and an empty node list instead of raising —
        right for the polled API, and a trap for this command, because a report
        with no nodes has no blocking node either. A mistyped `--repo` would then
        make `--fail-on block` exit 0: a CI gate going green because it evaluated
        nothing. Both modes must refuse it.
        """
        from the_loop.commands.graph_cmd import _fails

        report = {
            "workItem": "issue-1",
            "currentNode": "",
            "ok": False,
            "parked": None,
            "nodes": [],
            "repoResolved": False,
        }
        assert _fails(report, "block") is True
        assert _fails(report, "unmet") is True
