"""Committing the knowledge graph back to ``main`` (issue-385).

``scripts/graphify-commit.sh`` is the one place the workflow touches the repository: it
commits ``graphify-out/`` when it changed and pushes it onto the branch tip, rebasing
past whatever landed while the graph was being built — the release workflow's ``bump:``
commit is the usual case. Each scenario below drives the real script against a bare
repository on disk; no network, no GitHub.

Gherkin docstrings per ``testing.gherkinDocstrings``; the requirement links point at
``docs/specs/issue-385/requirements.md``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "graphify-commit.sh"

pytestmark = pytest.mark.skipif(
    not SCRIPT.is_file(), reason="repository scripts not present (source distribution)"
)

_IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **_IDENTITY, "GIT_CONFIG_GLOBAL": "/dev/null"}
    return subprocess.run(
        ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True
    ).stdout.strip()


def _run_script(cwd: Path, *args: str, **extra_env: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        **_IDENTITY,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GRAPHIFY_PUSH_BACKOFF": "0",  # no sleeping between retries in tests
        # On a GitHub runner GITHUB_SHA names the run's commit; the script would put it
        # in the message instead of the clone's HEAD. Empty reads as unset to the script.
        "GITHUB_SHA": "",
        **extra_env,
    }
    return subprocess.run(
        [str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True
    )


@pytest.fixture
def remote_and_clone(tmp_path: Path):
    """A bare ``origin`` with one commit on ``main``, and a full clone of it."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    _git(tmp_path, "clone", "-q", str(origin), str(seed))
    (seed / "README.md").write_text("# seed\n", encoding="utf-8")
    (seed / "graphify-out").mkdir()
    (seed / "graphify-out" / "graph.json").write_text(
        '{"nodes": []}\n', encoding="utf-8"
    )
    _git(seed, "add", "-A")
    _git(seed, "commit", "-qm", "chore: seed")
    _git(seed, "push", "-q", "origin", "HEAD:main")
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", str(origin), str(clone))
    return origin, clone


def _remote_log(origin: Path) -> list[str]:
    return _git(origin, "log", "--format=%s", "main").splitlines()


def test_an_unchanged_graph_is_not_committed(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: The rebuild produced a byte-identical graph
        Given a clone whose graphify-out/ matches the branch tip
        When the commit script runs
        Then it exits 0 without creating a commit
        And the remote branch is untouched
    Requirement: docs/specs/issue-385/requirements.md R1.5
    """
    origin, clone = remote_and_clone
    result = _run_script(clone, "main")
    assert result.returncode == 0, result.stderr
    assert "nothing changed" in result.stdout
    assert _remote_log(origin) == ["chore: seed"]


def test_a_changed_graph_lands_as_one_chore_commit(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: The rebuild changed the graph
        Given a clone whose graphify-out/ differs from the branch tip
        And an unrelated modified file outside graphify-out/
        When the commit script runs
        Then exactly one commit is pushed to the remote branch
        And its message is a Conventional Commits chore naming the built commit
        And it carries only the files under graphify-out/
    Requirement: docs/specs/issue-385/requirements.md R1.5
    """
    origin, clone = remote_and_clone
    (clone / "graphify-out" / "graph.json").write_text(
        '{"nodes": [1]}\n', encoding="utf-8"
    )
    (clone / "graphify-out" / "GRAPH_REPORT.md").write_text(
        "# report\n", encoding="utf-8"
    )
    (clone / "README.md").write_text("# touched by the build\n", encoding="utf-8")
    built = _git(clone, "rev-parse", "HEAD")

    # An empty identity in the environment is "unset" to the script, which then commits
    # under the release workflow's bot identity — the case CI exercises.
    result = _run_script(
        clone,
        "main",
        GITHUB_SHA=built,
        GIT_AUTHOR_NAME="",
        GIT_AUTHOR_EMAIL="",
        GIT_COMMITTER_NAME="",
        GIT_COMMITTER_EMAIL="",
    )

    assert result.returncode == 0, result.stderr
    assert "pushed" in result.stdout
    log = _remote_log(origin)
    assert log[0] == f"chore(graphify): rebuild the knowledge graph for {built[:7]}"
    assert log[1:] == ["chore: seed"]
    files = _git(origin, "show", "--stat", "--format=", "main").splitlines()
    touched = {line.split("|")[0].strip() for line in files if "|" in line}
    assert touched == {"graphify-out/graph.json", "graphify-out/GRAPH_REPORT.md"}
    author = _git(origin, "log", "-1", "--format=%an <%ae>", "main")
    assert (
        author
        == "github-actions[bot] <41898282+github-actions[bot]@users.noreply.github.com>"
    )


def test_a_commit_that_landed_meanwhile_is_rebased_past(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: The release workflow pushed a bump commit while the graph was building
        Given a clone one commit behind the remote branch
        And a changed graphify-out/ in that clone
        When the commit script runs
        Then the push succeeds without --force
        And the remote branch carries the bump commit and the graph commit on top of it
        And the bump commit's file survives
    Requirement: docs/specs/issue-385/requirements.md R1.5
    """
    origin, clone = remote_and_clone
    other = clone.parent / "other"
    _git(clone.parent, "clone", "-q", str(origin), str(other))
    (other / "CHANGELOG.md").write_text("## 1.0.0\n", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-qm", "bump: version 0.9.0 → 1.0.0")
    _git(other, "push", "-q", "origin", "HEAD:main")

    (clone / "graphify-out" / "graph.json").write_text(
        '{"nodes": [2]}\n', encoding="utf-8"
    )
    built = _git(clone, "rev-parse", "HEAD")
    result = _run_script(clone, "main")

    assert result.returncode == 0, result.stderr
    assert _remote_log(origin) == [
        f"chore(graphify): rebuild the knowledge graph for {built[:7]}",
        "bump: version 0.9.0 → 1.0.0",
        "chore: seed",
    ]
    assert _git(origin, "show", "main:CHANGELOG.md") == "## 1.0.0"


def test_a_shallow_checkout_is_enough(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: The workflow's default depth-1 checkout
        Given a depth-1 clone of the remote branch with a changed graphify-out/
        And a commit that landed on the remote meanwhile
        When the commit script runs
        Then the push succeeds
    Requirement: docs/specs/issue-385/requirements.md R1.5
    """
    origin, clone = remote_and_clone
    shallow = clone.parent / "shallow"
    _git(clone.parent, "clone", "-q", "--depth", "1", f"file://{origin}", str(shallow))
    (clone / "README.md").write_text("# moved on\n", encoding="utf-8")
    _git(clone, "commit", "-qam", "docs: move on")
    _git(clone, "push", "-q", "origin", "HEAD:main")

    (shallow / "graphify-out" / "graph.json").write_text(
        '{"nodes": [3]}\n', encoding="utf-8"
    )
    built = _git(shallow, "rev-parse", "HEAD")
    result = _run_script(shallow, "main")

    assert result.returncode == 0, result.stderr
    assert _remote_log(origin)[:2] == [
        f"chore(graphify): rebuild the knowledge graph for {built[:7]}",
        "docs: move on",
    ]


def test_a_push_that_keeps_failing_fails_the_job(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: The remote refuses every push
        Given a remote whose pre-receive hook rejects updates
        And a changed graphify-out/ in the clone
        When the commit script runs
        Then it retries a bounded number of times and exits non-zero
        And the remote branch is untouched
    Requirement: docs/specs/issue-385/requirements.md R1.5 (fail closed)
    """
    origin, clone = remote_and_clone
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\necho 'rejected' >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    (clone / "graphify-out" / "graph.json").write_text(
        '{"nodes": [4]}\n', encoding="utf-8"
    )

    result = _run_script(clone, "main")

    assert result.returncode != 0
    assert "giving up" in result.stderr
    assert _remote_log(origin) == ["chore: seed"]


def test_a_rebase_conflict_is_reported_not_forced(remote_and_clone) -> None:
    """
    Feature: Commit the knowledge graph back to main
      Scenario: Somebody committed a different graphify-out/ to main meanwhile
        Given a clone with a changed graphify-out/graph.json
        And a remote commit that changed the same file differently
        When the commit script runs
        Then it aborts the rebase and exits non-zero
        And it never force-pushes over the remote commit
    Requirement: docs/specs/issue-385/requirements.md R1.5 (fail closed)
    """
    origin, clone = remote_and_clone
    other = clone.parent / "other"
    _git(clone.parent, "clone", "-q", str(origin), str(other))
    (other / "graphify-out" / "graph.json").write_text(
        '{"nodes": ["theirs"]}\n', encoding="utf-8"
    )
    _git(other, "commit", "-qam", "chore(graphify): hand-edited")
    _git(other, "push", "-q", "origin", "HEAD:main")

    (clone / "graphify-out" / "graph.json").write_text(
        '{"nodes": ["ours"]}\n', encoding="utf-8"
    )
    result = _run_script(clone, "main")

    assert result.returncode != 0
    assert "conflict" in result.stderr
    assert _remote_log(origin)[0] == "chore(graphify): hand-edited"
    assert (
        _git(origin, "show", "main:graphify-out/graph.json") == '{"nodes": ["theirs"]}'
    )
