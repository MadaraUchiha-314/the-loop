"""Clone-and-worktree workspace for webhook/poll-spawned sessions (issue-76).

The CLI daemon runs independent of any one repo, but the harness it spawns
needs a checkout of the repo an event concerns. This module owns that checkout,
in one of two configurable **strategies** (``routing.workspace.strategy``,
decision-034):

* ``worktree`` (default) — one **clone per repo** under
  ``<root>/<host>/<owner>/<repo>`` (kept fresh with ``git fetch``, never worked
  in directly), plus one **git worktree per work item** under
  ``<root>/.worktrees/<host>/<owner>/<repo>/<slug>``. N concurrent work items on
  one repo share objects instead of paying for N full clones; the checkout tree
  ``<host>/<owner>/<repo>`` stays a clean mirror of the remote.
* ``clone`` — one **folder per work item** under ``<root>/.work-items/<slug>/``,
  into which each repo the work item touches is cloned at
  ``<root>/.work-items/<slug>/<host>/<owner>/<repo>``. No shared clone, no
  cross-repo worktree bookkeeping: a work item that spans several repos is one
  self-contained directory, and cleanup is a single ``rmtree`` of that folder.
  Costs a full clone per work item — the trade the operator opts into.

Both strategies key runtime state off the work-item slug and clean it up when
the work item's PR is merged/closed.

Git-only and provider-neutral: it shells out to ``git`` (the one native dep,
verified by ``is_available``) and derives the clone URL/host from the webhook
payload, falling back to a configured default host so the poller's leaner
``full_name``-only payloads work too. Auth is the operator's own git
credentials (e.g. ``gh auth setup-git`` for GitHub) — the workspace never
handles secrets.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("the-loop.workspace")

__all__ = [
    "RepoTarget",
    "Workspace",
    "WorkspaceError",
    "repo_target_from_payload",
]

# A path component we are willing to derive from remote-controlled data
# (owner/repo/host). Anything with a slash, ``..`` or leading dot is rejected so
# a hostile payload can never escape the workspace root via the layout.
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class WorkspaceError(Exception):
    """A clone/worktree git operation failed (spawn should fail + retry)."""


def _safe_component(value: str, kind: str) -> str:
    """Validate one host/owner/repo path segment (path-traversal guard)."""
    value = (value or "").strip()
    if value.endswith(".git"):
        value = value[: -len(".git")]
    if not _SAFE_COMPONENT_RE.match(value) or value in {".", ".."}:
        raise WorkspaceError(f"unsafe {kind} path component {value!r}")
    return value


def _host_from_url(url: str, default_host: str) -> str:
    """Pull the host out of a repo ``html_url``/``clone_url``, else the default."""
    match = re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?([^/:]+)", url or "")
    return match.group(1) if match else default_host


@dataclass(frozen=True)
class RepoTarget:
    """The repo an event concerns, resolved to a filesystem layout + clone URL."""

    host: str
    owner: str
    repo: str
    clone_url: str

    @property
    def rel_path(self) -> Path:
        return Path(self.host) / self.owner / self.repo


def repo_target_from_payload(
    payload: dict,
    *,
    protocol: str = "https",
    default_host: str = "github.com",
) -> Optional[RepoTarget]:
    """Resolve a :class:`RepoTarget` from a (webhook or synthesised) payload.

    Uses the rich fields a real webhook carries (``clone_url``/``ssh_url``/
    ``html_url``) when present, and otherwise reconstructs them from
    ``full_name`` + ``default_host`` so the poller's ``full_name``-only payloads
    still resolve. Returns ``None`` when the payload names no repository.
    """
    repo = (payload or {}).get("repository") or {}
    full_name = repo.get("full_name") or ""
    owner, sep, name = full_name.partition("/")
    if not sep or not owner or not name:
        return None
    host = _safe_component(
        _host_from_url(repo.get("html_url") or "", default_host), "host"
    )
    owner = _safe_component(owner, "owner")
    name = _safe_component(name, "repo")
    if protocol == "ssh":
        clone_url = repo.get("ssh_url") or f"git@{host}:{owner}/{name}.git"
    else:
        clone_url = repo.get("clone_url") or f"https://{host}/{owner}/{name}.git"
    return RepoTarget(host=host, owner=owner, repo=name, clone_url=clone_url)


class Workspace:
    """Provision per-work-item checkouts under ``root`` (worktree or clone)."""

    def __init__(self, root, *, strategy: str = "worktree", git_binary: str = "git"):
        self.root = Path(root).expanduser()
        self.strategy = strategy if strategy in ("worktree", "clone") else "worktree"
        self.git = git_binary

    # -- layout -----------------------------------------------------------------

    def repo_dir(self, target: RepoTarget) -> Path:
        """The primary shared clone (worktree strategy): ``<root>/<host>/<owner>/<repo>``."""
        return self.root / target.rel_path

    def worktree_dir(self, target: RepoTarget, slug: str) -> Path:
        """A work item's worktree, quarantined under ``<root>/.worktrees/…``."""
        return (
            self.root / ".worktrees" / target.rel_path / _safe_component(slug, "slug")
        )

    def workitem_dir(self, slug: str) -> Path:
        """A work item's own folder (clone strategy): ``<root>/.work-items/<slug>``."""
        return self.root / ".work-items" / _safe_component(slug, "slug")

    def clone_dir(self, target: RepoTarget, slug: str) -> Path:
        """A repo cloned inside a work item's folder (clone strategy)."""
        return self.workitem_dir(slug) / target.rel_path

    def is_available(self) -> bool:
        return shutil.which(self.git) is not None

    # -- git plumbing -----------------------------------------------------------

    def _git(
        self,
        args: List[str],
        *,
        cwd: Optional[Path] = None,
        timeout: Optional[float] = None,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        if not self.is_available():
            raise WorkspaceError(
                f"git binary {self.git!r} not found on PATH; install git or point "
                "the workspace at the right binary"
            )
        cmd = [self.git] + args
        logger.debug("running %s (cwd=%s)", " ".join(cmd[:5]) + " …", cwd)
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise WorkspaceError(f"git {args[0]} timed out after {timeout}s") from exc
        except OSError as exc:
            raise WorkspaceError(f"could not run git: {exc}") from exc
        if check and proc.returncode != 0:
            raise WorkspaceError(
                f"git {args[0]} exited {proc.returncode}: "
                f"{proc.stderr.strip() or proc.stdout.strip()}"
            )
        return proc

    def _is_clone(self, repo_dir: Path) -> bool:
        return (repo_dir / ".git").exists()

    # -- strategy dispatch ------------------------------------------------------

    def prepare(
        self,
        target: RepoTarget,
        slug: str,
        *,
        branch: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """Provide a ready checkout for one work item, per the configured strategy.

        Returns the directory the session should run in. Raises
        :class:`WorkspaceError` on a git failure so the caller can fail+retry.
        """
        if self.strategy == "clone":
            return self.ensure_workitem_clone(
                target, slug, branch=branch, timeout=timeout
            )
        return self.ensure_worktree(target, slug, branch=branch, timeout=timeout)

    def cleanup(
        self, target: RepoTarget, slug: str, *, timeout: Optional[float] = None
    ) -> bool:
        """Remove a work item's runtime checkout (best-effort). True if it existed.

        ``worktree``: unregister+delete the worktree, keep the shared clone.
        ``clone``: delete the whole per-work-item folder (every repo it cloned).
        """
        if self.strategy == "clone":
            return self.remove_workitem_clone(slug)
        return self.remove_worktree(target, slug, timeout=timeout)

    # -- clone / worktree lifecycle ---------------------------------------------

    def ensure_clone(
        self, target: RepoTarget, *, timeout: Optional[float] = None
    ) -> Path:
        """Clone ``target`` if absent, else best-effort ``fetch``; return its dir."""
        repo_dir = self.repo_dir(target)
        if self._is_clone(repo_dir):
            try:  # a stale mirror is fine; a network blip must not block dispatch
                self._git(["fetch", "--prune", "origin"], cwd=repo_dir, timeout=timeout)
            except WorkspaceError as exc:
                logger.warning(
                    "fetch of %s failed (using cached clone): %s", repo_dir, exc
                )
            return repo_dir
        repo_dir.parent.mkdir(parents=True, exist_ok=True)
        logger.info("cloning %s -> %s", target.clone_url, repo_dir)
        self._git(["clone", target.clone_url, str(repo_dir)], timeout=timeout)
        return repo_dir

    def default_branch(self, repo_dir: Path, *, timeout: Optional[float] = None) -> str:
        """The clone's default branch (from ``origin/HEAD``), falling back to main."""
        try:
            proc = self._git(
                ["rev-parse", "--abbrev-ref", "origin/HEAD"],
                cwd=repo_dir,
                timeout=timeout,
                check=False,
            )
            ref = proc.stdout.strip()  # e.g. "origin/main"
            if proc.returncode == 0 and "/" in ref:
                return ref.split("/", 1)[1]
        except WorkspaceError:
            pass
        return "main"

    def ensure_worktree(
        self,
        target: RepoTarget,
        slug: str,
        *,
        branch: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """Return a ready worktree for one work item, cloning the repo if needed.

        With ``branch`` (a PR head ref), the worktree checks out that branch
        (fetched from origin). Without one (a fresh issue), it starts detached at
        the default branch's tip — the primary clone keeps that branch checked
        out, so a shared branch would otherwise be rejected — and the harness
        creates its own feature branch inside.
        """
        repo_dir = self.ensure_clone(target, timeout=timeout)
        worktree = self.worktree_dir(target, slug)
        if (worktree / ".git").exists():
            return worktree  # already prepared (restart / redelivery)
        worktree.parent.mkdir(parents=True, exist_ok=True)
        if branch:
            try:
                self._git(["fetch", "origin", branch], cwd=repo_dir, timeout=timeout)
                self._git(
                    [
                        "worktree",
                        "add",
                        "-B",
                        branch,
                        str(worktree),
                        f"origin/{branch}",
                    ],
                    cwd=repo_dir,
                    timeout=timeout,
                )
                return worktree
            except WorkspaceError as exc:
                # A PR head that origin doesn't have yet (or a fork ref) — don't
                # fail the spawn; fall back to a detached default-branch worktree.
                logger.warning(
                    "worktree on branch %r failed (%s); using detached default branch",
                    branch,
                    exc,
                )
        base = f"origin/{self.default_branch(repo_dir, timeout=timeout)}"
        self._git(
            ["worktree", "add", "--detach", str(worktree), base],
            cwd=repo_dir,
            timeout=timeout,
        )
        return worktree

    def remove_worktree(
        self, target: RepoTarget, slug: str, *, timeout: Optional[float] = None
    ) -> bool:
        """Remove a work item's worktree (best-effort). Returns True if it existed.

        Called on PR merge/close cleanup: unregister the worktree from git and
        delete its directory. The primary clone and any local branch are left
        untouched — cleanup is cheap and non-destructive by design.
        """
        repo_dir = self.repo_dir(target)
        worktree = self.worktree_dir(target, slug)
        existed = worktree.exists()
        if self._is_clone(repo_dir):
            try:
                self._git(
                    ["worktree", "remove", "--force", str(worktree)],
                    cwd=repo_dir,
                    timeout=timeout,
                    check=False,
                )
                self._git(
                    ["worktree", "prune"], cwd=repo_dir, timeout=timeout, check=False
                )
            except WorkspaceError as exc:  # never raise during cleanup
                logger.warning(
                    "worktree cleanup for %s hit git error: %s", worktree, exc
                )
        if worktree.exists():  # ensure the dir is gone even if git left it
            shutil.rmtree(worktree, ignore_errors=True)
            existed = True
        return existed

    def ensure_workitem_clone(
        self,
        target: RepoTarget,
        slug: str,
        *,
        branch: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Path:
        """Clone ``target`` into the work item's own folder (clone strategy).

        Independent full clone (no shared object store), so — unlike a worktree —
        the default branch can be checked out directly and a PR head branch is
        checked out in place. Idempotent: an existing clone is reused (fetched).
        """
        dest = self.clone_dir(target, slug)
        if (dest / ".git").exists():
            try:  # a network blip on refresh must not block dispatch
                self._git(["fetch", "--prune", "origin"], cwd=dest, timeout=timeout)
            except WorkspaceError as exc:
                logger.warning("fetch of %s failed (using cached clone): %s", dest, exc)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        logger.info("cloning %s -> %s (work-item folder)", target.clone_url, dest)
        self._git(["clone", target.clone_url, str(dest)], timeout=timeout)
        if branch:
            try:
                self._git(["fetch", "origin", branch], cwd=dest, timeout=timeout)
                self._git(
                    ["checkout", "-B", branch, f"origin/{branch}"],
                    cwd=dest,
                    timeout=timeout,
                )
            except WorkspaceError as exc:
                # PR head origin doesn't have yet (or a fork ref) — keep the
                # default branch the clone already checked out; don't fail spawn.
                logger.warning(
                    "checkout of branch %r failed (%s); staying on default branch",
                    branch,
                    exc,
                )
        return dest

    def remove_workitem_clone(self, slug: str) -> bool:
        """Delete a work item's whole folder — every repo it cloned (clone strategy)."""
        folder = self.workitem_dir(slug)
        if not folder.exists():
            return False
        shutil.rmtree(folder, ignore_errors=True)
        return True
