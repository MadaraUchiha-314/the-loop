"""The ticket's symptom, end to end through the shipped seams (issue-311).

    the-loop graph … in a checkout on GitHub Enterprise
        → build_runtime resolves the host (CLI config, gh, the remote)
        → Runtime.work_item derives github:<host>/owner/repo#n
        → the notify hook's link, the ask's link and the portable record's url
          are all derived from THAT ref — and so is every gh argv

Every scenario walks a real ``build_runtime`` over a real harness config and a
real CLI config file (``$THE_LOOP_CLI_CONFIG``); no network, no ``gh``. The
github.com scenario is the regression guard: a config that says nothing must
mint the exact strings it always did.
"""

from __future__ import annotations

import pytest

from the_loop.comments import comment_argv
from the_loop.graph.bootstrap import build_runtime
from the_loop.graph.hooks.sideeffects import _work_item_url
from the_loop.sessions import WorkItemRef

WORK_ITEM = "issue-311"
GHE = "ghe.corp.example"


def _repo(tmp_path):
    (tmp_path / "docs" / "specs" / WORK_ITEM).mkdir(parents=True)
    (tmp_path / ".the-loop").mkdir()
    (tmp_path / ".the-loop" / "harness-config.yaml").write_text(
        "workflow:\n  specDir: docs/specs\n"
        "ticketing:\n  github:\n    owner: octo\n    repo: repo\n",
        encoding="utf-8",
    )
    return tmp_path


def _cli_config(tmp_path, monkeypatch, body: str):
    path = tmp_path / "cli-config.yaml"
    path.write_text('version: "0.7.0"\n' + body, encoding="utf-8")
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(path))
    monkeypatch.delenv("GH_HOST", raising=False)
    return path


@pytest.fixture(autouse=True)
def _no_remote(monkeypatch):
    """The temp checkout has no origin; tier 4 is exercised explicitly below."""
    monkeypatch.setattr("the_loop.ghhost._origin_remote", lambda root: "")


def test_a_configured_host_reaches_the_link_and_the_argv(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: the CLI config names a GitHub Enterprise host
        Given a checkout whose harness config declares ticketing octo/repo
        And a CLI config declaring integrations.github.host: ghe.corp.example
        When the graph derives the work item's ref
        Then the ref is github:ghe.corp.example/octo/repo#311
        And the URL the notify hook publishes is https://ghe.corp.example/octo/repo/issues/311
        And a comment on it is posted with gh api --hostname ghe.corp.example

    Requirement: docs/specs/issue-311/bugfix.md R1.1, R2.1, R4.1
    """
    repo = _repo(tmp_path)
    _cli_config(tmp_path, monkeypatch, f"integrations:\n  github:\n    host: {GHE}\n")

    runtime = build_runtime(repo)
    item = runtime.work_item(WORK_ITEM)

    assert runtime.config["githubHost"] == GHE
    assert item.ref == f"github:{GHE}/octo/repo#311"
    assert _work_item_url(item.ref) == f"https://{GHE}/octo/repo/issues/311"
    argv = comment_argv(WorkItemRef.parse(item.ref), "decision needed")
    assert argv[:3] == ["api", "--hostname", GHE]


def test_gh_host_answers_when_the_config_says_nothing(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: the operator relies on gh's own GH_HOST
        Given a CLI config with no integrations.github.host
        And GH_HOST=ghe.corp.example in the environment
        When the graph derives the work item's ref
        Then the ref and its URL name ghe.corp.example

    Requirement: docs/specs/issue-311/bugfix.md R1.1 (tier 3)
    """
    repo = _repo(tmp_path)
    _cli_config(tmp_path, monkeypatch, "integrations:\n  github:\n    transport: cli\n")
    monkeypatch.setenv("GH_HOST", GHE)

    item = build_runtime(repo).work_item(WORK_ITEM)
    assert item.ref == f"github:{GHE}/octo/repo#311"


def test_the_checkouts_remote_answers_in_session(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: nothing is configured and the checkout's origin is on GHE
        Given a CLI config with no host and no GH_HOST
        And the checkout's origin remote is git@ghe.corp.example:octo/repo.git
        When the graph derives the work item's ref
        Then the ref names ghe.corp.example — gh's own answer for that checkout

    Requirement: docs/specs/issue-311/bugfix.md R1.1 (tier 4), A4
    """
    repo = _repo(tmp_path)
    _cli_config(tmp_path, monkeypatch, "integrations:\n  github:\n    transport: cli\n")
    seen = []

    def remote(root):
        seen.append(root)
        return f"git@{GHE}:octo/repo.git"

    monkeypatch.setattr("the_loop.ghhost._origin_remote", remote)

    item = build_runtime(repo).work_item(WORK_ITEM)
    assert item.ref == f"github:{GHE}/octo/repo#311"
    assert seen == [repo]  # read for THIS checkout, once


def test_a_pull_request_loop_carries_the_host_too(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: an inner loop's pull-request ref is minted with the host
        Given a CLI config declaring integrations.github.host
        When a pdlc-pr-loop runtime is built for pull request 12
        Then its prRef is github:ghe.corp.example/octo/repo#12

    Requirement: docs/specs/issue-311/bugfix.md R2.2
    """
    repo = _repo(tmp_path)
    _cli_config(tmp_path, monkeypatch, f"integrations:\n  github:\n    host: {GHE}\n")
    runtime = build_runtime(repo, pr_number=12)
    assert runtime.config["prRef"] == f"github:{GHE}/octo/repo#12"


def test_github_com_mints_exactly_what_it_always_did(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: a github.com deployment sees no change
        Given a CLI config that names no host
        And no GH_HOST and no enterprise remote
        When the graph derives the work item's ref
        Then the ref is github:octo/repo#311, the URL is on github.com
        And the comment argv carries no --hostname

    Requirement: docs/specs/issue-311/bugfix.md A5
    """
    repo = _repo(tmp_path)
    _cli_config(tmp_path, monkeypatch, "integrations:\n  github:\n    transport: cli\n")

    runtime = build_runtime(repo)
    item = runtime.work_item(WORK_ITEM)
    assert runtime.config["githubHost"] == "github.com"
    assert item.ref == "github:octo/repo#311"
    assert _work_item_url(item.ref) == "https://github.com/octo/repo/issues/311"
    assert "--hostname" not in comment_argv(WorkItemRef.parse(item.ref), "hi")


def test_a_bad_configured_host_never_reaches_a_ref(tmp_path, monkeypatch):
    """
    Feature: links and gh calls name the GitHub the work item is on
      Scenario: the configured host is not a host
        Given integrations.github.host: "https://ghe.corp.example/api"
        When the graph derives the work item's ref
        Then the value is skipped and the ref falls back to github.com

    Requirement: docs/specs/issue-311/bugfix.md R1.2, A1
    """
    repo = _repo(tmp_path)
    _cli_config(
        tmp_path,
        monkeypatch,
        'integrations:\n  github:\n    host: "https://ghe.corp.example/api"\n',
    )
    item = build_runtime(repo).work_item(WORK_ITEM)
    assert item.ref == "github:octo/repo#311"
