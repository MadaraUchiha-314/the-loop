"""The daemon's one GitHub client — PyGithub, one token, twelve operations (issue-442).

Every GitHub read and write a process of the-loop's makes goes through this
module. Before it, eleven modules composed a ``gh`` argv each: the comment
writers, the existence check, the reactions, the announcement, the
self-diagnosis issue, the ledger, the poller's whole read side, the graph's
``cli`` transport. A ``gh`` binary is not a Python dependency and its login is
interactive, which is what made the-loop hard to deploy; a Python wheel can carry
`PyGithub <https://github.com/pygithub/pygithub/>`_ and a token can arrive in the
environment, so that is the shape now (decision-139).

Three properties every caller relies on:

* **The credential is the token the configuration names.** ``GitHubApiConfig``
  reads ``integrations.github.api.tokenEnv`` (default ``GH_TOKEN``, then
  ``GITHUB_TOKEN``) and the token itself comes from the process environment at
  call time — the source the attachment fetch and ``env.file`` (issue-318)
  already use. No ``gh auth token``, no keychain, no file of the-loop's own. A
  missing token is :class:`GitHubApiError` with ``missing_token`` set, and the
  message names the variables (R2.3).
* **One exception type.** PyGithub's :class:`~github.GithubException`, a
  transport error from ``requests`` and a malformed GraphQL document all become
  :class:`GitHubApiError` here, carrying the HTTP status (``None`` for a
  transport failure) and GitHub's own message — never the token. No caller
  imports PyGithub.
* **The host is the ref's.** Every method takes ``host`` (``""`` for github.com),
  and one :class:`~github.MainClass.Github` is kept per ``(host, token)``,
  addressed at ``https://<host>/api/v3`` unless the operator configured a
  ``baseUrl`` (issue-311, R3.3). A host reaches a base URL only after
  :func:`~the_loop.sessions.is_github_host`.

What goes over REST and what over GraphQL is decided per operation (design § 2):
typed PyGithub objects for the writes (a lazy ``Issue`` is one ``POST``); raw
REST pages for the reads whose shapes the poller already parses (reviews, review
comments, the issues document); PyGithub's ``graphql_query`` for the three things
``gh`` itself did over GraphQL — the two listings (``closingIssuesReferences`` has
no REST form) and the conversation comments (whose ids must stay node ids so no
operator's baselined thread is re-forwarded on upgrade, issue-246) — and for a
reaction on a node id.

The client never sleeps for a rate limit: the ``Github`` is built with a
connection-level ``retry=2`` and the caller's timeout, not PyGithub's default
``GithubRetry``, which parks a thread until the window resets (R5.1, A5).
"""

from __future__ import annotations

import logging
import os
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from .ghhost import PUBLIC_API_BASE, api_base_for
from .sessions import DEFAULT_GITHUB_HOST, is_github_host, is_github_name

logger = logging.getLogger("the-loop.ghapi")

__all__ = [
    "DEFAULT_TOKEN_ENVS",
    "GhComment",
    "GhItem",
    "GhItemState",
    "GitHubApiConfig",
    "GitHubApiError",
    "GitHubClient",
    "KIND_CONVERSATION",
    "KIND_REVIEW",
    "KIND_REVIEW_THREAD",
    "MERGE_METHODS",
    "REACTION_CONTENTS",
    "REACTION_KINDS",
    "is_branch_name",
]

#: The variables a token is read from when the config names none, in order.
DEFAULT_TOKEN_ENVS: Tuple[str, ...] = ("GH_TOKEN", "GITHUB_TOKEN")

#: Upper bound on items fetched per repository per kind (the poller's cap).
LIST_LIMIT = 200

#: Page size for every paged read. GraphQL and REST both accept 100.
PAGE_SIZE = 100

#: The three surfaces a pull request carries instructions on (issue-246).
KIND_CONVERSATION = "conversation"  # IssueComment (IC_)
KIND_REVIEW = "review"  # PullRequestReview (PRR_) — a review body
KIND_REVIEW_THREAD = "review-thread"  # PullRequestReviewComment (PRRC_) — inline

#: A review a human has written but not submitted — visible only to its author.
_REVIEW_PENDING = "PENDING"

#: GitHub's fixed reaction palette: REST ``content`` value -> GraphQL
#: ``ReactionContent`` enum member. The config accepts exactly these names.
REACTION_CONTENTS: Dict[str, str] = {
    "+1": "THUMBS_UP",
    "-1": "THUMBS_DOWN",
    "laugh": "LAUGH",
    "confused": "CONFUSED",
    "heart": "HEART",
    "hooray": "HOORAY",
    "rocket": "ROCKET",
    "eyes": "EYES",
}

#: The REST reaction targets: an issue or pull request, an issue (conversation)
#: comment, an inline review comment — the three endpoints ``gh api`` was given.
REACTION_KINDS: Tuple[str, ...] = ("issue", "issue-comment", "review-comment")

_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_=+/-]+$")

#: A branch name the harness verbs accept (issue-447, A3): a conservative subset of
#: git's ref grammar — no whitespace, no `..`, no leading `-` or `/`, no `@{`,
#: nothing a query string or a JSON body would have to escape.
_BRANCH_RE = re.compile(r"^(?![-/])(?!.*\.\.)(?!.*//)[A-Za-z0-9._/-]{1,255}(?<![./])$")

#: A commit SHA, abbreviated or full.
_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")

#: The three ways GitHub merges a pull request (``PUT …/pulls/{n}/merge``).
MERGE_METHODS: Tuple[str, ...] = ("merge", "squash", "rebase")

# A pull request's review threads, resolved or not — the one thing about a review
# REST cannot say (issue-447). Values travel as variables, never as query text.
_REVIEW_THREADS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      reviewThreads(first: $first, after: $after) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id isResolved isOutdated path line
          comments(first: 100) {
            nodes { id body createdAt url author { login } }
          }
        }
      }
    }
  }
}
"""

_ADD_REACTION_MUTATION = (
    "mutation($subjectId: ID!, $content: ReactionContent!) "
    "{ addReaction(input: {subjectId: $subjectId, content: $content}) "
    "{ clientMutationId } }"
)

# The two listings and the conversation read, as GraphQL — the queries `gh issue
# list --json`, `gh pr list --json` and `gh issue/pr view --json comments` ran, so
# every shape the poller parses (`updatedAt`, `url`, `author.login`, node ids)
# is what it always was. `hasIssuesEnabled` is the issues-disabled signal
# (issue-315). Values travel as variables, never as query text (A6).
_ISSUES_QUERY = """
query($owner: String!, $name: String!, $labels: [String!], $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    hasIssuesEnabled
    issues(states: OPEN, labels: $labels, first: $first, after: $after,
           orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title updatedAt url
        author { login }
        labels(first: 100) { nodes { name } }
      }
    }
  }
}
"""

_PULLS_QUERY = """
query($owner: String!, $name: String!, $labels: [String!], $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(states: OPEN, labels: $labels, first: $first, after: $after,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title updatedAt url headRefName body
        author { login }
        labels(first: 100) { nodes { name } }
        closingIssuesReferences(first: 50) { nodes { number } }
      }
    }
  }
}
"""

_COMMENTS_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $first: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    issueOrPullRequest(number: $number) {
      ... on Issue {
        comments(first: $first, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes { id body createdAt url author { login } }
        }
      }
      ... on PullRequest {
        comments(first: $first, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes { id body createdAt url author { login } }
        }
      }
    }
  }
}
"""

#: What GitHub says about a repository whose Issues are turned off, in the REST
#: answer (410) and in this module's own rendering of ``hasIssuesEnabled: false``.
ISSUES_DISABLED_MESSAGE = "Issues are disabled for this repo"


def is_branch_name(value: str) -> bool:
    """Whether ``value`` is a branch name the harness verbs may send (A3)."""
    return bool(value) and bool(_BRANCH_RE.match(value)) and "@{" not in value


# ----------------------------------------------------------------- data shapes


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
    kind: str = KIND_CONVERSATION
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
    #: ``closed_by.login`` — who closed the item, or "" (issue-329).
    closed_by: str = ""

    @property
    def open(self) -> bool:
        return self.state == "open"


@dataclass(frozen=True)
class GhItem:
    """A labelled issue or PR returned by a listing."""

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


# ---------------------------------------------------------------- the config


@dataclass(frozen=True)
class GitHubApiConfig:
    """Mirror of ``integrations.github.api`` — where the token is, and the base.

    ``token_envs`` are variable **names**; the token is never a config value.
    ``base_url`` is the operator's API base when set to something other than the
    public API (an enterprise ``https://<host>/api/v3``), else the public base —
    and then a ref's own host derives its base (:func:`ghhost.api_base_for`).
    Frozen and hashable: it is the key of the process-wide client cache and sits
    on frozen config dataclasses.
    """

    token_envs: Tuple[str, ...] = DEFAULT_TOKEN_ENVS
    base_url: str = PUBLIC_API_BASE

    @classmethod
    def from_cli_config(cls, config: Optional[Mapping[str, Any]]) -> "GitHubApiConfig":
        """``integrations.github.api`` of a CLI config document (absent = defaults)."""
        github = ((dict(config or {}).get("integrations") or {}).get("github")) or {}
        api = github.get("api") if isinstance(github, Mapping) else None
        return cls.from_mapping(api if isinstance(api, Mapping) else {})

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "GitHubApiConfig":
        """The ``api`` block, or the private ``_github`` fan-out key (same keys)."""
        data = data or {}
        raw = data.get("tokenEnv")
        if isinstance(raw, str):
            names: Tuple[str, ...] = (raw,)
        elif isinstance(raw, (list, tuple)):
            names = tuple(str(n) for n in raw if str(n).strip())
        else:
            names = ()
        base = str(data.get("baseUrl") or "").strip().rstrip("/")
        return cls(
            token_envs=names or DEFAULT_TOKEN_ENVS, base_url=base or PUBLIC_API_BASE
        )

    def to_mapping(self) -> Dict[str, Any]:
        return {"tokenEnv": list(self.token_envs), "baseUrl": self.base_url}

    def token(self, env: Optional[Mapping[str, str]] = None) -> str:
        """The first set variable's value, or ``""``. Read at call time."""
        environ: Mapping[str, str] = os.environ if env is None else env
        for name in self.token_envs:
            value = environ.get(name) or ""
            if value.strip():
                return value.strip()
        return ""

    @property
    def missing_token_reason(self) -> str:
        """The one sentence every writer, pre-flight and refusal says (R2.3)."""
        return "no GitHub token: set " + " or ".join(self.token_envs)

    def base_for(self, host: str) -> str:
        """The REST base a ref on ``host`` is addressed at (issue-311, R4.3).

        An explicit, non-public ``baseUrl`` is the operator's and is honoured
        verbatim (decision-042); against the public default, a hosted ref
        derives ``https://<host>/api/v3``.
        """
        if self.base_url and self.base_url != PUBLIC_API_BASE:
            return self.base_url
        return api_base_for(host)


# ----------------------------------------------------------------- the error


class GitHubApiError(Exception):
    """A GitHub call could not be made or was refused.

    ``status`` is the HTTP status GitHub answered (``None`` for a transport
    failure, a timeout or a missing token); ``message`` is GitHub's own message
    or the transport's; ``missing_token`` marks the one failure a deployment
    fixes by setting a variable. The text never carries the token.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        missing_token: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.status = status
        self.missing_token = missing_token

    @property
    def not_found(self) -> bool:
        return self.status == 404

    def __str__(self) -> str:
        if self.status is not None:
            return f"GitHub {self.status}: {self.message}"
        return self.message


# ---------------------------------------------------------------- the client


def _raw_row_class():
    """A page element kept as the dict GitHub sent.

    Handed to PyGithub's :class:`~github.PaginatedList.PaginatedList` as the
    content class, so its ``Link``-header pagination walks every page while the
    rows stay the raw documents the poller already parses — and no attribute
    access can trigger the per-object completion fetch a typed list element
    performs for a field its page did not carry. Built on PyGithub's own
    ``NonCompletableGithubObject`` (never fetches itself); defined lazily so the
    import cost is paid by the first paged read, not by every ``the-loop`` command.
    """
    from github.GithubObject import NonCompletableGithubObject

    class _RawRow(NonCompletableGithubObject):
        def _initAttributes(self) -> None:
            pass

        def _useAttributes(self, attributes: Dict[str, Any]) -> None:
            self.data: Dict[str, Any] = dict(attributes)

    return _RawRow


def _iso(value: Any) -> str:
    """An ISO-8601 ``Z`` string from what GitHub or PyGithub hands back."""
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value or "")


def _login(node: Any) -> str:
    return str((node or {}).get("login") or "") if isinstance(node, Mapping) else ""


class GitHubClient:
    """The twelve operations, on PyGithub, behind one seam.

    ``factory`` builds the :class:`~github.MainClass.Github` for a base URL and
    a token; tests inject one, or run the real one against PyGithub's own
    connection-injection hook. ``timeout`` bounds every request (seconds).
    """

    _shared: Dict[Tuple["GitHubApiConfig", float], "GitHubClient"] = {}
    _shared_lock = threading.Lock()

    def __init__(
        self,
        config: Optional[GitHubApiConfig] = None,
        *,
        timeout: float = 30.0,
        factory: Optional[Callable[..., Any]] = None,
    ):
        self.config = config or GitHubApiConfig()
        self.timeout = timeout
        self._factory = factory or self._build
        self._clients: Dict[Tuple[str, str], Any] = {}
        self._lock = threading.Lock()

    @classmethod
    def shared(
        cls, config: Optional[GitHubApiConfig] = None, *, timeout: float = 30.0
    ) -> "GitHubClient":
        """One client per ``(config, timeout)`` for the process — the writers
        that used to fork a ``gh`` per call now share one HTTP session per host."""
        key = (config or GitHubApiConfig(), float(timeout))
        with cls._shared_lock:
            client = cls._shared.get(key)
            if client is None:
                client = cls(key[0], timeout=key[1])
                cls._shared[key] = client
            return client

    # -- construction ------------------------------------------------------------

    def _build(self, base_url: str, token: str) -> Any:
        from github import Auth, Github

        return Github(
            auth=Auth.Token(token),
            base_url=base_url,
            timeout=max(1, int(self.timeout)),
            per_page=PAGE_SIZE,
            user_agent="the-loop",
            # Connection-level retries only (a dropped socket), never PyGithub's
            # `GithubRetry`, which sleeps until a rate-limit window resets (A5).
            retry=2,
            # No courtesy pause between requests: the volume is a handful a
            # minute, and a dispatch thread must not sleep inside a write.
            seconds_between_requests=None,
            seconds_between_writes=None,
        )

    def has_token(self) -> bool:
        return bool(self.config.token())

    def github(self, host: str = "") -> Any:
        """The :class:`Github` for ``host`` (``""`` = github.com), or raise.

        Cached per ``(host, token)`` so a rotated token builds a new one. A host
        that is not the shape of a host never reaches a base URL (A3).
        """
        host = "" if host == DEFAULT_GITHUB_HOST else str(host or "")
        if host and not is_github_host(host):
            raise GitHubApiError(f"{host!r} is not a GitHub host")
        token = self.config.token()
        if not token:
            raise GitHubApiError(self.config.missing_token_reason, missing_token=True)
        key = (host, token)
        with self._lock:
            client = self._clients.get(key)
            if client is None:
                # One token, one live Github per host: forget any built on an
                # earlier token for this host.
                for stale in [k for k in self._clients if k[0] == host]:
                    del self._clients[stale]
                client = self._factory(self.config.base_for(host), token)
                self._clients[key] = client
            return client

    def _requester(self, host: str = "") -> Any:
        return self.github(host).requester

    # -- the boundary ------------------------------------------------------------

    @staticmethod
    def _coordinates(owner: str, repo: str) -> Tuple[str, str]:
        """Refuse coordinates that are not GitHub names before they reach a URL (A2)."""
        if not (is_github_name(owner) and is_github_name(repo)):
            raise GitHubApiError(f"unusable repo coordinates {owner!r}/{repo!r}")
        return owner, repo

    @staticmethod
    def _number(value: Any, what: str = "number") -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            text = str(value)
            if not text.isdigit() or int(text) <= 0:
                raise GitHubApiError(f"unusable {what} {value!r}")
            return int(text)
        return value

    def _call(self, what: str, fn: Callable[[], Any]) -> Any:
        """Run one PyGithub call, translating every failure to :class:`GitHubApiError`."""
        try:
            return fn()
        except GitHubApiError:
            raise
        except Exception as exc:  # noqa: BLE001 — the one translation boundary
            raise self._translate(what, exc) from None

    @staticmethod
    def _translate(what: str, exc: BaseException) -> GitHubApiError:
        from github import GithubException

        if isinstance(exc, GithubException):
            data = exc.data if isinstance(exc.data, Mapping) else {}
            message = str(exc.message or data.get("message") or "").strip()
            errors = data.get("errors")
            if not message and isinstance(errors, list) and errors:
                first = errors[0]
                message = str(
                    (first.get("message") if isinstance(first, Mapping) else first)
                    or ""
                )
            if not message:
                message = exc.__class__.__name__
            logger.debug("%s failed: %s %s", what, exc.status, message)
            return GitHubApiError(message, status=int(exc.status or 0) or None)
        # requests' ConnectionError / Timeout, an AssertionError from a
        # malformed document, anything else: no status, the exception's text.
        text = str(exc).strip() or exc.__class__.__name__
        logger.debug("%s failed without a status: %s", what, text)
        return GitHubApiError(f"{what}: {text}")

    # -- lazy typed objects: one request per write ------------------------------
    #
    # `completed=False` is PyGithub's own idiom for an object built from a URL
    # that must NOT fetch itself: the write that follows is then the one request.

    def _issue(self, owner: str, repo: str, number: int, host: str) -> Any:
        from github.Issue import Issue

        return Issue(
            self._requester(host),
            url=f"/repos/{owner}/{repo}/issues/{number}",
            completed=False,
        )

    def _repo(self, owner: str, repo: str, host: str) -> Any:
        from github.Repository import Repository

        return Repository(
            self._requester(host), url=f"/repos/{owner}/{repo}", completed=False
        )

    @staticmethod
    def _branch(value: Any, what: str = "branch") -> str:
        text = str(value or "")
        if not is_branch_name(text):
            raise GitHubApiError(f"unusable {what} name {text!r}")
        return text

    @staticmethod
    def _sha(value: Any) -> str:
        text = str(value or "")
        if not _SHA_RE.match(text):
            raise GitHubApiError(f"unusable commit sha {text!r}")
        return text

    # -- writes ------------------------------------------------------------------

    def post_comment(
        self, owner: str, repo: str, number: int, body: str, host: str = ""
    ) -> str:
        """``POST /repos/{o}/{r}/issues/{n}/comments`` — the issues endpoint
        serves pull-request conversations too. Returns the comment's ``html_url``."""
        owner, repo = self._coordinates(owner, repo)
        number = self._number(number)
        issue = self._issue(owner, repo, number, host)
        comment = self._call("post comment", lambda: issue.create_comment(str(body)))
        return str(getattr(comment, "html_url", "") or "")

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Iterable[str] = (),
        host: str = "",
    ) -> Tuple[int, str]:
        """``POST /repos/{o}/{r}/issues`` with ``labels`` on the same request —
        GitHub drops them silently for a caller without triage rights, the
        documented degradation. Returns ``(number, html_url)``."""
        owner, repo = self._coordinates(owner, repo)
        names = [str(lbl) for lbl in labels if str(lbl).strip()]
        repository = self._repo(owner, repo, host)

        def _create():
            if names:
                return repository.create_issue(str(title), body=str(body), labels=names)
            return repository.create_issue(str(title), body=str(body))

        issue = self._call("create issue", _create)
        number = getattr(issue, "number", None)
        if not isinstance(number, int):
            raise GitHubApiError("GitHub returned no issue number")
        return number, str(getattr(issue, "html_url", "") or "")

    def add_reaction(
        self, owner: str, repo: str, kind: str, id: Any, content: str, host: str = ""
    ) -> None:
        """One ``POST …/reactions`` on an issue/PR, an issue comment or a review
        comment — the three REST targets a dispatch reaction can have."""
        owner, repo = self._coordinates(owner, repo)
        if content not in REACTION_CONTENTS:
            raise GitHubApiError(f"unknown reaction {content!r}")
        number = self._number(id, "id")
        requester = self._requester(host)
        if kind == "issue":
            target = self._issue(owner, repo, number, host)
        elif kind == "issue-comment":
            from github.IssueComment import IssueComment

            target = IssueComment(
                requester,
                url=f"/repos/{owner}/{repo}/issues/comments/{number}",
                completed=False,
            )
        elif kind == "review-comment":
            from github.PullRequestComment import PullRequestComment

            target = PullRequestComment(
                requester,
                url=f"/repos/{owner}/{repo}/pulls/comments/{number}",
                completed=False,
            )
        else:
            raise GitHubApiError(f"unknown reaction target kind {kind!r}")
        self._call(f"react on {kind}", lambda: target.create_reaction(content))

    def add_reaction_by_node(self, node_id: str, content: str, host: str = "") -> None:
        """GraphQL ``addReaction`` — for a target the payload names by node id only
        (a webhook comment's ``node_id``, a poll-path comment's ``id``)."""
        if not node_id or not _NODE_ID_RE.match(node_id):
            raise GitHubApiError(f"unusable node id {node_id!r}")
        if content not in REACTION_CONTENTS:
            raise GitHubApiError(f"unknown reaction {content!r}")
        self.graphql(
            _ADD_REACTION_MUTATION,
            {"subjectId": node_id, "content": REACTION_CONTENTS[content]},
            host=host,
        )

    def add_labels(
        self, owner: str, repo: str, number: int, labels: Iterable[str], host: str = ""
    ) -> None:
        """``POST /repos/{o}/{r}/issues/{n}/labels`` — adds, never replaces (O11)."""
        owner, repo = self._coordinates(owner, repo)
        names = [str(lbl) for lbl in labels if str(lbl).strip()]
        if not names:
            return
        issue = self._issue(owner, repo, self._number(number), host)
        self._call("add labels", lambda: issue.add_to_labels(*names))

    def ensure_label(
        self, owner: str, repo: str, name: str, color: str = "ededed", host: str = ""
    ) -> bool:
        """Create the repository label; ``True`` when created, ``False`` when it
        already existed (GitHub's 422 is success — the label is there)."""
        owner, repo = self._coordinates(owner, repo)
        repository = self._repo(owner, repo, host)
        try:
            self._call(
                "create label",
                lambda: repository.create_label(str(name), str(color or "ededed")),
            )
        except GitHubApiError as exc:
            if exc.status == 422:
                return False
            raise
        return True

    def remove_label(
        self, owner: str, repo: str, number: int, label: str, host: str = ""
    ) -> bool:
        """Take ONE label off an issue; ``False`` when it was not there (404 is
        success — it is absent, which is all the caller wanted)."""
        owner, repo = self._coordinates(owner, repo)
        issue = self._issue(owner, repo, self._number(number), host)
        try:
            self._call("remove label", lambda: issue.remove_from_labels(str(label)))
        except GitHubApiError as exc:
            if exc.not_found:
                return False
            raise
        return True

    # -- reads -------------------------------------------------------------------

    def rest(
        self,
        method: str,
        path: str,
        payload: Optional[Dict[str, Any]] = None,
        host: str = "",
    ) -> Any:
        """One REST call through PyGithub's requester; the parsed JSON body."""
        requester = self._requester(host)

        def _do():
            _headers, data = requester.requestJsonAndCheck(method, path, input=payload)
            # PyGithub stamps the request path onto a document that carries no
            # `url` of its own (so a typed object built from it could complete
            # itself). GitHub's real `url` is absolute, never the path; drop
            # the stamp so an empty answer still reads as empty.
            if isinstance(data, dict) and data.get("url") == path:
                data = {k: v for k, v in data.items() if k != "url"}
            return data

        return self._call(f"{method} {path}", _do)

    def rest_pages(
        self, path: str, params: Optional[Dict[str, Any]] = None, host: str = ""
    ) -> List[Dict[str, Any]]:
        """Every page of a REST array endpoint, as dicts — PyGithub's ``Link``
        pagination over raw rows (``--paginate``)."""
        from github.PaginatedList import PaginatedList

        requester = self._requester(host)
        query: Dict[str, Any] = {"per_page": PAGE_SIZE}
        query.update(params or {})
        row_class = _raw_row_class()

        def _walk():
            pages = PaginatedList(row_class, requester, path, query)
            return [row.data for row in pages if isinstance(row.data, dict)]

        return self._call(f"GET {path}", _walk)

    def graphql(
        self, query: str, variables: Dict[str, Any], host: str = ""
    ) -> Dict[str, Any]:
        """One GraphQL document through PyGithub's requester; the ``data`` object."""
        requester = self._requester(host)

        def _do():
            _headers, data = requester.graphql_query(query, variables)
            payload = data.get("data") if isinstance(data, Mapping) else None
            if not isinstance(payload, Mapping):
                raise AssertionError("GraphQL returned no data object")
            return dict(payload)

        return self._call("graphql", _do)

    def get_issue(self, owner: str, repo: str, number: int, host: str = "") -> Dict:
        """``GET /repos/{o}/{r}/issues/{n}`` — answers for issues **and** pull
        requests (a ref carries no kind). The raw document."""
        owner, repo = self._coordinates(owner, repo)
        data = self.rest(
            "GET", f"/repos/{owner}/{repo}/issues/{self._number(number)}", host=host
        )
        if not isinstance(data, dict) or not data:
            raise GitHubApiError(
                f"repos/{owner}/{repo}/issues/{number} returned no object"
            )
        return data

    def item_state(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> GhItemState:
        """The closure question (issue-94), off the one issues endpoint."""
        data = self.get_issue(owner, repo, number, host)
        pull_request = data.get("pull_request")
        return GhItemState(
            number=int(data.get("number") or number),
            state=str(data.get("state") or ""),
            is_pr=isinstance(pull_request, dict),
            merged=bool((pull_request or {}).get("merged_at")),
            title=str(data.get("title") or ""),
            url=str(data.get("html_url") or ""),
            closed_by=_login(data.get("closed_by")),
        )

    def labels_of(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[str]:
        """The label names an issue/PR carries right now."""
        owner, repo = self._coordinates(owner, repo)
        rows = self.rest_pages(
            f"/repos/{owner}/{repo}/issues/{self._number(number)}/labels", host=host
        )
        return [str(row.get("name")) for row in rows if row.get("name")]

    def viewer_login(self, host: str = "") -> str:
        """The login the token belongs to — the author of every comment the-loop
        wrote (O5). ``""`` when unreadable; callers fail closed on that."""
        try:
            gh = self.github(host)
            return str(self._call("read login", lambda: gh.get_user().login) or "")
        except GitHubApiError as exc:
            logger.debug("could not read the GitHub login: %s", exc)
            return ""

    def list_labeled_issues(
        self, owner: str, repo: str, labels: Sequence[str], host: str = ""
    ) -> List[GhItem]:
        """Open issues in ``owner/repo`` carrying every label (PRs excluded),
        newest-updated first, capped at :data:`LIST_LIMIT`.

        A repository whose Issues are off answers ``hasIssuesEnabled: false``;
        that is raised as a ``410`` carrying GitHub's own REST sentence, so the
        poller classifies it exactly as before (issue-315).
        """
        owner, repo = self._coordinates(owner, repo)
        items: List[GhItem] = []
        # No labels means no filter (what a listing without `--label` did); the
        # provider keeps nothing from it either way (issue-381).
        for repository, page in self._graphql_pages(
            _ISSUES_QUERY, owner, repo, "issues", {"labels": list(labels) or None}, host
        ):
            if repository.get("hasIssuesEnabled") is False:
                raise GitHubApiError(ISSUES_DISABLED_MESSAGE, status=410)
            for node in page:
                items.append(self._item_from_node(node, is_pr=False))
                if len(items) >= LIST_LIMIT:
                    return items
        return items

    def list_labeled_prs(
        self, owner: str, repo: str, labels: Sequence[str], host: str = ""
    ) -> List[GhItem]:
        """Open PRs carrying every label, with head branch, body and GitHub's
        own linked issues (``closingIssuesReferences``, issue-93)."""
        owner, repo = self._coordinates(owner, repo)
        items: List[GhItem] = []
        for _repository, page in self._graphql_pages(
            _PULLS_QUERY,
            owner,
            repo,
            "pullRequests",
            {"labels": list(labels) or None},
            host,
        ):
            for node in page:
                items.append(self._item_from_node(node, is_pr=True))
                if len(items) >= LIST_LIMIT:
                    return items
        return items

    def list_issue_comments(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[GhComment]:
        """Every conversation comment on an issue or pull request, ids as GraphQL
        node ids (what ``gh … view --json comments`` returned, issue-246)."""
        owner, repo = self._coordinates(owner, repo)
        number = self._number(number)
        comments: List[GhComment] = []
        after: Optional[str] = None
        while True:
            data = self.graphql(
                _COMMENTS_QUERY,
                {
                    "owner": owner,
                    "name": repo,
                    "number": number,
                    "first": PAGE_SIZE,
                    "after": after,
                },
                host=host,
            )
            thread = (data.get("repository") or {}).get("issueOrPullRequest")
            if not isinstance(thread, Mapping):
                raise GitHubApiError(
                    f"{owner}/{repo}#{number} is not an issue or pull request",
                    status=404,
                )
            connection = thread.get("comments") or {}
            for node in connection.get("nodes") or []:
                if isinstance(node, Mapping):
                    comments.append(self._comment_from_node(node))
            info = connection.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                return comments
            after = str(info["endCursor"])

    def list_reviews(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[GhComment]:
        """Submitted PR reviews that carry an instruction (issue-246): a review
        with an empty body and a PENDING draft are dropped here."""
        owner, repo = self._coordinates(owner, repo)
        reviews: List[GhComment] = []
        for row in self.rest_pages(
            f"/repos/{owner}/{repo}/pulls/{self._number(number)}/reviews", host=host
        ):
            state = str(row.get("state") or "").upper()
            body = str(row.get("body") or "")
            if state == _REVIEW_PENDING or not body.strip():
                continue
            reviews.append(
                GhComment(
                    id=str(row.get("node_id") or ""),
                    body=body,
                    author=_login(row.get("user")),
                    created_at=_iso(row.get("submitted_at")),
                    url=str(row.get("html_url") or ""),
                    kind=KIND_REVIEW,
                    state=state,
                )
            )
        return reviews

    def list_review_comments(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[GhComment]:
        """Inline review-thread comments, each with the file/line it is on
        (``original_line`` when the diff has moved past it)."""
        owner, repo = self._coordinates(owner, repo)
        inline: List[GhComment] = []
        for row in self.rest_pages(
            f"/repos/{owner}/{repo}/pulls/{self._number(number)}/comments", host=host
        ):
            line = row.get("line")
            if not isinstance(line, int):
                line = row.get("original_line")
            inline.append(
                GhComment(
                    id=str(row.get("node_id") or ""),
                    body=str(row.get("body") or ""),
                    author=_login(row.get("user")),
                    created_at=_iso(row.get("created_at")),
                    url=str(row.get("html_url") or ""),
                    kind=KIND_REVIEW_THREAD,
                    path=str(row.get("path") or ""),
                    line=line if isinstance(line, int) else None,
                )
            )
        return inline

    def list_comments(
        self, owner: str, repo: str, number: int, is_pr: bool, host: str = ""
    ) -> List[GhComment]:
        """Every comment on an issue/PR, whichever surface GitHub filed it under.

        An issue is one read. A pull request is that read plus the two REST
        reads for the other surfaces (issue-246), merged into one chronological
        list — the first-sight control path forwards commands in thread order,
        so the last command wins.
        """
        comments = self.list_issue_comments(owner, repo, number, host)
        if not is_pr:
            return comments
        comments += self.list_reviews(owner, repo, number, host)
        comments += self.list_review_comments(owner, repo, number, host)
        return sorted(comments, key=lambda c: c.created_at)

    # -- the harness's pull-request verbs (issue-447) -----------------------------

    def repository(self, owner: str, repo: str, host: str = "") -> Dict[str, Any]:
        """``GET /repos/{o}/{r}`` — the raw document (``default_branch``)."""
        owner, repo = self._coordinates(owner, repo)
        data = self.rest("GET", f"/repos/{owner}/{repo}", host=host)
        if not isinstance(data, dict) or not data:
            raise GitHubApiError(f"repos/{owner}/{repo} returned no object")
        return data

    def create_pull(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
        draft: bool = False,
        host: str = "",
    ) -> Tuple[int, str]:
        """``POST /repos/{o}/{r}/pulls``. Returns ``(number, html_url)``.

        ``head`` is a branch of this repository, or ``owner:branch`` for a fork.
        """
        owner, repo = self._coordinates(owner, repo)
        head_owner, _, head_branch = head.rpartition(":")
        if head_owner and not is_github_name(head_owner):
            raise GitHubApiError(f"unusable head owner {head_owner!r}")
        self._branch(head_branch, "head")
        self._branch(base, "base")
        if not str(title).strip():
            raise GitHubApiError("a pull request needs a title")
        data = self.rest(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            {
                "title": str(title),
                "body": str(body),
                "head": head,
                "base": base,
                "draft": bool(draft),
            },
            host=host,
        )
        if not isinstance(data, dict) or not isinstance(data.get("number"), int):
            raise GitHubApiError(f"repos/{owner}/{repo}/pulls returned no number")
        return int(data["number"]), str(data.get("html_url") or "")

    def get_pull(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> Dict[str, Any]:
        """``GET /repos/{o}/{r}/pulls/{n}`` — the raw document."""
        owner, repo = self._coordinates(owner, repo)
        data = self.rest(
            "GET", f"/repos/{owner}/{repo}/pulls/{self._number(number)}", host=host
        )
        if not isinstance(data, dict) or not data:
            raise GitHubApiError(
                f"repos/{owner}/{repo}/pulls/{number} returned no object"
            )
        return data

    def commit_checks(
        self, owner: str, repo: str, sha: str, host: str = ""
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """``(check_runs, statuses)`` for ``sha`` — two requests, one page each.

        A hundred check runs is the page GitHub serves at most; a commit carrying
        more is summarised from the first hundred, which is still a verdict an
        agent can act on (the NFR bounds ``pr status`` at three requests).
        """
        owner, repo = self._coordinates(owner, repo)
        sha = self._sha(sha)
        runs = self.rest(
            "GET",
            f"/repos/{owner}/{repo}/commits/{sha}/check-runs?per_page={PAGE_SIZE}",
            host=host,
        )
        status = self.rest(
            "GET", f"/repos/{owner}/{repo}/commits/{sha}/status", host=host
        )
        check_runs = runs.get("check_runs") if isinstance(runs, dict) else None
        statuses = status.get("statuses") if isinstance(status, dict) else None
        return (
            [r for r in (check_runs or []) if isinstance(r, dict)],
            [s for s in (statuses or []) if isinstance(s, dict)],
        )

    def merge_pull(
        self, owner: str, repo: str, number: int, method: str, host: str = ""
    ) -> Dict[str, Any]:
        """``PUT /repos/{o}/{r}/pulls/{n}/merge``. GitHub's refusal (405 not
        mergeable, 409 head moved) is :class:`GitHubApiError` with its status."""
        owner, repo = self._coordinates(owner, repo)
        if method not in MERGE_METHODS:
            raise GitHubApiError(f"unusable merge method {method!r}")
        data = self.rest(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{self._number(number)}/merge",
            {"merge_method": method},
            host=host,
        )
        return data if isinstance(data, dict) else {}

    def review_threads(
        self, owner: str, repo: str, number: int, host: str = ""
    ) -> List[Dict[str, Any]]:
        """Every review thread on a pull request, resolved or not, oldest first."""
        owner, repo = self._coordinates(owner, repo)
        number = self._number(number)
        threads: List[Dict[str, Any]] = []
        after: Optional[str] = None
        while True:
            data = self.graphql(
                _REVIEW_THREADS_QUERY,
                {
                    "owner": owner,
                    "name": repo,
                    "number": number,
                    "first": PAGE_SIZE,
                    "after": after,
                },
                host=host,
            )
            pull = (data.get("repository") or {}).get("pullRequest")
            if not isinstance(pull, Mapping):
                raise GitHubApiError(f"{owner}/{repo}#{number} not found", status=404)
            conn = pull.get("reviewThreads") or {}
            for node in conn.get("nodes") or []:
                if not isinstance(node, Mapping):
                    continue
                line = node.get("line")
                threads.append(
                    {
                        "id": str(node.get("id") or ""),
                        "isResolved": bool(node.get("isResolved")),
                        "isOutdated": bool(node.get("isOutdated")),
                        "path": str(node.get("path") or ""),
                        "line": line if isinstance(line, int) else None,
                        "comments": [
                            {
                                "id": str(c.get("id") or ""),
                                "author": _login(c.get("author")),
                                "body": str(c.get("body") or ""),
                                "createdAt": _iso(c.get("createdAt")),
                                "url": str(c.get("url") or ""),
                            }
                            for c in ((node.get("comments") or {}).get("nodes") or [])
                            if isinstance(c, Mapping)
                        ],
                    }
                )
            info = conn.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                return threads
            after = str(info["endCursor"])

    def open_pulls_for_head(
        self, owner: str, repo: str, branch: str, host: str = ""
    ) -> List[Dict[str, Any]]:
        """The open pull requests of ``owner/repo`` whose head is ``owner:branch``
        (``GET …/pulls?state=open&head=…``) — what ``link-pr --discover`` links."""
        owner, repo = self._coordinates(owner, repo)
        branch = self._branch(branch)
        return self.rest_pages(
            f"/repos/{owner}/{repo}/pulls",
            {"state": "open", "head": f"{owner}:{branch}"},
            host=host,
        )

    # -- GraphQL paging and parsing ------------------------------------------------

    def _graphql_pages(
        self,
        query: str,
        owner: str,
        repo: str,
        connection: str,
        variables: Dict[str, Any],
        host: str,
    ):
        after: Optional[str] = None
        while True:
            data = self.graphql(
                query,
                {
                    "owner": owner,
                    "name": repo,
                    "first": PAGE_SIZE,
                    "after": after,
                    **variables,
                },
                host=host,
            )
            repository = data.get("repository")
            if not isinstance(repository, Mapping):
                raise GitHubApiError(f"{owner}/{repo} not found", status=404)
            conn = repository.get(connection) or {}
            nodes = [n for n in (conn.get("nodes") or []) if isinstance(n, Mapping)]
            yield repository, nodes
            info = conn.get("pageInfo") or {}
            if not info.get("hasNextPage") or not info.get("endCursor"):
                return
            after = str(info["endCursor"])

    @staticmethod
    def _item_from_node(node: Mapping[str, Any], is_pr: bool) -> GhItem:
        labels = [
            str(lab.get("name"))
            for lab in ((node.get("labels") or {}).get("nodes") or [])
            if isinstance(lab, Mapping) and lab.get("name")
        ]
        linked = [
            ref.get("number")
            for ref in ((node.get("closingIssuesReferences") or {}).get("nodes") or [])
            if isinstance(ref, Mapping) and isinstance(ref.get("number"), int)
        ]
        return GhItem(
            number=int(node["number"]),
            title=str(node.get("title") or ""),
            labels=labels,
            updated_at=_iso(node.get("updatedAt")),
            url=str(node.get("url") or ""),
            is_pr=is_pr,
            author=_login(node.get("author")),
            head_ref=str(node.get("headRefName") or ""),
            body=str(node.get("body") or ""),
            linked_issues=[n for n in linked if isinstance(n, int)],
        )

    @staticmethod
    def _comment_from_node(node: Mapping[str, Any]) -> GhComment:
        return GhComment(
            id=str(node.get("id") or ""),
            body=str(node.get("body") or ""),
            author=_login(node.get("author")),
            created_at=_iso(node.get("createdAt")),
            url=str(node.get("url") or ""),
        )
