"""Unit + integration tests for the clone-and-worktree workspace (issue-76).

Spec: docs/specs/issue-76/design.md (decision-034).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from the_loop.workspace import (
    RepoTarget,
    Workspace,
    WorkspaceError,
    repo_target_from_payload,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


# -- helpers ------------------------------------------------------------------


def _git(args, cwd):
    env_args = [
        "-c",
        "user.email=test@the-loop.dev",
        "-c",
        "user.name=the-loop test",
        "-c",
        "init.defaultBranch=main",
        "-c",
        "commit.gpgsign=false",
    ]
    subprocess.run(
        ["git"] + env_args + args, cwd=str(cwd), check=True, capture_output=True
    )


def make_origin(tmp_path: Path, name="repo") -> Path:
    """A bare origin repo with one commit on ``main`` — a stand-in for GitHub."""
    seed = tmp_path / f"{name}-seed"
    seed.mkdir()
    _git(["init"], seed)
    (seed / "README.md").write_text("# seed\n")
    _git(["add", "-A"], seed)
    _git(["commit", "-m", "initial"], seed)
    bare = tmp_path / f"{name}.git"
    _git(["clone", "--bare", str(seed), str(bare)], tmp_path)
    return bare


def target_for(
    bare: Path, *, host="github.com", owner="octo", repo="repo"
) -> RepoTarget:
    return RepoTarget(host=host, owner=owner, repo=repo, clone_url=str(bare))


# -- repo_target_from_payload -------------------------------------------------


def test_target_from_full_webhook_payload_uses_clone_url_and_html_host():
    payload = {
        "repository": {
            "full_name": "octo/hello",
            "html_url": "https://github.example.com/octo/hello",
            "clone_url": "https://github.example.com/octo/hello.git",
            "ssh_url": "git@github.example.com:octo/hello.git",
        }
    }
    target = repo_target_from_payload(payload)
    assert target.host == "github.example.com"
    assert target.owner == "octo" and target.repo == "hello"
    assert target.clone_url == "https://github.example.com/octo/hello.git"
    assert target.rel_path == Path("github.example.com/octo/hello")


def test_target_ssh_protocol_prefers_ssh_url():
    payload = {
        "repository": {
            "full_name": "octo/hello",
            "html_url": "https://github.com/octo/hello",
            "ssh_url": "git@github.com:octo/hello.git",
        }
    }
    target = repo_target_from_payload(payload, protocol="ssh")
    assert target.clone_url == "git@github.com:octo/hello.git"


def test_target_from_lean_poller_payload_reconstructs_url_and_default_host():
    # The poller synthesises payloads carrying only repository.full_name.
    payload = {"repository": {"full_name": "octo/hello"}}
    target = repo_target_from_payload(payload, default_host="ghe.corp")
    assert target.host == "ghe.corp"
    assert target.clone_url == "https://ghe.corp/octo/hello.git"
    ssh = repo_target_from_payload(payload, protocol="ssh", default_host="ghe.corp")
    assert ssh.clone_url == "git@ghe.corp:octo/hello.git"


def test_target_none_when_no_repository():
    assert repo_target_from_payload({}) is None
    assert repo_target_from_payload({"repository": {"full_name": "no-slash"}}) is None


@pytest.mark.parametrize(
    "full_name",
    ["../evil/repo", "octo/..", "octo/../../etc", ".ssh/repo"],
)
def test_target_rejects_path_traversal_components(full_name):
    with pytest.raises(WorkspaceError):
        repo_target_from_payload({"repository": {"full_name": full_name}})


# -- layout -------------------------------------------------------------------


def test_layout_follows_host_owner_repo(tmp_path):
    ws = Workspace(tmp_path / "root")
    target = target_for(tmp_path / "x.git", host="github.com", owner="octo", repo="r")
    assert ws.repo_dir(target) == tmp_path / "root" / "github.com" / "octo" / "r"
    assert ws.worktree_dir(target, "s-1") == (
        tmp_path / "root" / ".worktrees" / "github.com" / "octo" / "r" / "s-1"
    )


# -- clone / worktree lifecycle ----------------------------------------------


def test_ensure_clone_creates_layout_then_reuses(tmp_path):
    bare = make_origin(tmp_path)
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    repo_dir = ws.ensure_clone(target)
    assert repo_dir == ws.repo_dir(target)
    assert (repo_dir / ".git").is_dir()
    assert (repo_dir / "README.md").is_file()
    # A second call reuses (fetches) the existing clone, same dir.
    assert ws.ensure_clone(target) == repo_dir


def test_ensure_worktree_detached_at_default_branch(tmp_path):
    bare = make_origin(tmp_path)
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    wt = ws.ensure_worktree(target, "github-octo-repo-15")
    assert wt == ws.worktree_dir(target, "github-octo-repo-15")
    assert (wt / "README.md").is_file()
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(wt),
        capture_output=True,
        text=True,
    )
    assert head.stdout.strip() == "HEAD"  # detached, so the harness owns branching


def test_ensure_worktree_on_pr_branch_checks_it_out(tmp_path):
    bare = make_origin(tmp_path)
    # Push a feature branch to the origin, as a PR head would be.
    work = tmp_path / "pusher"
    _git(["clone", str(bare), str(work)], tmp_path)
    _git(["checkout", "-b", "feature/x"], work)
    (work / "f.txt").write_text("feature\n")
    _git(["add", "-A"], work)
    _git(["commit", "-m", "feature"], work)
    _git(["push", "origin", "feature/x"], work)

    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    wt = ws.ensure_worktree(target, "github-octo-repo-7", branch="feature/x")
    assert (wt / "f.txt").is_file()
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=str(wt),
        capture_output=True,
        text=True,
    )
    assert head.stdout.strip() == "feature/x"


def test_ensure_worktree_unknown_branch_falls_back_to_detached(tmp_path):
    bare = make_origin(tmp_path)
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    # branch origin doesn't have — must not raise; falls back to default branch.
    wt = ws.ensure_worktree(target, "s-1", branch="nope/missing")
    assert (wt / "README.md").is_file()


def test_ensure_worktree_idempotent(tmp_path):
    bare = make_origin(tmp_path)
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    first = ws.ensure_worktree(target, "s-1")
    again = ws.ensure_worktree(target, "s-1")
    assert first == again and (again / "README.md").is_file()


def test_remove_worktree_deletes_and_reports(tmp_path):
    bare = make_origin(tmp_path)
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    wt = ws.ensure_worktree(target, "s-1")
    assert wt.exists()
    assert ws.remove_worktree(target, "s-1") is True
    assert not wt.exists()
    # The primary clone survives cleanup; a second removal is a no-op.
    assert (ws.repo_dir(target) / ".git").is_dir()
    assert ws.remove_worktree(target, "s-1") is False


def test_ensure_clone_raises_on_bad_url(tmp_path):
    ws = Workspace(tmp_path / "root")
    target = RepoTarget(
        host="github.com",
        owner="octo",
        repo="nope",
        clone_url=str(tmp_path / "does-not-exist.git"),
    )
    with pytest.raises(WorkspaceError):
        ws.ensure_clone(target)


def test_is_available_reflects_git_binary(tmp_path):
    assert Workspace(tmp_path).is_available() is True
    assert Workspace(tmp_path, git_binary="definitely-not-git").is_available() is False


# -- config parsing -----------------------------------------------------------


def test_workspace_config_defaults_disabled():
    from the_loop.webhook.dispatcher import RoutingConfig

    ws = RoutingConfig.from_mapping({}).workspace
    assert ws.root == "" and ws.enabled is False
    assert ws.clone_protocol == "https" and ws.default_host == "github.com"
    assert ws.keep_worktree_on_close is False and ws.git_binary == "git"


def test_workspace_config_parses_overrides():
    from the_loop.webhook.dispatcher import RoutingConfig

    ws = RoutingConfig.from_mapping(
        {
            "workspace": {
                "root": "~/loop-workspace",
                "cloneProtocol": "ssh",
                "defaultHost": "ghe.corp",
                "keepWorktreeOnClose": True,
                "gitBinary": "/usr/bin/git",
            }
        }
    ).workspace
    assert ws.enabled is True and ws.root == "~/loop-workspace"
    assert ws.clone_protocol == "ssh" and ws.default_host == "ghe.corp"
    assert ws.keep_worktree_on_close is True and ws.git_binary == "/usr/bin/git"


# -- dispatcher integration (clone + worktree wired into spawn/close) ----------

import time  # noqa: E402

from the_loop.harness import DispatchResult  # noqa: E402
from the_loop.sessions import Session, SessionRegistry, WorkItemRef  # noqa: E402
from the_loop.webhook.dispatcher import (  # noqa: E402
    Dispatcher,
    RoutingConfig,
    WorkspaceConfig,
)
from the_loop.webhook.router import RoutedEvent, extract_work_items  # noqa: E402


class _RecordingAdapter:
    name = "claude"

    def __init__(self, spawn_id="spawned-1"):
        self.spawn_id = spawn_id
        self.spawns = []

    def is_available(self):
        return True

    def resume(self, session, prompt, timeout=None):
        return DispatchResult(ok=True, session_id=session.harness_session_id)

    def spawn(self, work_item, prompt, cwd, timeout=None):
        self.spawns.append((work_item.ref, cwd))
        return DispatchResult(ok=True, session_id=self.spawn_id)


def _wait(pred, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(0.01)
    return pred()


def _dispatcher(tmp_path, bare, adapter, **ws_over):
    registry = SessionRegistry(tmp_path / "sessions")
    config = RoutingConfig(
        spawn_on_unmatched="always",
        workspace=WorkspaceConfig(root=str(tmp_path / "root"), **ws_over),
    )
    dispatcher = Dispatcher(
        registry=registry, adapters={"claude": adapter}, config=config
    )
    return registry, dispatcher


def _issue_event(bare, number=15, delivery="d-1"):
    payload = {
        "action": "opened",
        "repository": {
            "full_name": "octo/repo",
            "html_url": "https://github.com/octo/repo",
            "clone_url": str(bare),
        },
        "issue": {"number": number},
        "sender": {"login": "octo"},
    }
    return RoutedEvent(
        event="issues",
        action="opened",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
    )


def _pr_close_event(bare, number=16, branch="claude/github-issue-15-x", delivery="c-1"):
    payload = {
        "action": "closed",
        "repository": {
            "full_name": "octo/repo",
            "html_url": "https://github.com/octo/repo",
            "clone_url": str(bare),
        },
        "pull_request": {
            "number": number,
            "head": {"ref": branch},
            "body": "Closes #15",
            "merged": True,
        },
    }
    return RoutedEvent(
        event="pull_request",
        action="closed",
        delivery_id=delivery,
        work_items=extract_work_items("pull_request", payload),
        payload=payload,
    )


def test_dispatcher_spawns_into_a_worktree_cwd(tmp_path):
    bare = make_origin(tmp_path)
    adapter = _RecordingAdapter()
    registry, dispatcher = _dispatcher(tmp_path, bare, adapter)
    dispatcher.handle(_issue_event(bare))
    assert _wait(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
    _, cwd = adapter.spawns[0]
    item = WorkItemRef.parse("github:octo/repo#15")
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    assert Path(cwd) == ws.worktree_dir(target, item.slug)
    assert (Path(cwd) / "README.md").is_file()  # the worktree is a real checkout
    # The session records the worktree as its cwd, and the primary clone exists.
    session = registry.find_by_work_item(item)
    assert session is not None and session.cwd == cwd
    assert (ws.repo_dir(target) / ".git").is_dir()


def test_dispatcher_pr_close_removes_worktree(tmp_path):
    bare = make_origin(tmp_path)
    adapter = _RecordingAdapter()
    registry, dispatcher = _dispatcher(tmp_path, bare, adapter)
    item = WorkItemRef.parse("github:octo/repo#15")
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    # Pre-create a session + its worktree, as a prior spawn would have.
    worktree = ws.ensure_worktree(target, item.slug)
    registry.register(
        Session(
            work_item=item,
            harness="claude",
            harness_session_id="s-1",
            cwd=str(worktree),
        )
    )
    assert worktree.exists()
    dispatcher.handle(_pr_close_event(bare))
    dispatcher.stop()
    assert registry.find_by_work_item(item) is None  # auto-closed
    assert not worktree.exists()  # ...and its worktree cleaned up
    assert (ws.repo_dir(target) / ".git").is_dir()  # primary clone kept


def test_dispatcher_pr_close_keeps_worktree_when_configured(tmp_path):
    bare = make_origin(tmp_path)
    adapter = _RecordingAdapter()
    registry, dispatcher = _dispatcher(
        tmp_path, bare, adapter, keep_worktree_on_close=True
    )
    item = WorkItemRef.parse("github:octo/repo#15")
    ws = Workspace(tmp_path / "root")
    target = target_for(bare)
    worktree = ws.ensure_worktree(target, item.slug)
    registry.register(
        Session(
            work_item=item,
            harness="claude",
            harness_session_id="s-1",
            cwd=str(worktree),
        )
    )
    dispatcher.handle(_pr_close_event(bare))
    dispatcher.stop()
    assert worktree.exists()  # kept for post-mortem when configured


def test_dispatcher_without_workspace_uses_spawn_workdir(tmp_path):
    # Legacy behaviour preserved: no workspace.root => static spawnWorkdir.
    adapter = _RecordingAdapter()
    registry = SessionRegistry(tmp_path / "sessions")
    config = RoutingConfig(spawn_on_unmatched="always", spawn_workdir=str(tmp_path))
    dispatcher = Dispatcher(
        registry=registry, adapters={"claude": adapter}, config=config
    )
    assert dispatcher.workspace is None
    dispatcher.handle(_issue_event(tmp_path / "unused.git"))
    assert _wait(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()
    _, cwd = adapter.spawns[0]
    assert cwd == str(tmp_path)
