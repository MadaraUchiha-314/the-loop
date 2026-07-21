"""Thin ``gh`` CLI wrapper for the poller (issue-34).

Polling reads GitHub through the user's own ``gh`` CLI (already authenticated),
exactly as the-loop uses ``gh`` elsewhere — so the poller needs no token of its
own and inherits ``gh``'s auth/enterprise config. ``gh`` is a native binary a
Python wheel cannot carry, so its presence is verified up front (mirrors the
tmux/ttyd preflight in ``runner.check_dependencies``).

Everything shells out to ``gh ... --json`` and parses stdout, with an injectable
``runner`` so tests drive it with canned JSON instead of a real ``gh``.

Spec: docs/specs/issue-34/design.md §2.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

logger = logging.getLogger("the-loop.gh-poll")

_GH_INSTALL_HINT = (
    "macOS: `brew install gh` · Debian/Ubuntu: `apt install gh` · "
    "others: https://github.com/cli/cli#installation — then `gh auth login`"
)

# Upper bound on items fetched per repo per kind; a labelled backlog larger than
# this is pathological and the newest still get through on later polls.
_LIST_LIMIT = 200


class GhError(Exception):
    """A ``gh`` invocation failed (non-zero exit, bad JSON, or gh missing)."""


@dataclass(frozen=True)
class GhComment:
    """One issue/PR conversation comment (GraphQL ``comments`` shape)."""

    id: str  # stable node id, used for cross-poll dedup
    body: str
    author: str
    created_at: str
    url: str


@dataclass(frozen=True)
class GhItem:
    """A labelled issue or PR returned by ``gh issue/pr list``."""

    number: int
    title: str
    labels: List[str]
    updated_at: str
    url: str
    is_pr: bool
    head_ref: str = ""  # PRs only (links a PR to its issue-<n> branch)
    body: str = ""  # PRs only (closing keywords live here)


def check_gh_dependency(binary: str = "gh") -> List[str]:
    """Missing-dependency messages for ``gh`` (empty when present)."""
    if shutil.which(binary) is None:
        return [f"missing dependency: {binary} — install it ({_GH_INSTALL_HINT})"]
    return []


class GhClient:
    """Read-only ``gh`` wrapper: list labelled issues/PRs and their comments."""

    def __init__(
        self,
        binary: str = "gh",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout: Optional[float] = 60.0,
    ):
        self.binary = binary
        self._runner = runner
        self.timeout = timeout

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    # -- primitives -------------------------------------------------------------

    def _run_json(self, argv: Sequence[str]):
        """Run ``gh <argv>`` and parse its stdout as JSON."""
        cmd = [self.binary] + list(argv)
        logger.debug("running %s", " ".join(cmd))
        try:
            proc = self._runner(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise GhError(f"gh {argv[0]} timed out after {self.timeout}s") from exc
        except OSError as exc:
            raise GhError(f"could not run gh: {exc}") from exc
        if proc.returncode != 0:
            raise GhError(
                f"gh {' '.join(argv[:3])} exited {proc.returncode}: "
                f"{(proc.stderr or proc.stdout or '').strip()}"
            )
        try:
            return json.loads(proc.stdout or "null")
        except json.JSONDecodeError as exc:
            raise GhError(f"gh {argv[0]} returned invalid JSON: {exc}") from exc

    # -- listing ---------------------------------------------------------------

    def list_labeled_issues(self, owner: str, repo: str, label: str) -> List[GhItem]:
        """Open issues in ``owner/repo`` carrying ``label`` (PRs excluded)."""
        data = self._run_json(
            [
                "issue",
                "list",
                "--repo",
                f"{owner}/{repo}",
                "--label",
                label,
                "--state",
                "open",
                "--limit",
                str(_LIST_LIMIT),
                "--json",
                "number,title,labels,updatedAt,url",
            ]
        )
        return [self._item_from_json(row, is_pr=False) for row in data or []]

    def list_labeled_prs(self, owner: str, repo: str, label: str) -> List[GhItem]:
        """Open PRs in ``owner/repo`` carrying ``label``."""
        data = self._run_json(
            [
                "pr",
                "list",
                "--repo",
                f"{owner}/{repo}",
                "--label",
                label,
                "--state",
                "open",
                "--limit",
                str(_LIST_LIMIT),
                "--json",
                "number,title,labels,updatedAt,url,headRefName,body",
            ]
        )
        return [self._item_from_json(row, is_pr=True) for row in data or []]

    def list_comments(
        self, owner: str, repo: str, number: int, is_pr: bool
    ) -> List[GhComment]:
        """All conversation comments on an issue/PR (``gh`` paginates for us).

        ``gh issue view`` rejects PR numbers and vice-versa, so the kind picks
        the sub-command; both expose the same GraphQL ``comments`` shape.
        """
        sub = "pr" if is_pr else "issue"
        data = self._run_json(
            [
                sub,
                "view",
                str(number),
                "--repo",
                f"{owner}/{repo}",
                "--json",
                "comments",
            ]
        )
        comments = (data or {}).get("comments") or []
        return [self._comment_from_json(c) for c in comments]

    # -- parsing ---------------------------------------------------------------

    @staticmethod
    def _item_from_json(row: dict, is_pr: bool) -> GhItem:
        labels = [
            (lab or {}).get("name", "")
            for lab in (row.get("labels") or [])
            if (lab or {}).get("name")
        ]
        return GhItem(
            number=int(row["number"]),
            title=str(row.get("title") or ""),
            labels=labels,
            updated_at=str(row.get("updatedAt") or ""),
            url=str(row.get("url") or ""),
            is_pr=is_pr,
            head_ref=str(row.get("headRefName") or ""),
            body=str(row.get("body") or ""),
        )

    @staticmethod
    def _comment_from_json(row: dict) -> GhComment:
        author = (row.get("author") or {}).get("login") or ""
        return GhComment(
            id=str(row.get("id") or ""),
            body=str(row.get("body") or ""),
            author=str(author),
            created_at=str(row.get("createdAt") or ""),
            url=str(row.get("url") or ""),
        )


@dataclass
class RepoSpec:
    """An ``owner/repo`` target parsed from config/flags."""

    owner: str
    repo: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @classmethod
    def parse(cls, value: str) -> "RepoSpec":
        owner, sep, repo = str(value).strip().partition("/")
        if not sep or not owner or not repo:
            raise ValueError(
                f"invalid repo {value!r}; expected OWNER/REPO (e.g. octo/hello)"
            )
        return cls(owner=owner, repo=repo)


def parse_repos(values: Sequence[str]) -> List[RepoSpec]:
    """Parse a list of ``owner/repo`` strings, de-duplicated in order."""
    seen = set()
    specs: List[RepoSpec] = []
    for value in values:
        spec = RepoSpec.parse(value)
        if spec.full_name not in seen:
            seen.add(spec.full_name)
            specs.append(spec)
    return specs
