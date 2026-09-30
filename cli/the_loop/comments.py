"""Post a comment on, or open, a work item through the daemon's GitHub client.

the-loop writes to GitHub in several places — dispatch reactions
(:mod:`the_loop.reactions`, issue-84), the interactive-session announcement
(:mod:`the_loop.announce`, issue-86), the control paper trail
(:mod:`the_loop.control`, issue-106), the ledger's kickoff issue (issue-309) —
and this module is the shared piece under the comment and issue writers:
validate the repo coordinates, reach GitHub, interpret the result.

The contract every caller relies on, unchanged across the move from the
operator's ``gh`` to PyGithub (issue-442, decision-139):

* **one credential** — the token ``integrations.github.api.tokenEnv`` names,
  read from the environment (:class:`~the_loop.ghapi.GitHubApiConfig`); every
  body still carries the loop-prevention marker or it is read back as human
  input (issue-104);
* **best-effort** — a missing token or a failing call returns a reason string;
  it never raises, and never fails the action the comment was describing;
* **injectable client** so tests drive it without a network.

The body is the caller's to compose; this module never builds one, so no
payload-derived text can leak in here by accident.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

from .ghapi import GitHubApiConfig, GitHubApiError, GitHubClient
from .sessions import WorkItemRef, is_github_host

logger = logging.getLogger("the-loop.comments")

__all__ = [
    "create_issue",
    "post_issue_comment",
    "post_issue_comment_with_url",
    "resolve_client",
]

# Defensive validation of the API coordinates before they reach a request.
# They come from an already-parsed WorkItemRef rather than a payload, but the
# check is cheap and this is the one place they become a URL path.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def resolve_client(
    api: Optional[GitHubApiConfig],
    client: Optional[GitHubClient],
    timeout: Optional[float],
) -> GitHubClient:
    """The client a writer uses: the injected one, else the process-wide client
    for ``api`` (one HTTP session per host, shared by every best-effort writer)."""
    if client is not None:
        return client
    return GitHubClient.shared(api or GitHubApiConfig(), timeout=timeout or 30.0)


def post_issue_comment(
    item: WorkItemRef,
    body: str,
    *,
    api: Optional[GitHubApiConfig] = None,
    client: Optional[GitHubClient] = None,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str]:
    """Post ``body`` on ``item``. Returns ``(ok, error)``; never raises.

    ``error`` is a short human-readable reason when ``ok`` is False — a
    non-GitHub work item, unusable coordinates, no token, or whatever GitHub
    itself said.
    """
    ok, error, _ = _post(item, body, api=api, client=client, timeout=timeout)
    return ok, error


def post_issue_comment_with_url(
    item: WorkItemRef,
    body: str,
    *,
    api: Optional[GitHubApiConfig] = None,
    client: Optional[GitHubClient] = None,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str, str]:
    """:func:`post_issue_comment`, plus the created comment's ``html_url``.

    One shared implementation, two return shapes — the URL matters only to
    `the-loop ask` (issue-208), which records it on the ``session.awaiting_input``
    event so the dashboard can link "answer on the ticket" to the exact comment.
    A response without a URL degrades to an empty URL, never to a failed post:
    the comment is on the ticket either way.
    """
    return _post(item, body, api=api, client=client, timeout=timeout)


def _post(
    item: WorkItemRef,
    body: str,
    *,
    api: Optional[GitHubApiConfig],
    client: Optional[GitHubClient],
    timeout: Optional[float],
) -> Tuple[bool, str, str]:
    if item.provider != "github":
        return False, f"work item {item.ref} is not a GitHub one", ""
    if not _NAME_RE.match(item.owner) or not _NAME_RE.match(item.repo):
        return False, f"unusable repo coordinates in {item.ref}", ""
    gh = resolve_client(api, client, timeout)
    try:
        url = gh.post_comment(item.owner, item.repo, item.number, body, host=item.host)
    except GitHubApiError as exc:
        return False, str(exc), ""
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        return False, f"{type(exc).__name__}: {exc}", ""
    return True, "", url or ""


def create_issue(
    repo_slug: str,
    title: str,
    body: str,
    labels=(),
    *,
    api: Optional[GitHubApiConfig] = None,
    client: Optional[GitHubClient] = None,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str, str, str]:
    """Open an issue. Returns ``(ok, error, ref, html_url)``; never raises.

    The ledger's record of a ``work-item.create`` event (issue-309), and the
    self-diagnosis report (issue-242). The same contract as the comment writer:
    best-effort, an injectable client, and coordinates validated before they
    reach a request. The body is the caller's to compose — this function never
    builds one.

    ``repo_slug`` is ``[<host>/]<owner>/<repo>`` (issue-311): a kickoff on
    GitHub Enterprise names its host, and the ref handed back carries it, so the
    thread binds to the right work item. ``labels`` ride the same request;
    GitHub silently drops them for a caller without triage rights on the target
    repository, which is the documented degradation — the body names the
    intended label either way.
    """
    parts = repo_slug.strip().split("/")
    host = ""
    if len(parts) == 3:
        host, owner, repo = parts
        if not is_github_host(host):
            return False, f"kickoff repo {repo_slug!r} does not name a host", "", ""
    elif len(parts) == 2:
        owner, repo = parts
    else:
        return False, f"kickoff repo {repo_slug!r} is not [host/]owner/repo", "", ""
    if not owner or not repo:
        return False, f"kickoff repo {repo_slug!r} is not [host/]owner/repo", "", ""
    if not _NAME_RE.match(owner) or not _NAME_RE.match(repo):
        return False, f"unusable repo coordinates in {repo_slug!r}", "", ""
    if not title.strip():
        return False, "an issue needs a title", "", ""
    gh = resolve_client(api, client, timeout)
    try:
        number, url = gh.create_issue(
            owner,
            repo,
            title,
            body,
            [str(lbl) for lbl in labels if str(lbl).strip()],
            host=host,
        )
    except GitHubApiError as exc:
        return False, str(exc), "", ""
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        return False, f"{type(exc).__name__}: {exc}", "", ""
    ref = WorkItemRef(
        provider="github", owner=owner, repo=repo, number=number, host=host
    ).ref
    return True, "", ref, url or ""
