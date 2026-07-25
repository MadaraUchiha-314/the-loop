"""GitHub poll provider: a ``gh`` CLI wrapper + the GitHub :class:`PollProvider`.

This is the *only* place in the polling stack that knows about GitHub. The
poller core (``poller.py``) speaks the provider-agnostic contract in
``base.py``; GitHub is reached solely because a ``polling.sources`` config entry
selects ``provider: github``.

Polling reads GitHub through the user's own ``gh`` CLI (already authenticated),
exactly as the-loop uses ``gh`` elsewhere — so the poller needs no token of its
own and inherits ``gh``'s auth/enterprise config. ``gh`` is a native binary a
Python wheel cannot carry, so its presence is verified up front (mirrors the
tmux/ttyd preflight in ``runner.check_dependencies``).

Everything shells out to ``gh ... --json`` and parses stdout, with an injectable
``runner`` so tests drive it with canned JSON instead of a real ``gh``. The
provider maps ``gh``'s shapes onto the neutral :class:`WorkItem`/:class:`Comment`
and builds the shared ``RoutedEvent`` the dispatcher already consumes.

Spec: docs/specs/issue-34/design.md §2.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from ..sessions import WorkItemRef
from ..webhook.router import RoutedEvent, event_carries_label, extract_work_items
from .base import (
    Closure,
    Comment,
    PollProvider,
    ProviderError,
    WorkItem,
    register_provider,
)

logger = logging.getLogger("the-loop.poll")

_GH_INSTALL_HINT = (
    "macOS: `brew install gh` · Debian/Ubuntu: `apt install gh` · "
    "others: https://github.com/cli/cli#installation — then `gh auth login`"
)

# Upper bound on items fetched per repo per kind; a labelled backlog larger than
# this is pathological and the newest still get through on later polls.
_LIST_LIMIT = 200

# Item kinds this provider emits (provider-local vocabulary).
_KIND_ISSUE = "issue"
_KIND_PR = "pull-request"

# JSON fields the PR listing asks for. ``closingIssuesReferences`` is GitHub's
# own PR→issue linkage (the Development panel as well as the closing keywords it
# parses); asking for it here keeps the linkage free — it rides the listing call
# the poller already makes each cycle (issue-93). It is a relatively recent
# ``gh`` field, so an older binary rejects it and the listing degrades to
# ``_PR_FIELDS_LEGACY`` (branch/keyword conventions only).
_PR_LINK_FIELD = "closingIssuesReferences"
_PR_FIELDS_LEGACY = "number,title,labels,updatedAt,url,headRefName,body,author"
_PR_FIELDS = f"{_PR_FIELDS_LEGACY},{_PR_LINK_FIELD}"


class GhError(ProviderError):
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
class GhItemState:
    """The lifecycle state of one issue/PR (``/issues/{n}`` REST shape).

    One endpoint answers for both kinds: on GitHub's REST API a pull request
    *is* an issue, and the response carries a ``pull_request`` object whose
    ``merged_at`` separates a merged PR from a closed one.
    """

    number: int
    state: str  # "open" | "closed"
    is_pr: bool = False
    merged: bool = False
    title: str = ""
    url: str = ""

    @property
    def open(self) -> bool:
        return self.state == "open"


@dataclass(frozen=True)
class GhItem:
    """A labelled issue or PR returned by ``gh issue/pr list``."""

    number: int
    title: str
    labels: List[str]
    updated_at: str
    url: str
    is_pr: bool
    author: str = ""  # login that opened the issue/PR (authorization guard)
    head_ref: str = ""  # PRs only (links a PR to its issue-<n> branch)
    body: str = ""  # PRs only (closing keywords live here)
    # PRs only: issue numbers GitHub itself reports the PR as closing (issue-93)
    linked_issues: List[int] = field(default_factory=list)


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
        # Latched once an old gh rejects _PR_LINK_FIELD, so later cycles skip
        # the attempt that is known to fail (issue-93).
        self._no_link_field = False

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
                "number,title,labels,updatedAt,url,author",
            ]
        )
        return [self._item_from_json(row, is_pr=False) for row in data or []]

    def list_labeled_prs(self, owner: str, repo: str, label: str) -> List[GhItem]:
        """Open PRs in ``owner/repo`` carrying ``label``, with their linked issues.

        Degrades (once, then latched) to the legacy field list when the installed
        ``gh`` does not know ``closingIssuesReferences`` — routing then falls back
        to the head-branch/closing-keyword conventions, exactly as before
        issue-93. Any other ``gh`` failure still propagates: a downgrade must not
        mask an auth or network fault.
        """
        fields = _PR_FIELDS_LEGACY if self._no_link_field else _PR_FIELDS
        try:
            data = self._list_prs(owner, repo, label, fields)
        except GhError as exc:
            if self._no_link_field or _PR_LINK_FIELD.lower() not in str(exc).lower():
                raise
            logger.warning(
                "this gh does not support the '%s' JSON field, so a PR linked to "
                "an issue only through GitHub's Development panel cannot be "
                "matched to that issue's session; upgrade gh to restore it (%s). "
                "Falling back to head-branch / closing-keyword conventions.",
                _PR_LINK_FIELD,
                _GH_INSTALL_HINT,
            )
            self._no_link_field = True
            data = self._list_prs(owner, repo, label, _PR_FIELDS_LEGACY)
        return [self._item_from_json(row, is_pr=True) for row in data or []]

    def _list_prs(self, owner: str, repo: str, label: str, fields: str):
        return self._run_json(
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
                fields,
            ]
        )

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

    def fetch_item_state(self, owner: str, repo: str, number: int) -> GhItemState:
        """Lifecycle state of one issue/PR — the closure question (issue-94).

        Uses the REST ``issues`` endpoint deliberately: the session registry
        records a bare ``#<number>`` with no kind, and ``gh issue view`` refuses
        PR numbers (and vice-versa), while this one endpoint answers for both.
        """
        data = self._run_json(["api", f"repos/{owner}/{repo}/issues/{number}"])
        if not isinstance(data, dict) or not data:
            raise GhError(
                f"gh api repos/{owner}/{repo}/issues/{number} returned no object"
            )
        pull_request = data.get("pull_request")
        return GhItemState(
            number=int(data.get("number") or number),
            state=str(data.get("state") or ""),
            is_pr=isinstance(pull_request, dict),
            merged=bool((pull_request or {}).get("merged_at")),
            title=str(data.get("title") or ""),
            url=str(data.get("html_url") or ""),
        )

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
            author=str((row.get("author") or {}).get("login") or ""),
            head_ref=str(row.get("headRefName") or ""),
            body=str(row.get("body") or ""),
            linked_issues=[
                number
                for number in (
                    (ref or {}).get("number") for ref in (row.get(_PR_LINK_FIELD) or [])
                )
                if isinstance(number, int)
            ],
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


@register_provider
class GitHubPollProvider(PollProvider):
    """GitHub implementation of the poll-provider contract.

    Discovers labelled issues/PRs via ``gh``, and maps them onto the neutral
    ``WorkItem``/``Comment`` and the shared ``RoutedEvent`` shape. All GitHub
    payload synthesis lives here so the poller core stays provider-agnostic.
    """

    name = "github"

    def __init__(
        self,
        repos: List[RepoSpec],
        label: str,
        monitor_issues: bool = True,
        monitor_prs: bool = True,
        gh: Optional[GhClient] = None,
    ):
        self.repos = repos
        self.label = label
        self.monitor_issues = monitor_issues
        self.monitor_prs = monitor_prs
        self.gh = gh or GhClient()

    @classmethod
    def from_source(cls, source: dict, *, default_label: str) -> "GitHubPollProvider":
        source = source or {}
        monitor = source.get("monitor") or {}
        repos = [str(r) for r in (source.get("repos") or [])]
        return cls(
            repos=parse_repos(repos),
            label=str(source.get("label") or "") or default_label,
            monitor_issues=bool(monitor.get("issues", True)),
            monitor_prs=bool(monitor.get("pullRequests", True)),
            gh=GhClient(binary=str(source.get("ghBinary", "gh"))),
        )

    def describe(self) -> str:
        return f"github {', '.join(s.full_name for s in self.repos) or '(no repos)'}"

    def check_dependencies(self) -> List[str]:
        return check_gh_dependency(self.gh.binary)

    # -- discovery -------------------------------------------------------------

    def list_work_items(self) -> List[WorkItem]:
        if not self.repos:
            raise ProviderError(
                "github polling source has no repositories — set the source's "
                "'repos' (OWNER/REPO) in the CLI config"
            )
        items: List[WorkItem] = []
        for spec in self.repos:
            if self.monitor_issues:
                for gh_item in self.gh.list_labeled_issues(
                    spec.owner, spec.repo, self.label
                ):
                    items.append(self._work_item(spec, gh_item))
            if self.monitor_prs:
                for gh_item in self.gh.list_labeled_prs(
                    spec.owner, spec.repo, self.label
                ):
                    items.append(self._work_item(spec, gh_item))
        return items

    def list_comments(self, item: WorkItem) -> List[Comment]:
        gh_comments = self.gh.list_comments(
            item.owner, item.repo, item.number, is_pr=item.kind == _KIND_PR
        )
        return [
            Comment(
                id=c.id,
                body=c.body,
                author=c.author,
                created_at=c.created_at,
                url=c.url,
            )
            for c in gh_comments
        ]

    # -- event construction ----------------------------------------------------

    def refs(self, item: WorkItem) -> List[WorkItemRef]:
        return extract_work_items(self._event_name(item), self._item_payload(item))

    def presence_event(self, item: WorkItem, refs: List[WorkItemRef]) -> RoutedEvent:
        payload = self._item_payload(item)
        # Fresh delivery id each emission: presence is only emitted while no
        # session exists, so a failed spawn retries next cycle (never spams).
        return RoutedEvent(
            event=self._event_name(item),
            action="labeled",
            delivery_id=f"poll-presence-{item.ref}-{uuid.uuid4()}",
            work_items=refs,
            payload=payload,
            labeled=event_carries_label(payload, self.label),
        )

    def comment_event(
        self, item: WorkItem, comment: Comment, refs: List[WorkItemRef]
    ) -> RoutedEvent:
        # issue_comment carries issue AND PR conversation comments on GitHub;
        # reuse the item's refs so a PR comment still reaches a session
        # registered against the linked issue. labeled=False: comments only feed
        # existing sessions, never spawn (spawning is presence's job).
        payload = self._item_payload(item)
        payload["action"] = "created"
        payload["comment"] = {
            "id": comment.id,
            "body": comment.body,
            "html_url": comment.url,
            "created_at": comment.created_at,
            "user": {"login": comment.author},
        }
        return RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id=f"poll-comment-{comment.id}",
            work_items=refs,
            payload=payload,
            labeled=False,
        )

    # -- closure reconciliation (issue-94) -------------------------------------

    def owns(self, ref: WorkItemRef) -> bool:
        """True when ``ref`` is a GitHub item in one of this source's repos."""
        if ref.provider != self.name:
            return False
        full_name = f"{ref.owner}/{ref.repo}".lower()
        return any(spec.full_name.lower() == full_name for spec in self.repos)

    def closure(self, ref: WorkItemRef) -> Optional[Closure]:
        """Whether ``ref`` has ended, and how (``None`` while it is still open)."""
        state = self.gh.fetch_item_state(ref.owner, ref.repo, ref.number)
        if state.open or not state.state:
            return None
        return Closure(
            state="merged" if state.merged else "closed",
            kind=_KIND_PR if state.is_pr else _KIND_ISSUE,
            title=state.title,
            url=state.url,
        )

    def closure_event(self, ref: WorkItemRef, closure: Closure) -> RoutedEvent:
        """The webhook-shaped ``closed`` event the dispatcher already handles.

        Deliberately the same shape a real webhook carries, so a polled closure
        and a pushed one take one identical close path (registry, tmux,
        workspace, event log). The delivery id is stable per (item, state) so a
        repeat inside the dedup window is a no-op.
        """
        entity: dict = {
            "number": ref.number,
            "title": closure.title,
            "html_url": closure.url,
            "labels": [],
        }
        payload: dict = {
            "action": "closed",
            "repository": {"full_name": f"{ref.owner}/{ref.repo}"},
        }
        if closure.kind == _KIND_PR:
            event = "pull_request"
            entity["merged"] = closure.merged
            payload["pull_request"] = entity
        else:
            event = "issues"
            payload["issue"] = entity
        return RoutedEvent(
            event=event,
            action="closed",
            delivery_id=f"poll-close-{ref.ref}-{closure.state}",
            work_items=[ref],
            payload=payload,
            labeled=False,
        )

    # -- mapping ---------------------------------------------------------------

    @staticmethod
    def _work_item(spec: RepoSpec, gh_item: GhItem) -> WorkItem:
        return WorkItem(
            provider="github",
            owner=spec.owner,
            repo=spec.repo,
            number=gh_item.number,
            kind=_KIND_PR if gh_item.is_pr else _KIND_ISSUE,
            title=gh_item.title,
            url=gh_item.url,
            author=gh_item.author,
            labels=list(gh_item.labels),
            raw={
                "headRef": gh_item.head_ref,
                "body": gh_item.body,
                "linkedIssues": list(gh_item.linked_issues),
            },
        )

    @staticmethod
    def _event_name(item: WorkItem) -> str:
        return "pull_request" if item.kind == _KIND_PR else "issues"

    @staticmethod
    def _item_payload(item: WorkItem) -> dict:
        """A webhook-shaped payload so router helpers and templates work as-is."""
        labels = [{"name": name} for name in item.labels]
        entity = {
            "number": item.number,
            "title": item.title,
            "html_url": item.url,
            "labels": labels,
        }
        payload: dict = {
            "action": "labeled",
            "repository": {"full_name": f"{item.owner}/{item.repo}"},
        }
        if item.kind == _KIND_PR:
            entity["head"] = {"ref": item.raw.get("headRef", "")}
            entity["body"] = item.raw.get("body", "")
            # Same shape a real webhook payload would carry, so the router reads
            # GitHub's own PR→issue linkage through one code path (issue-93).
            entity["closingIssuesReferences"] = [
                {"number": n} for n in item.raw.get("linkedIssues") or []
            ]
            payload["pull_request"] = entity
        else:
            payload["issue"] = entity
        return payload
