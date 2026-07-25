"""the-loop's operational GitHub labels — create them, add them, remove them.

Two labels drive the daemon from the GitHub UI:

* the **auto-execute** label (``routing.autoExecuteLabel``) — opts a work item
  into autonomous execution (issue-15);
* the **paused** label (``routing.pausedLabel``) — stops the-loop acting on a
  work item, and removing it starts again (issue-98).

A label-driven control is only usable if the label exists, so ``the-loop labels
ensure`` creates them (idempotently) during init/onboarding, and ``sessions
pause``/``resume`` add and remove the paused label so the ticket shows the same
state the local ledger holds.

Everything goes through the operator's own ``gh`` CLI — the daemon's existing
auth posture (no token of the-loop's own), the same as ``reactions.py`` and
``announce.py``. Label writes on a work item are **best-effort**: a failure is
reported and returned, never raised, because the local pause must stand on its
own when GitHub is unreachable. ``labels ensure`` is the exception — an
onboarding command that silently created nothing would be worse than one that
fails loudly.

The GitHub **issues** endpoint is used for label add/remove on purpose: on
GitHub a pull request *is* an issue, so one path serves both kinds (the same
reasoning as ``GhClient.fetch_item_state``).

Spec: docs/specs/issue-98/design.md §7.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence
from urllib.parse import quote

from .sessions import WorkItemRef

logger = logging.getLogger("the-loop.labels")

GH_INSTALL_HINT = (
    "macOS: `brew install gh` · Debian/Ubuntu: `apt install gh` · "
    "others: https://github.com/cli/cli#installation — then `gh auth login`"
)

# Defensive validation before anything reaches a gh argv (the values come from
# config and from parsed refs, but they still end up on a command line).
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")  # owner / repo path segments
_LABEL_RE = re.compile(r"^[^\x00-\x1f]{1,50}$")  # GitHub's own label limit


@dataclass(frozen=True)
class LabelSpec:
    """One label the-loop wants to exist, with how it should look."""

    name: str
    color: str  # 6 hex digits, no leading '#'
    description: str


def default_specs(auto_execute_label: str, paused_label: str) -> List[LabelSpec]:
    """The operational labels, named from config (a renamed label still gets made)."""
    specs = []
    if auto_execute_label:
        specs.append(
            LabelSpec(
                name=auto_execute_label,
                color="0E8A16",
                description="the-loop: work this item autonomously",
            )
        )
    if paused_label:
        specs.append(
            LabelSpec(
                name=paused_label,
                color="D93F0B",
                description="the-loop: pause monitoring for this item",
            )
        )
    return specs


@dataclass
class LabelResult:
    """Outcome of one label operation."""

    ok: bool
    changed: bool = False  # something was actually created/added/removed
    detail: str = ""
    error: str = ""


class LabelError(Exception):
    """``labels ensure`` could not run at all (no gh, bad coordinates, API error)."""


class GitHubLabeler:
    """Create/add/remove labels through the operator's ``gh`` CLI.

    ``runner`` is injectable so tests drive it without a real ``gh`` (mirrors
    :class:`~the_loop.poller.github.GhClient` and
    :class:`~the_loop.reactions.GitHubReactor`).
    """

    def __init__(
        self,
        gh_binary: str = "gh",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout: Optional[float] = 30.0,
    ):
        self.gh_binary = gh_binary
        self._runner = runner
        self.timeout = timeout

    # -- plumbing --------------------------------------------------------------

    def is_available(self) -> bool:
        return shutil.which(self.gh_binary) is not None

    def _run(self, argv: Sequence[str]) -> subprocess.CompletedProcess:
        cmd = [self.gh_binary] + list(argv)
        logger.debug("running %s", " ".join(cmd))
        return self._runner(cmd, capture_output=True, text=True, timeout=self.timeout)

    @staticmethod
    def _detail(proc: subprocess.CompletedProcess) -> str:
        return ((proc.stderr or "") + (proc.stdout or "")).strip()

    @staticmethod
    def _validate(owner: str, repo: str, label: str) -> None:
        if not _NAME_RE.match(owner) or not _NAME_RE.match(repo):
            raise LabelError(f"invalid repository {owner}/{repo}")
        if not _LABEL_RE.match(label):
            raise LabelError(f"invalid label name {label!r}")

    # -- ensure (init / onboarding) --------------------------------------------

    def existing_labels(self, owner: str, repo: str) -> List[str]:
        """Names of every label already in the repo (raises on any gh failure)."""
        proc = self._run(
            ["api", "--paginate", f"repos/{owner}/{repo}/labels", "--jq", ".[].name"]
        )
        if proc.returncode != 0:
            raise LabelError(
                f"could not list labels for {owner}/{repo}: {self._detail(proc)}"
            )
        names = [line.strip() for line in (proc.stdout or "").splitlines()]
        return [name for name in names if name]

    def ensure(
        self,
        owner: str,
        repo: str,
        specs: Sequence[LabelSpec],
        dry_run: bool = False,
    ) -> List[LabelResult]:
        """Create every missing label; skip the ones already there (idempotent)."""
        if not self.is_available():
            raise LabelError(
                f"gh CLI {self.gh_binary!r} not found on PATH — install it "
                f"({GH_INSTALL_HINT})"
            )
        for spec in specs:
            self._validate(owner, repo, spec.name)
        present = set(self.existing_labels(owner, repo))
        results = []
        for spec in specs:
            if spec.name in present:
                results.append(
                    LabelResult(ok=True, changed=False, detail=f"{spec.name}: exists")
                )
                continue
            if dry_run:
                results.append(
                    LabelResult(
                        ok=True, changed=False, detail=f"{spec.name}: would create"
                    )
                )
                continue
            proc = self._run(
                [
                    "api",
                    "--method",
                    "POST",
                    f"repos/{owner}/{repo}/labels",
                    "-f",
                    f"name={spec.name}",
                    "-f",
                    f"color={spec.color}",
                    "-f",
                    f"description={spec.description}",
                ]
            )
            if proc.returncode != 0:
                raise LabelError(
                    f"could not create label {spec.name!r} in {owner}/{repo}: "
                    f"{self._detail(proc)}"
                )
            results.append(
                LabelResult(ok=True, changed=True, detail=f"{spec.name}: created")
            )
        return results

    # -- per-work-item (pause / resume) ----------------------------------------

    def add(self, work_item: WorkItemRef, label: str) -> LabelResult:
        """Put ``label`` on the issue/PR. Best-effort: never raises."""
        return self._write(work_item, label, remove=False)

    def remove(self, work_item: WorkItemRef, label: str) -> LabelResult:
        """Take ``label`` off the issue/PR. Best-effort: never raises."""
        return self._write(work_item, label, remove=True)

    def _write(self, work_item: WorkItemRef, label: str, remove: bool) -> LabelResult:
        verb = "remove" if remove else "add"
        if work_item.provider != "github":
            return LabelResult(
                ok=False,
                error=(
                    f"{work_item.ref} is not a GitHub work item; its pause is "
                    "local only"
                ),
            )
        try:
            self._validate(work_item.owner, work_item.repo, label)
        except LabelError as exc:
            return LabelResult(ok=False, error=str(exc))
        if not self.is_available():
            return LabelResult(
                ok=False,
                error=(
                    f"gh CLI {self.gh_binary!r} not found on PATH; could not "
                    f"{verb} the {label!r} label ({GH_INSTALL_HINT})"
                ),
            )
        base = f"repos/{work_item.owner}/{work_item.repo}/issues/{work_item.number}"
        if remove:
            argv = ["api", "--method", "DELETE", f"{base}/labels/{quote(label)}"]
        else:
            argv = [
                "api",
                "--method",
                "POST",
                f"{base}/labels",
                "-f",
                f"labels[]={label}",
            ]
        try:
            proc = self._run(argv)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return LabelResult(ok=False, error=str(exc))
        if proc.returncode != 0:
            detail = self._detail(proc)
            if remove and "404" in detail:
                # Already off the item — the state the caller wanted.
                return LabelResult(ok=True, changed=False, detail="label not present")
            return LabelResult(ok=False, error=f"gh exited {proc.returncode}: {detail}")
        return LabelResult(ok=True, changed=True, detail=f"label {verb}ed")

    # -- read (used by `sessions show` when it wants live labels) ---------------

    def labels_on(self, work_item: WorkItemRef) -> Optional[List[str]]:
        """Labels currently on the issue/PR, or ``None`` when they can't be read."""
        if work_item.provider != "github" or not self.is_available():
            return None
        base = f"repos/{work_item.owner}/{work_item.repo}/issues/{work_item.number}"
        try:
            proc = self._run(["api", base])
        except (OSError, subprocess.TimeoutExpired):
            return None
        if proc.returncode != 0:
            return None
        try:
            data = json.loads(proc.stdout or "null")
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return [
            str((lab or {}).get("name") or "")
            for lab in (data.get("labels") or [])
            if isinstance(lab, dict) and lab.get("name")
        ]
