"""Does this work item exist? — the check a branch name cannot answer (issue-269).

Three linkage sources can name the work item a pull request delivers, and two of
them *state* the repository they mean: GitHub's own ``closingIssuesReferences``,
and a qualified closing keyword. The third — the-loop's own ``issue-<n>`` branch
convention — does not. It is resolved in the pull request's own repository, and
before this module nothing ever asked whether the result existed. In a
multi-repository deployment (the ticket lives in one repository, the code in
another) that fabricated a work item, which then took the operator's ``the-loop
start`` and spawned a session of its own against a ref that 404s.

So: **one question, asked only where a ref could have been invented.**

Built in the mould of :mod:`the_loop.comments` — the operator's own ``gh``, an
injectable runner, never raises — with one deliberate difference. That module
performs an action and reports whether it worked; this one answers a question,
so its failure mode is *unknown*, not *failed*, and unknown means **keep the
ref**. An existence check that cannot run must never mute a daemon: only a
definitive HTTP 404 is evidence of absence.

The payload → argv boundary is real here (a ``WorkItemRef``'s owner and repo
come from a webhook payload), so coordinates are validated against GitHub's own
name shape before they reach a command line, the process is spawned from an argv
list with no shell, and a ref that fails validation is answered *unknown* —
never dropped, because a malformed payload must not be able to delete a work
item from routing.

Spec: docs/specs/issue-269/design.md §C2.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from collections import OrderedDict
from typing import Callable, Optional

from .sessions import WorkItemRef, is_github_name

logger = logging.getLogger("the-loop.linkage")

__all__ = ["WorkItemVerifier", "existence_argv", "looks_not_found"]

#: How long one existence question may take. Deliberately short: this runs on the
#: ingress thread, and a hung ``gh`` must not hold a poll cycle open.
DEFAULT_TIMEOUT = 10.0

#: How many answers are remembered. A daemon sees a handful of live work items;
#: the cache exists so a repeatedly-commented pull request costs one call, not
#: so history is kept.
DEFAULT_CACHE_SIZE = 256

_HTTP_404_RE = re.compile(r"HTTP[\s/:]*404\b", re.IGNORECASE)
_BARE_404_RE = re.compile(r"\b404\b")


def looks_not_found(text: str) -> bool:
    """Whether ``text`` is GitHub saying the thing is not there.

    Shared with :mod:`the_loop.announce`, which gets the same sentence back from
    ``gh`` when it tries to comment on a work item that does not exist — the one
    piece of direct evidence the daemon used to log and ignore.

    Narrow on purpose: ``HTTP 404`` in any spacing, or a bare ``404`` in text
    that also says *not found*. A comment body that merely contains the number
    404 is not an answer about existence.
    """
    text = text or ""
    if _HTTP_404_RE.search(text):
        return True
    return bool(_BARE_404_RE.search(text)) and "not found" in text.lower()


def existence_argv(item: WorkItemRef) -> list:
    """The ``gh`` arguments that ask whether ``item`` exists.

    The REST ``issues`` endpoint answers for issues **and** pull requests (on
    GitHub a pull request is an issue), which matters because a ref carries no
    kind — the same reason ``GhClient.fetch_item_state`` uses it for the closure
    question. A ref on GitHub Enterprise is asked of **its own** host: a 404 from
    the public GitHub about an enterprise work item would be an answer to a
    different question.
    """
    host = [] if item.default_host else ["--hostname", item.host]
    return ["api"] + host + [f"repos/{item.owner}/{item.repo}/issues/{item.number}"]


class WorkItemVerifier:
    """Answers "does this work item exist?" through the operator's own ``gh``.

    Never raises, never blocks longer than ``timeout``, and answers ``False``
    (i.e. *not known to be missing*) for everything it cannot establish. The
    runner is injectable so tests drive it without a real ``gh`` — the pattern
    :class:`~the_loop.reactions.GitHubReactor` and
    :class:`~the_loop.announce.SessionAnnouncer` already use.
    """

    def __init__(
        self,
        gh_binary: str = "gh",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        self.gh_binary = gh_binary
        self._runner = runner
        self.timeout = timeout
        self._cache_size = max(1, cache_size)
        # ref -> True (definitely gone) | False (definitely there). An answer the
        # check could not establish is NOT cached: a transient failure must not
        # freeze into a permanent verdict.
        self._cache: "OrderedDict[str, bool]" = OrderedDict()
        self._warned_missing_gh = False

    # -- the question ----------------------------------------------------------

    def is_missing(self, item: WorkItemRef) -> bool:
        """``True`` only when the provider says this work item does not exist."""
        if item.provider != "github":
            # Nothing to ask, and nothing to conclude: a Jira ref is not absent
            # merely because `gh` cannot see it.
            return False
        if not (is_github_name(item.owner) and is_github_name(item.repo)):
            logger.debug(
                "not asking about %s: unusable repo coordinates; keeping the ref",
                item.ref,
            )
            return False
        cached = self._cache.get(item.ref)
        if cached is not None:
            self._cache.move_to_end(item.ref)
            return cached
        if shutil.which(self.gh_binary) is None:
            if not self._warned_missing_gh:
                self._warned_missing_gh = True
                logger.warning(
                    "gh CLI %r not found on PATH — work items derived from a branch "
                    "name cannot be verified, so they are routed as before "
                    "(install gh to have a branch-invented work item dropped)",
                    self.gh_binary,
                )
            return False
        cmd = [self.gh_binary] + existence_argv(item)
        try:
            proc = self._runner(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.debug("could not ask whether %s exists: %s", item.ref, exc)
            return False
        if proc.returncode == 0:
            self._remember(item.ref, False)
            return False
        detail = ((proc.stderr or "") + " " + (proc.stdout or "")).strip()
        if looks_not_found(detail):
            logger.info("%s does not exist (%s)", item.ref, detail)
            self._remember(item.ref, True)
            return True
        logger.debug(
            "could not establish whether %s exists (gh exited %s: %s); keeping it",
            item.ref,
            proc.returncode,
            detail,
        )
        return False

    def record_missing(self, item: WorkItemRef) -> None:
        """Remember that ``item`` does not exist, on evidence from elsewhere.

        The session announcement gets the same 404 from ``gh`` when it comments
        on a work item that was never created (issue-269 R3.2). That is direct
        evidence; filing it here is what stops the next event carrying the same
        branch-derived ref from asking again — or from being acted on.
        """
        if item.provider == "github":
            self._remember(item.ref, True)

    # -- the cache -------------------------------------------------------------

    def _remember(self, ref: str, missing: bool) -> None:
        self._cache[ref] = missing
        self._cache.move_to_end(ref)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
