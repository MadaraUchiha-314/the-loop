"""Post a comment on a work item through the operator's own ``gh`` CLI.

the-loop writes to GitHub in three places now — dispatch reactions
(:mod:`the_loop.reactions`, issue-84), the interactive-session announcement
(:mod:`the_loop.announce`, issue-86) and the control paper trail
(:mod:`the_loop.control`, issue-106) — and the last of them is what made the
shared piece worth extracting: validate the repo coordinates, find ``gh``, build
the ``gh api …/issues/<n>/comments`` argv, run it, interpret the result.

The contract every caller relies on, unchanged from those two precedents:

* **the operator's credentials, never the-loop's own** (decision-023) — so the
  comment carries the loop-prevention marker or it will be read back as human
  input (issue-104);
* **best-effort** — a missing or failing ``gh`` returns a reason string; it never
  raises, and never fails the action the comment was describing;
* **injectable runner** so tests drive it without a real ``gh``.

The body is the caller's to compose; this module never builds one, so no
payload-derived text can leak in here by accident.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Callable, Optional, Tuple, Union

from .sessions import DEFAULT_GITHUB_HOST, WorkItemRef, is_github_host

logger = logging.getLogger("the-loop.comments")

__all__ = [
    "comment_argv",
    "create_issue",
    "gh_host_args",
    "issue_argv",
    "post_issue_comment",
    "post_issue_comment_with_url",
]

# Defensive validation of the API coordinates before they reach a `gh` argv.
# They come from an already-parsed WorkItemRef rather than a payload, but the
# check is cheap and this is the one place they become a command line.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def gh_host_args(item_or_host: Union[WorkItemRef, str]) -> list:
    """The ``gh api`` arguments that select ``item``'s GitHub — or nothing.

    The one spelling of a host on the ``gh api`` command line (issue-311, R4):
    ``--hostname <host>`` when the work item is not on github.com, and **nothing**
    when it is, so every argv a github.com deployment ever produced is
    byte-identical. ``gh`` keeps its credentials per host and sends only the one
    it holds for the host named here. Every ``gh api`` the-loop composes — a
    comment, a reaction, an issue, an existence check, a poll read — goes through
    this rather than spelling the flag itself, which is what stops a call site
    from forgetting it.

    Accepts a :class:`WorkItemRef` or a bare host string.
    """
    host = (
        item_or_host.host
        if isinstance(item_or_host, WorkItemRef)
        else str(item_or_host or "")
    )
    if not host or host == DEFAULT_GITHUB_HOST:
        return []
    return ["--hostname", host]


def comment_argv(item: WorkItemRef, body: str) -> list:
    """The ``gh`` arguments that post ``body`` on ``item``.

    The issues endpoint serves PR conversations too, so one argv covers both.
    A work item on GitHub Enterprise is addressed on its own host (issue-311).
    """
    return [
        "api",
        *gh_host_args(item),
        "--method",
        "POST",
        f"repos/{item.owner}/{item.repo}/issues/{item.number}/comments",
        "-f",
        f"body={body}",
    ]


def post_issue_comment(
    item: WorkItemRef,
    body: str,
    *,
    gh_binary: str = "gh",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str]:
    """Post ``body`` on ``item``. Returns ``(ok, error)``; never raises.

    ``error`` is a short human-readable reason when ``ok`` is False — a
    non-GitHub work item, unusable coordinates, no ``gh`` on PATH, or whatever
    ``gh`` itself said.
    """
    ok, error, _ = _post(
        item, body, gh_binary=gh_binary, runner=runner, timeout=timeout
    )
    return ok, error


def post_issue_comment_with_url(
    item: WorkItemRef,
    body: str,
    *,
    gh_binary: str = "gh",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str, str]:
    """:func:`post_issue_comment`, plus the created comment's ``html_url``.

    One shared implementation, two return shapes — the URL matters only to
    `the-loop ask` (issue-208), which records it on the ``session.awaiting_input``
    event so the dashboard can link "answer on the ticket" to the exact comment.
    An unparsable ``gh`` response degrades to an empty URL, never to a failed
    post: the comment is on the ticket either way.
    """
    return _post(item, body, gh_binary=gh_binary, runner=runner, timeout=timeout)


def _post(
    item: WorkItemRef,
    body: str,
    *,
    gh_binary: str,
    runner: Callable[..., subprocess.CompletedProcess],
    timeout: Optional[float],
) -> Tuple[bool, str, str]:
    if item.provider != "github":
        return False, f"work item {item.ref} is not a GitHub one", ""
    if not _NAME_RE.match(item.owner) or not _NAME_RE.match(item.repo):
        return False, f"unusable repo coordinates in {item.ref}", ""
    if shutil.which(gh_binary) is None:
        return False, f"gh CLI {gh_binary!r} not found on PATH", ""
    cmd = [gh_binary] + comment_argv(item, body)
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc), ""
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"gh exited {proc.returncode}: {detail}", ""
    return True, "", _html_url(proc.stdout or "")


def _html_url(stdout: str) -> str:
    """The ``html_url`` out of gh's JSON response, or ``""``."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return ""
    url = data.get("html_url") if isinstance(data, dict) else None
    return url if isinstance(url, str) else ""


def issue_argv(
    owner: str, repo: str, title: str, body: str, labels=(), host: str = ""
) -> list:
    """The ``gh`` arguments that open an issue on ``owner/repo`` (issue-309).

    ``gh api`` rather than ``gh issue create``: the API form returns the created
    issue as JSON, so the number and ``html_url`` come back in one call and no
    URL has to be parsed out of prose. ``host`` addresses an enterprise GitHub
    (issue-311); empty means github.com.
    """
    args = [
        "api",
        *gh_host_args(host),
        "--method",
        "POST",
        f"repos/{owner}/{repo}/issues",
        "-f",
        f"title={title}",
        "-f",
        f"body={body}",
    ]
    for label in labels:
        args += ["-f", f"labels[]={label}"]
    return args


def create_issue(
    repo_slug: str,
    title: str,
    body: str,
    labels=(),
    *,
    gh_binary: str = "gh",
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
    timeout: Optional[float] = 30.0,
) -> Tuple[bool, str, str, str]:
    """Open an issue. Returns ``(ok, error, ref, html_url)``; never raises.

    The ledger's record of a ``work-item.create`` event (issue-309). The same
    contract as the comment writer: the operator's credentials, best-effort, an
    injectable runner, and coordinates validated before they reach an argv. The
    body is the caller's to compose — this function never builds one.

    ``repo_slug`` is ``[<host>/]<owner>/<repo>`` — ``gh``'s own ``--repo``
    grammar (issue-311): a kickoff on GitHub Enterprise names its host, and the
    ref handed back carries it, so the thread binds to the right work item.
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
    if shutil.which(gh_binary) is None:
        return False, f"gh CLI {gh_binary!r} not found on PATH", "", ""
    cmd = [gh_binary] + issue_argv(
        owner,
        repo,
        title,
        body,
        [str(lbl) for lbl in labels if str(lbl).strip()],
        host=host,
    )
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc), "", ""
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"gh exited {proc.returncode}: {detail}", "", ""
    try:
        data = json.loads(proc.stdout or "")
    except ValueError:
        data = {}
    number = data.get("number") if isinstance(data, dict) else None
    if not isinstance(number, int):
        return False, "gh returned no issue number", "", _html_url(proc.stdout or "")
    ref = WorkItemRef(
        provider="github", owner=owner, repo=repo, number=number, host=host
    ).ref
    return True, "", ref, _html_url(proc.stdout or "")
