"""PR-scoped specs end to end (issue-543): testing-plan row T2.

Each scenario drives the real graph runtime (``build_runtime``) and the real
verb (``core.graphs.pr_spec``) over two real git checkouts — the origin, holding
the work item's chain and state, and a pull request's — with GitHub stubbed.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_loop.core import graphs as core_graphs
from the_loop.ghapi import GhComment
from the_loop.graph import prspec
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.hooks.loops import inner_loop_state_dir
from the_loop.graph.state import STATE_FILENAME, WorkItemState

ID = "issue-15"
WI_REF = "github:octo/origin#15"
API_PR = "github:octo/api#12"
ORIGIN_PR = "github:octo/origin#2"

CHAIN = {
    "requirements.md": (
        "---\ntype: requirements\nstatus: approved\n---\n\n# R\n\n## Requirements\n\n"
        "### Requirement 1 — API\n\n#### Acceptance criteria (EARS)\n\n1. WHEN a THEN b.\n"
    ),
    "design.md": "---\ntype: design\nstatus: approved\n---\n\n# D\n\n## Security design\n\nx\n",
    "testing-plan.md": (
        "---\ntype: testing-plan\nstatus: approved\n---\n\n# T\n\n## Test matrix\n\n"
        "| # | Type | Applies? | Scope | Where |\n|---|---|---|---|---|\n"
        "| T1 | Unit | yes | x | y |\n"
    ),
    "tasks.md": "---\ntype: tasks\n---\n\n# Tasks\n\n- [x] 1. Build it\n",
}


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _init_repo(path: Path, slug: str, branch: str = "main") -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "remote", "add", "origin", f"https://github.com/{slug}.git")
    (path / "README").write_text("x\n")
    _git(path, "add", ".")
    _git(path, "commit", "-q", "-m", "init")
    _git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    if branch != "main":
        _git(path, "checkout", "-q", "-b", branch)
    return path


def _row(ref: str, **extra: Any) -> Dict[str, Any]:
    repo, _, number = ref.partition(":")[2].partition("#")
    return {"ref": ref, "repository": repo, "number": int(number), **extra}


@pytest.fixture(autouse=True)
def cli_config(tmp_path, monkeypatch):
    """One authorized user, and nothing from the machine running the tests."""
    path = tmp_path / "cli-config.yaml"
    path.write_text("routing:\n  authorizedUsers: [owner]\n", encoding="utf-8")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    monkeypatch.delenv("THE_LOOP_INSTANCE", raising=False)
    monkeypatch.delenv("THE_LOOP_WORK_ITEM", raising=False)
    return path


@pytest.fixture
def origin(tmp_path) -> Path:
    root = _init_repo(tmp_path / "origin", "octo/origin")
    spec = root / "docs" / "specs" / ID
    spec.mkdir(parents=True)
    for name, text in CHAIN.items():
        (spec / name).write_text(text, encoding="utf-8")
    return root


def _spec(origin: Path) -> Path:
    return origin / "docs" / "specs" / ID


def _outer_state(origin: Path, rows: List[Dict[str, Any]], current: str = "") -> None:
    data = {"workItem": WI_REF, "currentNode": current, "pullRequests": rows}
    (_spec(origin) / STATE_FILENAME).write_text(json.dumps(data), encoding="utf-8")


def _pr_checkout(tmp_path: Path, slug: str = "octo/api") -> Path:
    return _init_repo(tmp_path / "pr", slug, branch="feature")


def _write_pr_spec(
    checkout: Path, origin: Path, key: str, number: int, pr_ref: str
) -> None:
    target = checkout / "docs" / "specs" / key / f"pr-{number}"
    target.mkdir(parents=True)
    digest = prspec.chain_digest(_spec(origin))
    bodies = {
        "requirements.md": "## Requirements\n\n### The API part [wi:R1]\n\nDelivers [wi:R1.1].\n",
        "design.md": "## Design\n\nAs [wi:design#security-design].\n",
        "testing-plan.md": (
            "## Test matrix\n\n| # | Type | Applies? | Scope | Where |\n|---|---|---|---|---|\n"
            "| P1 | Unit | yes | proves [wi:TP-T1] | pytest |\n"
        ),
        "tasks.md": "## Tasks\n\n- [ ] 1. Build the API part [wi:task-1]\n",
    }
    for name, kind in prspec.PR_SPEC_FILES:
        (target / name).write_text(
            f'---\ntype: {kind}\nworkItem: "{WI_REF}"\npullRequest: "{pr_ref}"\n'
            f'sourceRevision: "abc1234"\nchainDigest: "{digest}"\n---\n\n# PR spec\n\n'
            f"## Context\n\nOne part of {WI_REF}.\n\n{bodies[name]}",
            encoding="utf-8",
        )


class FakeGitHub:
    def __init__(self, visibility=None, comments=None):
        self.visibility = visibility or {}
        self.comments = comments or {}

    def get_pull(self, owner, repo, number, host=""):
        return {"head": {"ref": "feature"}, "base": {"ref": "main"}}

    def repository(self, owner, repo, host=""):
        return {"visibility": self.visibility.get(f"{owner}/{repo}", "public")}

    def list_comments(self, owner, repo, number, is_pr, host=""):
        return list(self.comments.get((f"{owner}/{repo}", number), []))


def _record(origin: Path, checkout: Path, client: Any, **kw: Any) -> Dict[str, Any]:
    return core_graphs.pr_spec(
        str(origin), ID, 12, str(checkout), pr_repo="octo/api", client=client, **kw
    )


def test_a_cross_repository_pr_cannot_start_implementation_without_a_recorded_pr_spec(
    origin, tmp_path
):
    """
    Feature: PR-scoped specs
      Scenario: a cross-repository PR cannot start implementation without a recorded PR spec
        Given a work item delivered by a PR in its origin and a PR in octo/api
        And the octo/api PR's inner loop has started at `pr-spec`
        When the inner loop is advanced with no PR spec recorded
        Then it blocks at `pr-spec`, naming the command that records one
        When the PR spec is written in the PR's branch and recorded
        Then the inner loop moves on to `implementation`
    Requirement: docs/specs/issue-543/requirements.md R1.1, R4.1, R4.5
    """
    _outer_state(origin, [_row(ORIGIN_PR), _row(API_PR)])
    inner = build_runtime(origin, pr_number=12, pr_repo="octo/api")
    inner.start(ID, API_PR)
    blocked = inner.advance(ID, API_PR)
    assert (blocked.node, blocked.status) == ("pr-spec", "block")
    assert "the-loop graph pr-spec issue-15 --pr 12 --pr-repo octo/api" in " ".join(
        blocked.messages
    )

    checkout = _pr_checkout(tmp_path)
    _write_pr_spec(checkout, origin, "octo__origin__issue-15", 12, API_PR)
    result = _record(origin, checkout, FakeGitHub())
    assert result["recorded"], result["findings"]

    moved = inner.advance(ID, API_PR)
    assert moved.status == "pass"
    state_dir = inner_loop_state_dir(_spec(origin), 12, "octo/api")
    assert WorkItemState.load(state_dir, ID).current_node == "implementation"


def test_a_changed_chain_blocks_the_pr_at_reviewer_briefing_until_it_is_re_derived(
    origin, tmp_path
):
    """
    Feature: PR-scoped specs
      Scenario: a changed chain blocks the PR at reviewer-briefing until it is re-derived
        Given a recorded PR spec for the octo/api PR
        And the PR's inner loop is at `reviewer-briefing`
        When the work item's design changes
        Then `reviewer-briefing` blocks with "stale: chain changed since", naming design.md
        When an authorized person says on the PR that the PR spec still holds
        And the verb records that with --still-valid
        Then `reviewer-briefing` passes
    Requirement: docs/specs/issue-543/requirements.md R5.1, R5.2, R5.3
    """
    _outer_state(origin, [_row(ORIGIN_PR), _row(API_PR)])
    checkout = _pr_checkout(tmp_path)
    _write_pr_spec(checkout, origin, "octo__origin__issue-15", 12, API_PR)
    assert _record(origin, checkout, FakeGitHub())["recorded"]
    evidence = _spec(origin) / "evidence"
    evidence.mkdir()
    (evidence / "pull-requests.md").write_text("# PRs\n\n## Pull requests\n\n- #12\n")
    state_dir = inner_loop_state_dir(_spec(origin), 12, "octo/api")
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / STATE_FILENAME).write_text(
        json.dumps({"workItem": API_PR, "currentNode": "reviewer-briefing"})
    )
    inner = build_runtime(origin, pr_number=12, pr_repo="octo/api")

    with (_spec(origin) / "design.md").open("a", encoding="utf-8") as fh:
        fh.write("\nA new decision.\n")
    stale = inner.advance(ID, API_PR)
    assert (stale.node, stale.status) == ("reviewer-briefing", "block")
    assert "stale: chain changed since" in " ".join(stale.messages)
    assert "design.md" in " ".join(stale.messages)

    url = "https://github.com/octo/api/pull/12#issuecomment-9"
    # Written after the record it moves forward, as a real declaration is.
    said = (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat()
    still = GhComment(
        id="c", body="still holds", author="owner", created_at=said, url=url
    )
    client = FakeGitHub(comments={("octo/api", 12): [still]})
    assert _record(origin, checkout, client, still_valid=url)["recorded"]
    assert inner.advance(ID, API_PR).status == "pass"


def test_a_single_pr_work_item_walks_past_pr_spec_untouched(origin):
    """
    Feature: PR-scoped specs
      Scenario: a single-PR work item walks past pr-spec untouched
        Given a work item delivered by one PR in its origin repository
        And that PR's inner loop has started at `pr-spec`
        When the inner loop is advanced
        Then it moves to `implementation` with no PR spec written or recorded
    Requirement: docs/specs/issue-543/requirements.md R1.2; NFR single-repository unaffected
    """
    _outer_state(origin, [_row(ORIGIN_PR)])
    inner = build_runtime(origin, pr_number=2)
    inner.start(ID, ORIGIN_PR)
    assert inner.advance(ID, ORIGIN_PR).status == "pass"
    state_dir = inner_loop_state_dir(_spec(origin), 2)
    assert WorkItemState.load(state_dir, ID).current_node == "implementation"
    assert not list(_spec(origin).rglob(prspec.PR_SPEC_RECORD))


def test_under_never_mode_the_outer_implementation_holds_until_every_pr_has_a_record(
    origin, tmp_path
):
    """
    Feature: PR-scoped specs
      Scenario: under never mode the outer implementation holds until every PR has a record
        Given a work item delivered by a PR in its origin and a PR in octo/api
        And no inner loop was walked for either (PR sessions `never`)
        And every task is ticked
        When the outer `implementation` node is evaluated
        Then it blocks, naming both pull requests
        When the octo/api PR's spec is recorded
        Then it still blocks, naming only the origin PR
    Requirement: docs/specs/issue-543/requirements.md R1.4, R1.6
    """
    _outer_state(origin, [_row(ORIGIN_PR), _row(API_PR)], current="implementation")
    outer = build_runtime(origin)
    first = outer.advance(ID, WI_REF)
    text = " ".join(first.messages)
    assert (first.node, first.status) == ("implementation", "block")
    assert ORIGIN_PR in text and API_PR in text

    checkout = _pr_checkout(tmp_path)
    _write_pr_spec(checkout, origin, "octo__origin__issue-15", 12, API_PR)
    assert _record(origin, checkout, FakeGitHub())["recorded"]
    second = " ".join(outer.advance(ID, WI_REF).messages)
    assert ORIGIN_PR in second and API_PR not in second


def test_a_private_origin_will_not_publish_a_pr_spec_to_a_public_repository_without_an_authorized_grant(
    origin, tmp_path
):
    """
    Feature: PR-scoped specs
      Scenario: a private origin will not publish a PR spec to a public repository without an authorized grant
        Given the origin repository is private and octo/api is public
        When the octo/api PR's spec is recorded with no grant
        Then it is refused and no record is written
        When it is recorded with a grant by someone who is not authorized
        Then it is refused
        When an authorized person comments "allow-disclosure octo/api" on the work item
        And the verb is given that comment's URL
        Then the record is written, naming who granted it
    Requirement: docs/specs/issue-543/requirements.md Security AC1, AC2
    """
    _outer_state(origin, [_row(ORIGIN_PR), _row(API_PR)])
    checkout = _pr_checkout(tmp_path)
    _write_pr_spec(checkout, origin, "octo__origin__issue-15", 12, API_PR)
    visibility = {"octo/origin": "private", "octo/api": "public"}

    refused = _record(origin, checkout, FakeGitHub(visibility=visibility))
    assert not refused["recorded"]
    assert "disclosure refused" in refused["findings"][0]["text"]
    assert not list(_spec(origin).rglob(prspec.PR_SPEC_RECORD))

    url = "https://github.com/octo/origin/issues/15#issuecomment-3"

    def grant(author: str) -> FakeGitHub:
        body = "allow-disclosure octo/api"
        comment = GhComment(id="c", body=body, author=author, created_at="t", url=url)
        return FakeGitHub(
            visibility=visibility, comments={("octo/origin", 15): [comment]}
        )

    assert not _record(origin, checkout, grant("mallory"), disclosure_approval=url)[
        "recorded"
    ]
    granted = _record(origin, checkout, grant("owner"), disclosure_approval=url)
    assert granted["recorded"], granted["findings"]
    assert granted["record"]["disclosure"]["by"] == "@owner"
