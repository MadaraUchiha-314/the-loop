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

import logging
import re
import shutil
import subprocess
from typing import Callable, Optional, Tuple

from .sessions import WorkItemRef

logger = logging.getLogger("the-loop.comments")

__all__ = ["comment_argv", "post_issue_comment"]

# Defensive validation of the API coordinates before they reach a `gh` argv.
# They come from an already-parsed WorkItemRef rather than a payload, but the
# check is cheap and this is the one place they become a command line.
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def comment_argv(item: WorkItemRef, body: str) -> list:
    """The ``gh`` arguments that post ``body`` on ``item``.

    The issues endpoint serves PR conversations too, so one argv covers both.
    """
    return [
        "api",
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
    if item.provider != "github":
        return False, f"work item {item.ref} is not a GitHub one"
    if not _NAME_RE.match(item.owner) or not _NAME_RE.match(item.repo):
        return False, f"unusable repo coordinates in {item.ref}"
    if shutil.which(gh_binary) is None:
        return False, f"gh CLI {gh_binary!r} not found on PATH"
    cmd = [gh_binary] + comment_argv(item, body)
    try:
        proc = runner(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return False, f"gh exited {proc.returncode}: {detail}"
    return True, ""
