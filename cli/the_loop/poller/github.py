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
from typing import Callable, Dict, List, Optional, Sequence

from ..comments import gh_host_args
from ..sessions import DEFAULT_GITHUB_HOST, WorkItemRef, is_github_host
from ..webhook.router import RoutedEvent, event_carries_label, extract_work_items
from .base import (
    REPROBE_EVERY_CYCLES,
    Closure,
    Comment,
    Listing,
    PollProvider,
    ProviderError,
    ScopeFailure,
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

# The three surfaces a pull request carries instructions on (issue-246). GitHub
# files them under three different objects, and the poller used to read only the
# first — so a human's instruction left as a review was never forwarded, while
# the webhook ingress had handled all three since issue-15.
_KIND_CONVERSATION = "conversation"  # IssueComment (IC_) — `gh pr view --json comments`
_KIND_REVIEW = "review"  # PullRequestReview (PRR_) — a review body
_KIND_REVIEW_THREAD = "review-thread"  # PullRequestReviewComment (PRRC_) — inline

# A review a human has written but not submitted. Visible only to its author, so
# forwarding it would deliver words nobody has sent.
_REVIEW_PENDING = "PENDING"

# Page size for the REST reads below. `--paginate` walks every page, so this
# only decides how many round trips a long thread costs.
_REST_PAGE_SIZE = 100

# What `gh issue list` says about a repository whose GitHub Issues are turned
# off — the ONE condition this provider classifies as permanent (issue-315). It
# is configuration drift, not a fault: retrying it every cycle can only fail
# the same way, and it used to take the whole source down with it. If GitHub
# ever rewords the message the failure degrades to transient — retried,
# isolated, visible — never to silence.
_ISSUES_DISABLED = "has disabled issues"
_ISSUES_OFF_REASON = (
    "issues are disabled on this repository; its issues are skipped and "
    f"re-probed every {REPROBE_EVERY_CYCLES} cycles, its pull requests are "
    "still polled"
)


class GhError(ProviderError):
    """A ``gh`` invocation failed (non-zero exit, bad JSON, or gh missing)."""


@dataclass(frozen=True)
class GhComment:
    """One comment on an issue/PR — conversation, review, or review thread.

    The first five fields are what every surface has in common, and all the
    poller core reads. ``kind`` and the fields under it are how the provider
    later builds the event GitHub itself would have delivered for this object
    (issue-246); they are empty for a conversation comment.
    """

    id: str  # stable node id, used for cross-poll dedup
    body: str
    author: str
    created_at: str
    url: str
    kind: str = _KIND_CONVERSATION
    state: str = ""  # reviews: APPROVED | CHANGES_REQUESTED | COMMENTED
    path: str = ""  # review threads: the file the comment is anchored to
    line: Optional[int] = None  # review threads: the line, or None if unknown


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

    @staticmethod
    def _repo_flag(owner: str, repo: str, host: str = "") -> str:
        """``[HOST/]OWNER/REPO`` — ``gh``'s own ``--repo`` grammar (issue-311).

        The host is written exactly when it is not github.com, so every argv a
        github.com source ever produced is unchanged.
        """
        if host and host != DEFAULT_GITHUB_HOST:
            return f"{host}/{owner}/{repo}"
        return f"{owner}/{repo}"

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

    def list_labeled_issues(
        self, owner: str, repo: str, label: str, host: str = ""
    ) -> List[GhItem]:
        """Open issues in ``owner/repo`` carrying ``label`` (PRs excluded)."""
        data = self._run_json(
            [
                "issue",
                "list",
                "--repo",
                self._repo_flag(owner, repo, host),
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

    def list_labeled_prs(
        self, owner: str, repo: str, label: str, host: str = ""
    ) -> List[GhItem]:
        """Open PRs in ``owner/repo`` carrying ``label``, with their linked issues.

        Degrades (once, then latched) to the legacy field list when the installed
        ``gh`` does not know ``closingIssuesReferences`` — routing then falls back
        to the head-branch/closing-keyword conventions, exactly as before
        issue-93. Any other ``gh`` failure still propagates: a downgrade must not
        mask an auth or network fault.
        """
        fields = _PR_FIELDS_LEGACY if self._no_link_field else _PR_FIELDS
        try:
            data = self._list_prs(owner, repo, label, fields, host)
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
            data = self._list_prs(owner, repo, label, _PR_FIELDS_LEGACY, host)
        return [self._item_from_json(row, is_pr=True) for row in data or []]

    def _list_prs(self, owner: str, repo: str, label: str, fields: str, host: str = ""):
        return self._run_json(
            [
                "pr",
                "list",
                "--repo",
                self._repo_flag(owner, repo, host),
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
        self, owner: str, repo: str, number: int, is_pr: bool, host: str = ""
    ) -> List[GhComment]:
        """Every comment on an issue/PR, whichever surface GitHub filed it under.

        For an **issue** this is exactly the call it always was: one
        ``gh issue view --json comments``. ``gh issue view`` rejects PR numbers
        and vice-versa, so the kind picks the sub-command.

        For a **pull request** it is that call plus the two REST reads that
        answer for the other two surfaces (issue-246), merged into one
        chronological list. ``gh pr view --json`` cannot supply them: it exposes
        no review-thread connection at all, so at least one call has to go
        elsewhere, and REST costs a documented endpoint and ``--paginate``
        rather than a hand-written GraphQL query with three cursors. The
        conversation call is deliberately left alone — moving it to REST would
        change its ids from GraphQL node ids to numeric ones and re-forward every
        operator's already-baselined thread on upgrade.

        Ordering is chronological, not per-source: the first-sight control path
        forwards commands "in thread order (so the last command wins)"
        (issue-119), which a merge that simply appended reviews would break.
        """
        sub = "pr" if is_pr else "issue"
        data = self._run_json(
            [
                sub,
                "view",
                str(number),
                "--repo",
                self._repo_flag(owner, repo, host),
                "--json",
                "comments",
            ]
        )
        comments = [
            self._comment_from_json(c) for c in ((data or {}).get("comments") or [])
        ]
        if not is_pr:
            return comments
        comments += self.list_reviews(owner, repo, number, host)
        comments += self.list_review_comments(owner, repo, number, host)
        # Stable sort: same-timestamp items keep their source order.
        return sorted(comments, key=lambda c: c.created_at)

    def list_reviews(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[GhComment]:
        """Submitted PR reviews that carry an instruction (issue-246).

        Two are dropped here rather than downstream, because "carries no
        instruction" is a fact about the GitHub object and not a policy the
        poller core should hold: a review with an **empty body** (an Approve with
        no words), and a **PENDING** one (a draft its author has not submitted).
        Everything else — who may be obeyed, what has already been delivered —
        stays where it is, so the new stream passes the guards conversation
        comments pass, unchanged.
        """
        reviews: List[GhComment] = []
        for row in self._run_rest_list(
            f"repos/{owner}/{repo}/pulls/{number}/reviews", host
        ):
            state = str(row.get("state") or "").upper()
            body = str(row.get("body") or "")
            if state == _REVIEW_PENDING or not body.strip():
                continue
            reviews.append(
                GhComment(
                    id=str(row.get("node_id") or ""),
                    body=body,
                    author=str((row.get("user") or {}).get("login") or ""),
                    created_at=str(row.get("submitted_at") or ""),
                    url=str(row.get("html_url") or ""),
                    kind=_KIND_REVIEW,
                    state=state,
                )
            )
        return reviews

    def list_review_comments(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[GhComment]:
        """Inline review-thread comments, each with the file/line it is on.

        The anchor is part of the instruction — "this is wrong" means nothing
        without it — so it travels with the comment. ``line`` is null once the
        diff has moved past an outdated comment, and GitHub keeps the line it was
        written against in ``original_line``; that is the honest anchor to carry,
        because it is where the reviewer was looking.

        The ``diff_hunk`` GitHub also returns is deliberately **not** carried:
        the forwarded payload is capped (``_PAYLOAD_EXCERPT_MAX_CHARS``), and up
        to thirty lines of diff would truncate the instruction it was meant to
        contextualise. The session can read the diff; it cannot read a comment it
        was never told about.
        """
        inline: List[GhComment] = []
        for row in self._run_rest_list(
            f"repos/{owner}/{repo}/pulls/{number}/comments", host
        ):
            line = row.get("line")
            if not isinstance(line, int):
                line = row.get("original_line")
            inline.append(
                GhComment(
                    id=str(row.get("node_id") or ""),
                    body=str(row.get("body") or ""),
                    author=str((row.get("user") or {}).get("login") or ""),
                    created_at=str(row.get("created_at") or ""),
                    url=str(row.get("html_url") or ""),
                    kind=_KIND_REVIEW_THREAD,
                    path=str(row.get("path") or ""),
                    line=line if isinstance(line, int) else None,
                )
            )
        return inline

    def _run_rest_list(self, path: str, host: str = "") -> List[dict]:
        """Every page of a REST array endpoint, as dicts.

        ``--paginate`` matters rather than being a nicety: REST returns reviews
        oldest-first, so a single capped page would permanently hide the newest
        ones on a heavily-reviewed PR — the exact silence issue-246 is about.

        Failures propagate as :class:`GhError`. Nothing here catches and returns
        an empty list: a read that breaks must look broken, never like a quiet
        pull request.
        """
        data = self._run_json(
            [
                "api",
                *gh_host_args(host),
                f"{path}?per_page={_REST_PAGE_SIZE}",
                "--paginate",
            ]
        )
        if data is None:
            return []
        if not isinstance(data, list):
            raise GhError(
                f"gh api {path} returned {type(data).__name__}, expected a list"
            )
        return [row for row in data if isinstance(row, dict)]

    def fetch_item_state(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> GhItemState:
        """Lifecycle state of one issue/PR — the closure question (issue-94).

        Uses the REST ``issues`` endpoint deliberately: the session registry
        records a bare ``#<number>`` with no kind, and ``gh issue view`` refuses
        PR numbers (and vice-versa), while this one endpoint answers for both.
        """
        data = self._run_json(
            ["api", *gh_host_args(host), f"repos/{owner}/{repo}/issues/{number}"]
        )
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
    """A ``[host/]owner/repo`` target parsed from config/flags.

    ``host`` is ``""`` for github.com (issue-311): ``full_name`` stays the
    ``owner/repo`` a webhook payload's ``repository.full_name`` carries, and
    ``gh_repo`` is ``gh``'s own ``--repo`` grammar with the host written exactly
    when it is not the default.
    """

    owner: str
    repo: str
    host: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def gh_repo(self) -> str:
        return f"{self.host}/{self.full_name}" if self.host else self.full_name

    @classmethod
    def parse(cls, value: str) -> "RepoSpec":
        parts = str(value).strip().split("/")
        host = ""
        if len(parts) == 3:
            # Three segments are a host and a repository only when the first
            # is recognisably a host (A1): `ghe/octo/repo` is a typo, not a
            # work item on a machine called "ghe".
            host, owner, repo = parts
            if not is_github_host(host):
                raise ValueError(
                    f"invalid repo {value!r}; expected [HOST/]OWNER/REPO where HOST "
                    "is a dotted name or one with a port (e.g. ghe.corp/octo/hello)"
                )
        elif len(parts) == 2:
            owner, repo = parts
        else:
            owner = repo = ""
        if not owner or not repo:
            raise ValueError(
                f"invalid repo {value!r}; expected [HOST/]OWNER/REPO (e.g. octo/hello)"
            )
        if host == DEFAULT_GITHUB_HOST:
            host = ""
        return cls(owner=owner, repo=repo, host=host)


def parse_repos(values: Sequence[str]) -> List[RepoSpec]:
    """Parse a list of ``[host/]owner/repo`` strings, de-duplicated in order."""
    seen = set()
    specs: List[RepoSpec] = []
    for value in values:
        spec = RepoSpec.parse(value)
        if spec.gh_repo not in seen:
            seen.add(spec.gh_repo)
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
        # Repositories whose Issues are off (issue-315): scope -> the cycle the
        # condition was last seen. In memory on purpose — a hot reload rebuilds
        # the provider and a restart starts fresh, and both are exactly the
        # moments an operator who just re-enabled Issues wants a re-probe.
        self._issues_off: Dict[str, int] = {}
        self._cycles = 0

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
        """The strict form: the first repository that cannot be listed fails the call.

        Kept for callers that want all-or-nothing; the poller core reads
        :meth:`listing` instead, which is what keeps one repository's failure
        that repository's (issue-315).
        """
        listing = self.listing()
        unlisted = listing.failures + listing.skipped
        if unlisted:
            raise ProviderError(f"{unlisted[0].scope}: {unlisted[0].error}")
        return listing.items

    def listing(self) -> Listing:
        """Every configured repository, each listed on its own (issue-315).

        A repository is this provider's *scope*. One that cannot be listed is
        reported in the listing's ``failures`` and the walk continues, so the
        source's other repositories are polled exactly as if the failing one
        were not configured. The one whole-source failure left is having no
        repositories at all.
        """
        if not self.repos:
            raise ProviderError(
                "github polling source has no repositories — set the source's "
                "'repos' (OWNER/REPO) in the CLI config"
            )
        self._cycles += 1
        out = Listing()
        for spec in self.repos:
            self._list_scope(spec, out)
        return out

    @staticmethod
    def _scope(spec: RepoSpec) -> str:
        """How a repository is named in a :class:`ScopeFailure` — and compared."""
        return spec.gh_repo.lower()

    def scope_of(self, ref: WorkItemRef) -> str:
        if ref.provider != self.name:
            return ""
        host = "" if ref.host == DEFAULT_GITHUB_HOST else ref.host
        return self._scope(RepoSpec(owner=ref.owner, repo=ref.repo, host=host))

    def _list_scope(self, spec: RepoSpec, out: Listing) -> None:
        """List one repository's issues and pull requests into ``out``.

        Each listing fails alone: a repository whose issues cannot be read still
        has its pull requests read, and vice versa. The repository counts as
        *polled* when at least one of its listings answered.
        """
        scope = self._scope(spec)
        answered = False
        if self.monitor_issues:
            answered = self._list_issues(spec, scope, out)
        if self.monitor_prs:
            try:
                prs = self.gh.list_labeled_prs(
                    spec.owner, spec.repo, self.label, host=spec.host
                )
            except GhError as exc:
                out.failures.append(ScopeFailure(scope, str(exc)))
            else:
                answered = True
                out.items.extend(self._work_item(spec, gh_item) for gh_item in prs)
        if answered:
            out.polled.append(scope)

    def _list_issues(self, spec: RepoSpec, scope: str, out: Listing) -> bool:
        """One repository's issues, under the disabled-Issues quarantine.

        Returns whether the listing answered. A repository whose Issues are off
        (``_ISSUES_DISABLED``) is reported ONCE, as a permanent failure, and
        then simply not asked for issues — it lands in ``skipped`` with the
        standing reason — until ``REPROBE_EVERY_CYCLES`` cycles have passed. A
        re-probe that still fails renews the skip silently; one that answers
        reports the repository in ``recovered`` and polls it normally again.
        Every other failure stays transient: reported every cycle, never
        quarantined.
        """
        since = self._issues_off.get(scope)
        if since is not None and self._cycles - since < REPROBE_EVERY_CYCLES:
            out.skipped.append(ScopeFailure(scope, _ISSUES_OFF_REASON, permanent=True))
            return False
        try:
            issues = self.gh.list_labeled_issues(
                spec.owner, spec.repo, self.label, host=spec.host
            )
        except GhError as exc:
            if _ISSUES_DISABLED not in str(exc).lower():
                out.failures.append(ScopeFailure(scope, str(exc)))
            elif since is None:  # first sighting: surfaced, then quarantined
                self._issues_off[scope] = self._cycles
                out.failures.append(ScopeFailure(scope, str(exc), permanent=True))
            else:  # a re-probe that still fails: renewed, not re-announced
                self._issues_off[scope] = self._cycles
                out.skipped.append(
                    ScopeFailure(scope, _ISSUES_OFF_REASON, permanent=True)
                )
            return False
        if since is not None:
            del self._issues_off[scope]
            out.recovered.append(scope)
        out.items.extend(self._work_item(spec, gh_item) for gh_item in issues)
        return True

    def list_comments(self, item: WorkItem) -> List[Comment]:
        gh_comments = self.gh.list_comments(
            item.owner,
            item.repo,
            item.number,
            is_pr=item.kind == _KIND_PR,
            host=item.host,
        )
        return [
            Comment(
                id=c.id,
                body=c.body,
                author=c.author,
                created_at=c.created_at,
                url=c.url,
                # Which surface it came from, and (for an inline comment) where
                # it is anchored — read back by `comment_event` below, and by
                # nothing else (issue-246).
                raw={
                    "kind": c.kind,
                    "state": c.state,
                    "path": c.path,
                    "line": c.line,
                },
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
        """The event GitHub itself would have delivered for this comment.

        One of three, by surface (issue-246) — ``issue_comment``,
        ``pull_request_review`` or ``pull_request_review_comment`` — because
        three existing readers branch on exactly those names and are already
        right for them: ``router.event_actor`` (who may be obeyed),
        ``router.event_body`` (the self-comment marker and the control keyword)
        and ``reactions.target_from_event``. Labelling every surface
        ``issue_comment`` would be the shorter edit and would break the first
        two: they would look for ``payload["comment"]`` in a review payload,
        find nothing, and resolve an actor-less event the dispatcher then
        refuses to take a command from.

        The item's own refs are reused, so a comment on a PR still reaches a
        session registered against the linked issue. ``labeled=False``: comments
        only feed existing sessions, never spawn (spawning is presence's job).
        """
        payload = self._item_payload(item)
        raw = comment.raw or {}
        kind = str(raw.get("kind") or _KIND_CONVERSATION)
        if kind == _KIND_REVIEW:
            payload["action"] = "submitted"
            payload["review"] = {
                "id": comment.id,
                "body": comment.body,
                "html_url": comment.url,
                "submitted_at": comment.created_at,
                # Carried as context only. Whether an approval should itself
                # advance anything is a product question about approvals, not
                # this parity fix — nothing acts on it.
                "state": str(raw.get("state") or ""),
                "user": {"login": comment.author},
            }
            event = "pull_request_review"
        else:
            body: dict = {}
            if kind == _KIND_REVIEW_THREAD:
                # Anchor first: the payload excerpt is truncated from the end,
                # so a long body must not be able to push the file and line
                # (which are what make the comment actionable) out of it.
                body["path"] = str(raw.get("path") or "")
                body["line"] = raw.get("line")
            body.update(
                {
                    "id": comment.id,
                    "body": comment.body,
                    "html_url": comment.url,
                    "created_at": comment.created_at,
                    "user": {"login": comment.author},
                }
            )
            payload["action"] = "created"
            payload["comment"] = body
            event = (
                "pull_request_review_comment"
                if kind == _KIND_REVIEW_THREAD
                else "issue_comment"
            )
        return RoutedEvent(
            event=event,
            action=str(payload["action"]),
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
        # Host too (issue-311, R5.3): an enterprise source must not claim the
        # github.com repository that happens to share its owner/repo.
        full_name = f"{ref.owner}/{ref.repo}".lower()
        return any(
            spec.full_name.lower() == full_name
            and (spec.host or DEFAULT_GITHUB_HOST) == ref.host
            for spec in self.repos
        )

    def closure(self, ref: WorkItemRef) -> Optional[Closure]:
        """Whether ``ref`` has ended, and how (``None`` while it is still open)."""
        state = self.gh.fetch_item_state(ref.owner, ref.repo, ref.number, host=ref.host)
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
