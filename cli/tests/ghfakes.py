"""An in-memory double for :class:`the_loop.ghapi.GitHubClient` (issue-442).

The callers of the client — the comment writers, the existence check, the
reactor, the announcer, the poller's provider, the graph's provider — are
tested against this, the way they were tested against a fake ``gh`` runner:
the same method surface, canned answers, per-method failure knobs, and a log
of every call. The real client is tested separately against PyGithub's own
connection-injection hook (``ghreplay.py``), so nothing here is a claim about
what PyGithub sends — only about what the caller asked for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from the_loop.ghapi import (
    REACTION_CONTENTS,
    GhComment,
    GhItem,
    GhItemState,
    GitHubApiConfig,
    GitHubApiError,
    GitHubClient,
)

__all__ = ["FakeGitHubClient", "missing_token", "not_found", "http_error"]


def missing_token(config: Optional[GitHubApiConfig] = None) -> GitHubApiError:
    config = config or GitHubApiConfig()
    return GitHubApiError(config.missing_token_reason, missing_token=True)


def not_found(message: str = "Not Found") -> GitHubApiError:
    return GitHubApiError(message, status=404)


def http_error(status: int, message: str = "boom") -> GitHubApiError:
    return GitHubApiError(message, status=status)


@dataclass
class FakeGitHubClient(GitHubClient):
    """Every operation of the client, answered from memory.

    A subclass of the real client for the type checker's sake — every method
    the callers use is overridden here, and the real client's HTTP machinery
    (``_build``, the per-host cache) is never reached.

    ``fail`` raises the given error from **every** call; ``fail_on`` raises it
    from the named methods only. ``missing`` is the set of ``(owner, repo,
    number)`` that answer 404. Reads answer from the ``issues``/``prs``/
    ``comments``/``reviews``/``review_comments``/``states`` tables; writes
    append to ``posted``/``created``/``reactions``/``label_calls``.
    """

    config: GitHubApiConfig = field(default_factory=GitHubApiConfig)
    timeout: float = 30.0
    token: bool = True
    fail: Optional[GitHubApiError] = None
    fail_on: Dict[str, GitHubApiError] = field(default_factory=dict)
    missing: set = field(default_factory=set)
    viewer: str = "the-loop-bot"
    comment_url: str = "https://github.com/octo/repo/issues/15#issuecomment-9"
    next_issue_number: int = 42

    # reads
    issues: Dict[Tuple[str, str], List[GhItem]] = field(default_factory=dict)
    prs: Dict[Tuple[str, str], List[GhItem]] = field(default_factory=dict)
    comments: Dict[Tuple[str, str, int], List[GhComment]] = field(default_factory=dict)
    reviews: Dict[Tuple[str, str, int], List[GhComment]] = field(default_factory=dict)
    review_comments: Dict[Tuple[str, str, int], List[GhComment]] = field(
        default_factory=dict
    )
    states: Dict[Tuple[str, str, int], Dict[str, Any]] = field(default_factory=dict)
    labels: Dict[Tuple[str, str, int], List[str]] = field(default_factory=dict)
    issues_disabled: set = field(default_factory=set)  # (owner, repo)

    # writes and the log
    posted: List[Tuple[str, str, int, str, str]] = field(default_factory=list)
    created: List[Tuple[str, str, str, str, List[str], str]] = field(
        default_factory=list
    )
    reactions: List[Tuple[str, Any, str, str]] = field(default_factory=list)
    label_calls: List[Tuple[str, ...]] = field(default_factory=list)
    calls: List[Tuple[str, Dict[str, Any]]] = field(default_factory=list)

    # -- plumbing -------------------------------------------------------------

    @staticmethod
    def _host(host: str) -> str:
        """github.com stays unwritten, as the real client normalises it."""
        return "" if host in ("", "github.com") else host

    def _enter(self, method: str, **kwargs: Any) -> None:
        if "host" in kwargs:
            kwargs["host"] = self._host(kwargs["host"])
        self.calls.append((method, kwargs))
        if not self.token:
            raise missing_token(self.config)
        if self.fail is not None:
            raise self.fail
        if method in self.fail_on:
            raise self.fail_on[method]

    def has_token(self) -> bool:
        return self.token

    def github(self, host: str = "") -> Any:
        self._enter("github", host=host)
        return object()

    @property
    def calls_to(self) -> List[str]:
        return [name for name, _ in self.calls]

    # -- writes ---------------------------------------------------------------

    def post_comment(self, owner, repo, number, body, host="") -> str:
        self._enter("post_comment", owner=owner, repo=repo, number=number, host=host)
        if (owner, repo, int(number)) in self.missing:
            raise not_found()
        self.posted.append((owner, repo, int(number), body, self._host(host)))
        return self.comment_url

    def create_issue(
        self, owner, repo, title, body, labels=(), host=""
    ) -> Tuple[int, str]:
        self._enter("create_issue", owner=owner, repo=repo, host=host)
        number = self.next_issue_number
        self.next_issue_number += 1
        self.created.append((owner, repo, title, body, list(labels), self._host(host)))
        return number, f"https://github.com/{owner}/{repo}/issues/{number}"

    def add_reaction(self, owner, repo, kind, id, content, host="") -> None:
        self._enter("add_reaction", owner=owner, repo=repo, kind=kind, id=id, host=host)
        if content not in REACTION_CONTENTS:
            raise GitHubApiError(f"unknown reaction {content!r}")
        self.reactions.append((kind, id, content, self._host(host)))

    def add_reaction_by_node(self, node_id, content, host="") -> None:
        self._enter("add_reaction_by_node", node_id=node_id, host=host)
        if content not in REACTION_CONTENTS:
            raise GitHubApiError(f"unknown reaction {content!r}")
        self.reactions.append(("node", node_id, content, self._host(host)))

    def add_labels(self, owner, repo, number, labels, host="") -> None:
        self._enter("add_labels", owner=owner, repo=repo, number=number, host=host)
        current = self.labels.setdefault((owner, repo, int(number)), [])
        for label in labels:
            if label not in current:
                current.append(label)
        self.label_calls.append(("add", owner, repo, str(number), *list(labels)))

    def ensure_label(self, owner, repo, name, color="ededed", host="") -> bool:
        self._enter("ensure_label", owner=owner, repo=repo, name=name, host=host)
        self.label_calls.append(("ensure", owner, repo, name, color))
        return True

    def remove_label(self, owner, repo, number, label, host="") -> bool:
        self._enter("remove_label", owner=owner, repo=repo, number=number, host=host)
        current = self.labels.setdefault((owner, repo, int(number)), [])
        self.label_calls.append(("remove", owner, repo, str(number), label))
        if label in current:
            current.remove(label)
            return True
        return False

    # -- reads ----------------------------------------------------------------

    def get_issue(self, owner, repo, number, host="") -> Dict[str, Any]:
        self._enter("get_issue", owner=owner, repo=repo, number=number, host=host)
        key = (owner, repo, int(number))
        if key in self.missing:
            raise not_found()
        state = self.states.get(key)
        if state is None:
            return {"number": int(number), "state": "open"}
        return dict(state)

    def item_state(self, owner, repo, number, host="") -> GhItemState:
        data = self.get_issue(owner, repo, number, host)
        pull_request = data.get("pull_request")
        return GhItemState(
            number=int(data.get("number") or number),
            state=str(data.get("state") or ""),
            is_pr=isinstance(pull_request, dict),
            merged=bool((pull_request or {}).get("merged_at")),
            title=str(data.get("title") or ""),
            url=str(data.get("html_url") or ""),
            closed_by=str(((data.get("closed_by") or {}).get("login")) or ""),
        )

    def labels_of(self, owner, repo, number, host="") -> List[str]:
        self._enter("labels_of", owner=owner, repo=repo, number=number, host=host)
        return list(self.labels.get((owner, repo, int(number)), []))

    def viewer_login(self, host="") -> str:
        try:
            self._enter("viewer_login", host=host)
        except GitHubApiError:
            return ""
        return self.viewer

    def list_labeled_issues(
        self, owner, repo, labels: Sequence[str], host=""
    ) -> List[GhItem]:
        self._enter(
            "list_labeled_issues",
            owner=owner,
            repo=repo,
            labels=list(labels),
            host=host,
        )
        if (owner, repo) in self.issues_disabled:
            raise GitHubApiError("Issues are disabled for this repo", status=410)
        return list(self.issues.get((owner, repo), []))

    def list_labeled_prs(
        self, owner, repo, labels: Sequence[str], host=""
    ) -> List[GhItem]:
        self._enter(
            "list_labeled_prs", owner=owner, repo=repo, labels=list(labels), host=host
        )
        return list(self.prs.get((owner, repo), []))

    def list_issue_comments(self, owner, repo, number, host="") -> List[GhComment]:
        self._enter(
            "list_issue_comments", owner=owner, repo=repo, number=number, host=host
        )
        key = (owner, repo, int(number))
        if key in self.missing:
            raise not_found()
        return list(self.comments.get(key, []))

    def list_reviews(self, owner, repo, number, host="") -> List[GhComment]:
        self._enter("list_reviews", owner=owner, repo=repo, number=number, host=host)
        return list(self.reviews.get((owner, repo, int(number)), []))

    def list_review_comments(self, owner, repo, number, host="") -> List[GhComment]:
        self._enter(
            "list_review_comments", owner=owner, repo=repo, number=number, host=host
        )
        return list(self.review_comments.get((owner, repo, int(number)), []))

    def list_comments(self, owner, repo, number, is_pr, host="") -> List[GhComment]:
        comments = self.list_issue_comments(owner, repo, number, host)
        if not is_pr:
            return comments
        comments += self.list_reviews(owner, repo, number, host)
        comments += self.list_review_comments(owner, repo, number, host)
        return sorted(comments, key=lambda c: c.created_at)
