"""Integration: a completed work item is checked after normal cleanup (issue-452).

The issue's reproduction, in-process. A real :class:`Dispatcher` over a real
:class:`the_loop.workspace.Workspace` — a git worktree under ``tmp_path``,
``keepCheckoutOnClose: false`` — holding a work item whose session recorded a
completed graph. The ticket closes as an authorized user, the close path
removes the worktree and the cleanup deletes the session record: nothing of the
checkout is left. Then the real ``the-loop check`` command runs from an
unrelated directory, exactly as the issue ran it, and again after the daemon is
rebuilt over the same state directory.

Feature: Archived status after normal checkout cleanup
Requirement: docs/specs/issue-452/bugfix.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.commands.graph_cmd import CheckCommand, GraphCommand
from the_loop.control import ControlConfig, ControlStore
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig, WorkspaceConfig
from the_loop.webhook.router import RoutedEvent
from the_loop.workspace import RepoTarget, Workspace

REF = "github:octo/repo#3"
ITEM = "issue-3"
SELECTED = ["implementation", "verification"]


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path: Path) -> Path:
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "README.md").write_text("hello\n")
    _git(["add", "."], repo)
    _git(["commit", "-qm", "first"], repo)
    return repo


@pytest.fixture
def state_root(tmp_path, monkeypatch) -> Path:
    """The operator's state root, named by the CLI config `check` reads."""
    root = tmp_path / "state"
    config = tmp_path / "cli-config.yaml"
    config.write_text(f'version: "0.12.0"\nstate:\n  root: {root}\n')
    monkeypatch.setenv("THE_LOOP_CLI_CONFIG", str(config))
    return root


def _daemon(tmp_path: Path, state_root: Path, workspace: Workspace):
    registry = SessionRegistry(state_root / "local")
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            dispatch_timeout_seconds=30,
            spawn_workdir=str(tmp_path),
            portable_dir=str(state_root / "portable"),
            authorized_users=["octocat"],
            control=ControlConfig(require_start_command=False),
            workspace=WorkspaceConfig(
                root=str(workspace.root), keep_checkout_on_close=False
            ),
        ),
        tmux_runner=FakeTmux(),
        workspace=workspace,
    )
    return registry, dispatcher


def _completed_checkout(workspace: Workspace, origin: Path) -> Path:
    """A worktree whose session walked implementation → verification → complete."""
    item = WorkItemRef.parse(REF)
    target = RepoTarget(
        host="github.com", owner="octo", repo="repo", clone_url=str(origin)
    )
    checkout = workspace.prepare(target, item.slug)
    # The coupling reads only a checkout of the work item's own repository.
    _git(["remote", "set-url", "origin", "https://github.com/octo/repo.git"], checkout)
    spec = checkout / "docs" / "specs" / ITEM
    (spec / "evidence").mkdir(parents=True)
    (spec / "evidence" / "verification.md").write_text("# Verification\n")
    skipped = [
        "brainstorming",
        "requirements-definition",
        "requirements-approval",
        "design",
        "test-planning",
        "design-approval",
        "tasks-breakdown",
    ]
    state = {
        "workItem": ITEM,
        "currentNode": "complete",
        "phase": "complete",
        "harness": "codex",
        "nodes": {
            "phase-selection": {"outcome": "selected", "attempts": 1},
            **{n: {"outcome": "pass", "attempts": 1} for n in SELECTED},
            "complete": {
                "outcome": "pass",
                "attempts": 1,
                "exitedAt": "2026-10-02T22:29:41+00:00",
            },
        },
        "skips": {n: {"via": "phase-selection", "by": "octocat"} for n in skipped},
        "pullRequests": [{"ref": "github:octo/repo#4", "state": "merged"}],
    }
    (spec / "work-item-state.json").write_text(json.dumps(state))
    return checkout


def _closed() -> RoutedEvent:
    item = WorkItemRef.parse(REF)
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id="close-3",
        work_items=[item],
        payload={
            "action": "closed",
            "repository": {"full_name": "octo/repo"},
            "issue": {"number": 3, "state_reason": "completed"},
            "sender": {"login": "octocat"},
        },
    )


def _check(fmt: str = "json", fail_on: str = "block") -> int:
    return CheckCommand().run(
        argparse.Namespace(
            repo="",
            spec_dir="",
            work_item=REF,
            format=fmt,
            all=False,
            recompute=False,
            fail_on=fail_on,
        )
    )


@pytest.fixture
def cleaned_up(tmp_path, origin, state_root, monkeypatch):
    """The issue's steps 1–2: complete, close, and let normal cleanup run."""
    workspace = Workspace(tmp_path / "workspace", strategy="worktree")
    registry, dispatcher = _daemon(tmp_path, state_root, workspace)
    checkout = _completed_checkout(workspace, origin)
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="codex",
            harness_session_id="sess-3",
            cwd=str(checkout),
            tmux_target="loop-github-octo-repo-3",
        )
    )

    dispatcher.handle(_closed())
    dispatcher.stop()

    assert not checkout.exists(), "normal cleanup removed the checkout"
    assert registry.find_by_work_item(REF, include_closed=True) is None
    devbox = tmp_path / "devbox"
    devbox.mkdir()
    monkeypatch.chdir(devbox)
    return workspace


def test_a_completed_work_item_is_checked_after_normal_cleanup(cleaned_up, capsys):
    """
    Feature: Archived status after normal checkout cleanup
      Scenario: a completed work item is checked after normal cleanup
        Given a work item whose session recorded a completed graph in a worktree
        And keepCheckoutOnClose is false
        When an authorized user closes its ticket and normal cleanup runs
        And `the-loop check <ref> --format json --fail-on block` runs from an
            unrelated deployment directory
        Then the report is the archived completion with its frozen selections
             and its delivery, lists no node findings, and the command exits 0

    Requirement: docs/specs/issue-452/bugfix.md R1.1, R1.2, R2.1, R2.5
    """
    code = _check()

    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["currentNode"] == "complete"
    assert report["currentNode"] != "phase-selection"
    assert (report["ok"], report["stateFound"], report["nodes"]) == (True, False, [])
    archived = report["archived"]
    assert (archived["outcome"], archived["detail"]) == ("completed", "recorded")
    terminal = archived["terminal"]
    assert terminal["completed"] is True
    assert terminal["completedAt"] == "2026-10-02T22:29:41+00:00"
    assert "implementation" not in terminal["selections"]["skipped"]
    assert "design" in terminal["selections"]["skipped"]
    assert terminal["selections"]["harness"] == "codex"
    assert terminal["pullRequests"] == [
        {
            "ref": "github:octo/repo#4",
            "url": "https://github.com/octo/repo/issues/4",
            "state": "merged",
        }
    ]
    assert terminal["evidence"] == ["verification.md"]


def test_the_table_says_archived_and_never_unmet(cleaned_up, capsys):
    code = _check(fmt="table", fail_on="unmet")

    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0] == f"{ITEM}: ARCHIVED — completed (at complete)"
    assert "UNMET" not in out and "BLOCK" not in out
    assert "terminal record this machine kept" in out
    assert "pull request: github:octo/repo#4 (merged)" in out
    assert "evidence: docs/specs/issue-3/evidence/ — verification.md" in out


def test_graph_status_renders_the_same_archive(cleaned_up, capsys):
    code = GraphCommand().run(
        argparse.Namespace(
            repo="", spec_dir="", action="status", work_item=REF, pr=None, pr_repo=""
        )
    )

    out = capsys.readouterr().out
    assert code == 0
    assert out.splitlines()[0] == f"{ITEM}: ARCHIVED — completed (at complete)"


def test_the_daemon_restarts_between_cleanup_and_check(
    cleaned_up, tmp_path, state_root, capsys
):
    """
    Feature: Archived status after normal checkout cleanup
      Scenario: the daemon restarts between cleanup and check
        Given a completed work item whose checkout normal cleanup removed
        When the daemon is rebuilt over the same state directory
        Then the archived record is unchanged and `check` still reports it,
             without relaunching the item

    Requirement: docs/specs/issue-452/bugfix.md R2.6
    """
    registry, dispatcher = _daemon(tmp_path, state_root, cleaned_up)
    dispatcher.stop()

    ended = ControlStore(state_root / "portable").ended(REF)
    assert ended is not None and ended["outcome"] == "completed"
    assert registry.list_sessions() == []
    assert isinstance(dispatcher.tmux, FakeTmux) and dispatcher.tmux.spawns == []

    code = _check()

    assert code == 0
    assert json.loads(capsys.readouterr().out)["archived"]["outcome"] == "completed"
