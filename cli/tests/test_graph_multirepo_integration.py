"""One work item, several repositories (issue-183) — end to end through the seams.

The unit tests beside this file pin each piece; these walk the path an event
actually takes when a work item's contributions span repositories:

    a PR in octo/infra closes octo/app#15
        → the router maps it to the work item in the ORIGIN repository
        → graphlink walks that PR's inner loop
        → whose state lands under the ONE spec chain in the origin checkout
        → and the outer `implementation` gate holds until it finishes

Every step is exercised against the **shipped** router, runtime and hooks — no
network, no fixtures beyond a git checkout and the files a work item has anyway.
"""

from __future__ import annotations

import subprocess

import pytest

from the_loop.control import ControlConfig
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.contract import HookContext, WorkItem
from the_loop.graph.hooks.loops import await_inner_loops, inner_loop_state_dir
from the_loop.graph.state import GraphState
from the_loop.graphlink import GraphLink, GraphLinkConfig
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import extract_work_items

#: The work item lives in the repository the ticket was created in…
WI = WorkItemRef.parse("github:octo/app#15")
#: …and this pull request delivers its share of the work from another one.
FOREIGN_PR = WorkItemRef.parse("github:octo/infra#7")
#: A pull request in the origin repository, deliberately sharing the number.
ORIGIN_PR = WorkItemRef.parse("github:octo/app#7")


@pytest.fixture()
def origin(tmp_path):
    """A checkout of the ORIGIN repository, with the work item's spec chain."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "https://github.com/octo/app.git",
        ],
        check=True,
    )
    spec = tmp_path / "docs" / "specs" / "issue-15"
    spec.mkdir(parents=True)
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        "ticketing:\n  github:\n    owner: octo\n    repo: app\n"
        "workflow:\n  specDir: docs/specs\n  outerLoop:\n    surface: issue\n",
        encoding="utf-8",
    )
    return tmp_path


def _declare(spec_dir, repos):
    (spec_dir / "execution-log.md").write_text(
        "---\ntype: execution-log\nworkItem: issue-15\nrepos:\n"
        + "".join(f"  - {repo}\n" for repo in repos)
        + "---\n\n# Execution Log\n",
        encoding="utf-8",
    )


def _link():
    return GraphLink(
        GraphLinkConfig(enabled=True), control=ControlConfig(enabled=False)
    )


def _outer_ctx(origin, config=None):
    spec = origin / "docs" / "specs" / "issue-15"
    return HookContext(
        work_item=WorkItem(ref=WI.ref, id="issue-15", spec_dir=spec),
        node={"id": "implementation"},
        boundary="exit",
        repo=origin,
        config=config or {"originRepo": "octo/app"},
    )


def test_a_cross_repo_pull_request_routes_to_the_work_item():
    """
    Feature: one work item, several repositories
      Scenario: a pull request in a contributing repository reaches its work item
        Given a pull request in octo/infra whose body closes octo/app#15
        When the event is routed
        Then the work item in the ORIGIN repository is named before the PR itself

    Requirement: docs/specs/issue-183/requirements.md R1.5
    """
    payload = {
        "repository": {"full_name": "octo/infra"},
        "pull_request": {
            "number": 7,
            "body": "Closes octo/app#15",
            "head": {"ref": "feature/no-number"},
        },
    }
    refs = [r.ref for r in extract_work_items("pull_request", payload)]
    assert refs == ["github:octo/app#15", "github:octo/infra#7"]


def test_the_inner_loop_of_a_foreign_pr_lands_under_the_origin_spec_chain(origin):
    """
    Feature: one work item, several repositories
      Scenario: a contributing repository's pull request walks its own inner loop
        Given a work item whose spec chain lives in the origin repository
        When a pull request in octo/infra enters its inner loop
        Then its state is written under docs/specs/issue-15/pr-loops/octo__infra/pr-7/
        And the work item's own pointer is untouched

    Requirement: docs/specs/issue-183/requirements.md R1.1, R1.3
    """
    _link().on_pr_spawn(WI, FOREIGN_PR, str(origin), session_id="s-1", runner="tmux")

    spec = origin / "docs" / "specs" / "issue-15"
    inner = GraphState.load(inner_loop_state_dir(spec, 7, "octo/infra"), "issue-15")
    assert inner.current_node == "implementation"
    assert (spec / "pr-loops" / "octo__infra" / "pr-7" / "graph-state.json").is_file()
    assert GraphState.load(spec, "issue-15").current_node == ""


def test_two_repositories_share_a_pr_number_without_sharing_a_loop(origin):
    """
    Feature: one work item, several repositories
      Scenario: pull request #7 exists in both repositories
        Given inner loops for octo/app#7 and octo/infra#7
        When each is advanced
        Then they keep separate pointers under separate state directories

    Requirement: docs/specs/issue-183/requirements.md R1.3, R1.4
    """
    link = _link()
    link.on_pr_spawn(WI, ORIGIN_PR, str(origin), session_id="s-1", runner="tmux")
    link.on_pr_spawn(WI, FOREIGN_PR, str(origin), session_id="s-2", runner="tmux")
    link.on_pr_close(WI, ORIGIN_PR, str(origin), merged=True)

    spec = origin / "docs" / "specs" / "issue-15"
    assert GraphState.load(inner_loop_state_dir(spec, 7), "issue-15").current_node == (
        "complete"
    )
    assert (
        GraphState.load(
            inner_loop_state_dir(spec, 7, "octo/infra"), "issue-15"
        ).current_node
        == "implementation"
    )


def test_the_outer_gate_holds_until_every_declared_repository_finishes(origin):
    """
    Feature: one work item, several repositories
      Scenario: the work item waits at implementation for all its repositories
        Given a work item declaring repos: [octo/app, octo/infra]
        And only octo/app's pull request has finished
        When the outer implementation node's exit chain runs
        Then it waits, naming the repository that has no finished loop
        And it passes once that repository's pull request merges

    Requirement: docs/specs/issue-183/requirements.md R4.1, R4.2
    """
    spec = origin / "docs" / "specs" / "issue-15"
    _declare(spec, ["octo/app", "octo/infra"])
    link = _link()
    link.on_pr_spawn(WI, ORIGIN_PR, str(origin), session_id="s-1", runner="tmux")
    link.on_pr_close(WI, ORIGIN_PR, str(origin), merged=True)

    held = await_inner_loops(_outer_ctx(origin))
    assert held.status == "wait" and held.data["missing_repos"] == ["octo/infra"]

    link.on_pr_spawn(WI, FOREIGN_PR, str(origin), session_id="s-2", runner="tmux")
    assert await_inner_loops(_outer_ctx(origin)).status == "wait"  # started, unfinished
    link.on_pr_close(WI, FOREIGN_PR, str(origin), merged=True)
    assert await_inner_loops(_outer_ctx(origin)).status == "pass"


def test_the_origin_repos_config_reaches_the_gate(origin):
    """The origin repository is read from the work item's own checkout, so the
    gate can tell a top-level pr-<n>/ from a contributing repository's loop."""
    runtime = build_runtime(origin)
    assert runtime.config["originRepo"] == "octo/app"
    assert runtime.config["outerLoopSurface"] == "issue"

    spec = origin / "docs" / "specs" / "issue-15"
    _declare(spec, ["octo/app"])
    _link().on_pr_spawn(WI, ORIGIN_PR, str(origin), session_id="s-1", runner="tmux")
    ctx = _outer_ctx(origin, config=dict(runtime.config))
    assert await_inner_loops(ctx).status == "wait"  # started, not finished
    _link().on_pr_close(WI, ORIGIN_PR, str(origin), merged=True)
    assert await_inner_loops(ctx).status == "pass"


def test_a_cross_repo_link_does_not_arm_a_work_item(origin, monkeypatch):
    """Abuse case 3: routing says which work item an event is about; it never
    says that the work item may be worked. An unstarted one still drops."""
    link = _link()
    monkeypatch.setattr(link, "_awaiting_start", lambda work_item: True)
    link.on_pr_spawn(WI, FOREIGN_PR, str(origin), session_id="s-1", runner="tmux")

    spec = origin / "docs" / "specs" / "issue-15"
    assert not (spec / "pr-loops").exists()
