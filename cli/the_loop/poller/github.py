"""GitHub poll provider: the GitHub :class:`PollProvider`, over the daemon's client.

This is the *only* place in the polling stack that knows about GitHub. The
poller core (``poller.py``) speaks the provider-agnostic contract in
``base.py``; GitHub is reached solely because a ``polling.sources`` config entry
selects ``provider: github``.

Polling reads GitHub through :class:`~the_loop.ghapi.GitHubClient` (issue-442,
decision-139) — PyGithub under one token the CLI config names
(``integrations.github.api.tokenEnv``) — so the poller needs no ``gh`` binary and
no interactive login on the box. The token's presence is verified up front
(mirrors the tmux/ttyd preflight in ``runner.check_dependencies``), and every
read the client cannot make is a :class:`GhError`, the provider's own failure
type, so the core's per-scope isolation (issue-315) is unchanged.

The client is injectable so tests drive the provider with canned items instead
of a network. The provider maps the client's shapes onto the neutral
:class:`WorkItem`/:class:`Comment` and builds the shared ``RoutedEvent`` the
dispatcher already consumes.

Spec: docs/specs/issue-34/design.md §2; docs/specs/issue-442/design.md §4.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from .. import eventlog

from ..ghapi import (  # noqa: F401 — re-exported for the poller package
    KIND_CONVERSATION,
    KIND_REVIEW,
    KIND_REVIEW_THREAD,
    GhComment,
    GhItem,
    GhItemState,
    GitHubApiConfig,
    GitHubApiError,
    GitHubClient,
)
from ..sessions import DEFAULT_GITHUB_HOST, WorkItemRef, is_github_host
from ..webhook.router import (
    POLL_CLOSURE_DELIVERY_PREFIX,
    RoutedEvent,
    event_carries_labels,
    JiraLinkage,
    extract_work_items,
    normalize_labels,
)
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

_T = TypeVar("_T")

# Item kinds this provider emits (provider-local vocabulary).
_KIND_ISSUE = "issue"
_KIND_PR = "pull-request"

# The three surfaces a pull request carries instructions on (issue-246). GitHub
# files them under three different objects; the client reads all three and the
# provider builds, per surface, the event GitHub itself would have delivered.
_KIND_CONVERSATION = KIND_CONVERSATION
_KIND_REVIEW = KIND_REVIEW
_KIND_REVIEW_THREAD = KIND_REVIEW_THREAD

#: How long one poll read may take (seconds) — the client's per-request bound.
READ_TIMEOUT = 60.0

# What GitHub says about a repository whose Issues are turned off — the ONE
# condition this provider classifies as permanent (issue-315). It is
# configuration drift, not a fault: retrying it every cycle can only fail the
# same way, and it used to take the whole source down with it. The client
# raises it as a 410 carrying GitHub's REST sentence; both the status and the
# words are matched (belt and braces), so a rewording degrades to transient —
# retried, isolated, visible — never to silence.
_ISSUES_DISABLED = "issues are disabled"
_ISSUES_DISABLED_STATUS = 410
_ISSUES_OFF_REASON = (
    "issues are disabled on this repository; its issues are skipped and "
    f"re-probed every {REPROBE_EVERY_CYCLES} cycles, its pull requests are "
    "still polled"
)


class GhError(ProviderError):
    """A GitHub read failed (an HTTP error, a transport failure, no token).

    ``status`` is the HTTP status when GitHub answered one, else ``None``.
    """

    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


def check_github_credentials(api: Optional[GitHubApiConfig] = None) -> List[str]:
    """Missing-dependency messages for the GitHub token (empty when set)."""
    api = api or GitHubApiConfig()
    if api.token():
        return []
    return [
        f"missing credential: {api.missing_token_reason} — the daemon reads GitHub "
        "with a token now (issue-442); a fine-grained token needs Issues: read and "
        "write, Pull requests: read, Metadata: read on every polled repository"
    ]


def _read(what: str, fn: Callable[[], _T]) -> _T:
    """Run one client call, re-raising its failure as the provider's :class:`GhError`."""
    try:
        return fn()
    except GitHubApiError as exc:
        raise GhError(f"{what}: {exc}", status=exc.status) from None


@dataclass
class RepoSpec:
    """A ``[host/]owner/repo`` target parsed from config/flags.

    ``host`` is ``""`` for github.com (issue-311): ``full_name`` stays the
    ``owner/repo`` a webhook payload's ``repository.full_name`` carries, and
    ``gh_repo`` is ``gh``'s own ``--repo`` grammar with the host written exactly
    when it is not the default.

    A bare ``owner/repo`` takes the *resolved* default host when it is parsed
    (issue-331): the one the daemon resolves through ``ghhost.github_host``
    from the CLI config and ``$GH_HOST``. Decided once here, so
    the ``--repo`` argument, the scope name and :meth:`GitHubPollProvider.owns`
    cannot disagree about where a bare repository is — which they did when
    ``""`` meant github.com to ``owns()`` and "wherever ``gh`` points" to the
    listing.
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
    def parse(cls, value: str, default_host: str = "") -> "RepoSpec":
        """``[HOST/]OWNER/REPO``; a bare entry is on ``default_host`` (issue-331).

        A written host wins over the default. Either way the host then passes
        the one normalisation (github.com stays unwritten) and the one grammar
        (:func:`is_github_host`), so an inherited host that is not a host fails
        the entry here rather than reaching a ``--repo`` argument.
        """
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
        if not host and default_host:
            host = str(default_host).strip()
            if not is_github_host(host):
                raise ValueError(
                    f"invalid repo {value!r}: its default host {host!r} is not the "
                    "shape of a host (a dotted name or one with a port)"
                )
        if host == DEFAULT_GITHUB_HOST:
            host = ""
        return cls(owner=owner, repo=repo, host=host)


def parse_repos(values: Sequence[str], default_host: str = "") -> List[RepoSpec]:
    """Parse ``[host/]owner/repo`` strings, de-duplicated in order.

    ``default_host`` is what a bare entry is on (issue-331); the resolved host,
    ``github.com`` included, which :meth:`RepoSpec.parse` keeps unwritten.
    """
    seen = set()
    specs: List[RepoSpec] = []
    for value in values:
        spec = RepoSpec.parse(value, default_host=default_host)
        if spec.gh_repo not in seen:
            seen.add(spec.gh_repo)
            specs.append(spec)
    return specs


@register_provider
class GitHubPollProvider(PollProvider):
    """GitHub implementation of the poll-provider contract.

    Discovers labelled issues/PRs through the daemon's GitHub client, and maps
    them onto the neutral ``WorkItem``/``Comment`` and the shared ``RoutedEvent``
    shape. All GitHub payload synthesis lives here so the poller core stays
    provider-agnostic.
    """

    name = "github"

    def __init__(
        self,
        repos: List[RepoSpec],
        labels: Sequence[str],
        monitor_issues: bool = True,
        monitor_prs: bool = True,
        api: Optional[GitHubClient] = None,
    ):
        self.repos = repos
        # Every one of these must be on an item for this source to track it
        # (issue-381); an empty list lists and tracks nothing.
        self.labels = normalize_labels(labels)
        self.monitor_issues = monitor_issues
        self.monitor_prs = monitor_prs
        # The client (issue-442): one HTTP session per host for the whole
        # provider, bounded by the poll read timeout.
        self.api = api or GitHubClient(GitHubApiConfig(), timeout=READ_TIMEOUT)
        # Repositories whose Issues are off (issue-315): scope -> the cycle the
        # condition was last seen. In memory on purpose — a hot reload rebuilds
        # the provider and a restart starts fresh, and both are exactly the
        # moments an operator who just re-enabled Issues wants a re-probe.
        self._issues_off: Dict[str, int] = {}
        self._cycles = 0
        #: The missing labels last reported per filtered item, so a filtered item
        #: is logged once per change rather than on every poll cycle.
        self._filtered: Dict[Tuple[str, int], Tuple[str, ...]] = {}
        #: PR → Jira linkage (issue-475, design §C9). Attached by the poll
        #: daemon, which holds the config and the registry; ``None`` links no
        #: Jira key.
        self.jira_linkage: Optional[JiraLinkage] = None

    @classmethod
    def from_source(
        cls,
        source: dict,
        *,
        default_labels: Sequence[str],
        default_host: str = "",
        repositories: Sequence[str] = (),
        api: Optional[GitHubApiConfig] = None,
        config: Optional[Mapping[str, Any]] = None,
    ) -> "GitHubPollProvider":
        """The source says *how* to poll; ``repositories`` says *what* (issue-348);
        ``api`` says where the token is (issue-442, `integrations.github.api`).

        A source that still carries its own ``repos`` is refused rather than read:
        the config gate (``migrations.assert_current``) stops a daemon long before
        here, so reaching this point means a hand-built mapping — and honouring a
        list the operator wrote in the retired place would poll a set nothing else
        in this instance is bounded by.
        """
        source = source or {}
        if "repos" in source:
            raise ProviderError(
                "a github polling source still declares `repos`. The repositories "
                "this instance works with are declared once, at the top level "
                "(`repositories`), and read by every ingress — the receiver included "
                "(issue-348). It is NOT being ignored: polling a different set from "
                "the one that bounds your webhook receiver is the drift this key was "
                "removed to end. Run `/the-loop:upgrade-the-loop` to migrate."
            )
        monitor = source.get("monitor") or {}
        return cls(
            repos=parse_repos(
                [str(r) for r in repositories], default_host=default_host
            ),
            # The source's own list replaces the routing list; an empty or
            # absent one reuses it (issue-381).
            labels=normalize_labels(source.get("labels")) or list(default_labels),
            monitor_issues=bool(monitor.get("issues", True)),
            monitor_prs=bool(monitor.get("pullRequests", True)),
            api=GitHubClient(api or GitHubApiConfig(), timeout=READ_TIMEOUT),
        )

    def describe(self) -> str:
        # `gh_repo`, so the startup and reload lines say which GitHub each
        # repository was bound to (issue-331) — unchanged for github.com.
        return f"github {', '.join(s.gh_repo for s in self.repos) or '(no repos)'}"

    def check_dependencies(self) -> List[str]:
        return check_github_credentials(self.api.config)

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
                "this instance declares no repositories — set the top-level "
                "`repositories` ([HOST/]OWNER/REPO) in the CLI config; it is the "
                "one list every ingress reads (issue-348)"
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
                prs = _read(
                    f"pull requests of {spec.gh_repo}",
                    lambda: self.api.list_labeled_prs(
                        spec.owner, spec.repo, self.labels, host=spec.host
                    ),
                )
            except GhError as exc:
                out.failures.append(ScopeFailure(scope, str(exc)))
            else:
                answered = True
                out.items.extend(
                    self._work_item(spec, gh_item)
                    for gh_item in prs
                    if self._carries_every_label(gh_item, spec)
                )
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
            issues = _read(
                f"issues of {spec.gh_repo}",
                lambda: self.api.list_labeled_issues(
                    spec.owner, spec.repo, self.labels, host=spec.host
                ),
            )
        except GhError as exc:
            if not self._issues_disabled(exc):
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
        out.items.extend(
            self._work_item(spec, gh_item)
            for gh_item in issues
            if self._carries_every_label(gh_item, spec)
        )
        return True

    @staticmethod
    def _issues_disabled(exc: GhError) -> bool:
        """GitHub's *Issues are disabled* — by status or by its words (issue-315)."""
        return (
            exc.status == _ISSUES_DISABLED_STATUS
            or _ISSUES_DISABLED in str(exc).lower()
        )

    def _carries_every_label(
        self, gh_item: GhItem, spec: Optional[RepoSpec] = None
    ) -> bool:
        """Whether a listed item carries every configured label (issue-381, R2.1).

        GitHub is asked for items carrying all of them, and its filter answers
        that way — but the tracking decision is this provider's, so it is taken
        on the labels the listing actually returned, not on the filter's
        semantics. An empty list keeps nothing, as the gate arms nothing.
        """
        accepted = bool(self.labels) and set(self.labels) <= set(gh_item.labels)
        key = (spec.gh_repo if spec else "", gh_item.number)
        if accepted:
            self._filtered.pop(key, None)
            return True
        missing = sorted(set(self.labels) - set(gh_item.labels))
        if self._filtered.get(key) != tuple(missing):
            self._filtered[key] = tuple(missing)
            logger.info(
                "filtered GitHub item %s: missing required labels %s",
                gh_item.number,
                missing,
            )
            eventlog.emit(
                "poll.item_filtered",
                work_item=f"github:{spec.gh_repo}#{gh_item.number}" if spec else None,
                item_number=gh_item.number,
                required_labels=self.labels,
                missing_labels=missing,
                reason="missing-required-labels" if self.labels else "no-arming-labels",
            )
        return accepted

    def list_comments(self, item: WorkItem) -> List[Comment]:
        gh_comments = _read(
            f"comments of {item.ref}",
            lambda: self.api.list_comments(
                item.owner,
                item.repo,
                item.number,
                is_pr=item.kind == _KIND_PR,
                host=item.host,
            ),
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
        return extract_work_items(
            self._event_name(item), self._item_payload(item), self.jira_linkage
        )

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
            labeled=event_carries_labels(payload, self.labels),
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

    # -- CI (issue-462) ----------------------------------------------------------

    def ci_events(
        self, item: WorkItem, refs: List[WorkItemRef]
    ) -> List[Tuple[str, str, RoutedEvent]]:
        """The completed checks on a pull request's head, as the webhook events
        GitHub would have pushed for them: a ``check_run`` per check run, a
        ``status`` per commit status — so the dispatcher's CI gate judges a
        polled result by the same rule as a pushed one.

        Three reads: the pull request (for its head), its check runs, its combined
        status. A check still running is left out: it says nothing the gate acts
        on, and its completion is what the next pass will see.
        """
        if item.kind != _KIND_PR:
            return []
        host = item.host
        pull = _read(
            f"pull request {item.ref}",
            lambda: self.api.get_pull(item.owner, item.repo, item.number, host=host),
        )
        sha = str((pull.get("head") or {}).get("sha") or "")
        if not sha:
            return []
        runs, statuses = _read(
            f"checks of {item.ref}",
            lambda: self.api.commit_checks(item.owner, item.repo, sha, host=host),
        )
        repository = {
            "full_name": f"{item.owner}/{item.repo}",
            "html_url": f"https://{host}/{item.owner}/{item.repo}",
        }
        out: List[Tuple[str, str, RoutedEvent]] = []
        for run in runs:
            name = str(run.get("name") or "")
            if not name or run.get("status") != "completed":
                continue
            conclusion = str(run.get("conclusion") or "")
            payload = {
                "action": "completed",
                "check_run": {
                    "id": run.get("id"),
                    "name": name,
                    "status": "completed",
                    "conclusion": conclusion,
                    "head_sha": sha,
                    "html_url": run.get("html_url") or "",
                    "details_url": run.get("details_url") or "",
                    "app": run.get("app") or {},
                    "output": run.get("output") or {},
                    "pull_requests": [{"number": item.number}],
                },
                "repository": repository,
            }
            out.append(
                self._ci_event(
                    item,
                    refs,
                    f"check-run:{name}",
                    sha,
                    conclusion,
                    "check_run",
                    payload,
                )
            )
        for status in statuses:
            context = str(status.get("context") or "")
            state = str(status.get("state") or "")
            if not context or state == "pending":
                continue
            payload = {
                "state": state,
                "context": context,
                "sha": sha,
                "description": status.get("description") or "",
                "target_url": status.get("target_url") or "",
                "repository": repository,
            }
            out.append(
                self._ci_event(
                    item, refs, f"status:{context}", sha, state, "status", payload
                )
            )
        return out

    @staticmethod
    def _ci_event(
        item: WorkItem,
        refs: List[WorkItemRef],
        check: str,
        sha: str,
        conclusion: str,
        event: str,
        payload: dict,
    ) -> Tuple[str, str, RoutedEvent]:
        value = f"{sha}:{conclusion}"
        return (
            check,
            value,
            RoutedEvent(
                event=event,
                action=str(payload.get("action") or ""),
                # Stable per (item, check, result), so a repeat inside the dedup
                # window is a no-op even before the ledger is consulted.
                delivery_id=f"poll-ci-{item.ref}-{check}-{value}",
                work_items=list(refs),
                payload=payload,
                labeled=False,
            ),
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
        state = _read(
            f"state of {ref.ref}",
            lambda: self.api.item_state(ref.owner, ref.repo, ref.number, host=ref.host),
        )
        if state.open or not state.state:
            return None
        return Closure(
            state="merged" if state.merged else "closed",
            kind=_KIND_PR if state.is_pr else _KIND_ISSUE,
            title=state.title,
            url=state.url,
            actor=state.closed_by,
            reason=state.state_reason,
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
        # The closer, as GitHub records it (issue-329): the same `sender` a
        # webhook carries, so the dispatcher's cleanup gate judges a polled
        # closure by the same rule. Absent when GitHub names nobody, so that
        # payload stays byte-identical to the pre-issue-329 one.
        if closure.actor:
            payload["sender"] = {"login": closure.actor}
        if closure.kind == _KIND_PR:
            event = "pull_request"
            entity["merged"] = closure.merged
            payload["pull_request"] = entity
        else:
            event = "issues"
            # The webhook's own field (issue-452), and absent when GitHub gave
            # none, as `sender` is.
            if closure.reason:
                entity["state_reason"] = closure.reason
            payload["issue"] = entity
        return RoutedEvent(
            event=event,
            action="closed",
            delivery_id=f"{POLL_CLOSURE_DELIVERY_PREFIX}{ref.ref}-{closure.state}",
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
