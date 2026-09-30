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

Built in the mould of :mod:`the_loop.comments` — the daemon's GitHub client, an
injectable seam, never raises — with one deliberate difference. That module
performs an action and reports whether it worked; this one answers a question,
so its failure mode is *unknown*, not *failed*, and unknown means **keep the
ref**. An existence check that cannot run must never mute a daemon: only a
definitive HTTP 404 is evidence of absence.

The payload → request boundary is real here (a ``WorkItemRef``'s owner and repo
come from a webhook payload), so coordinates are validated against GitHub's own
name shape before they reach a URL, and a ref that fails validation is answered
*unknown* — never dropped, because a malformed payload must not be able to
delete a work item from routing.

Spec: docs/specs/issue-269/design.md §C2; issue-442 moved the read from ``gh``
to PyGithub without changing an answer.
"""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Optional

from .comments import resolve_client
from .ghapi import GitHubApiConfig, GitHubApiError, GitHubClient
from .sessions import WorkItemRef, is_github_name

logger = logging.getLogger("the-loop.linkage")

__all__ = ["WorkItemVerifier", "looks_not_found"]

#: How long one existence question may take. Deliberately short: this runs on the
#: ingress thread, and a hung request must not hold a poll cycle open.
DEFAULT_TIMEOUT = 10.0

#: How many answers are remembered. A daemon sees a handful of live work items;
#: the cache exists so a repeatedly-commented pull request costs one call, not
#: so history is kept.
DEFAULT_CACHE_SIZE = 256

_HTTP_404_RE = re.compile(r"(?:HTTP|GitHub)[\s/:]*404\b", re.IGNORECASE)
_BARE_404_RE = re.compile(r"\b404\b")


def looks_not_found(text: str) -> bool:
    """Whether ``text`` is GitHub saying the thing is not there.

    Shared with :mod:`the_loop.announce`, which gets the same sentence back
    (``GitHub 404: Not Found``, the client's rendering) when it tries to comment
    on a work item that does not exist — the one piece of direct evidence the
    daemon used to log and ignore.

    Narrow on purpose: ``HTTP 404`` / ``GitHub 404`` in any spacing, or a bare
    ``404`` in text that also says *not found*. A comment body that merely
    contains the number 404 is not an answer about existence.
    """
    text = text or ""
    if _HTTP_404_RE.search(text):
        return True
    return bool(_BARE_404_RE.search(text)) and "not found" in text.lower()


class WorkItemVerifier:
    """Answers "does this work item exist?" through the daemon's GitHub client.

    Never raises, never blocks longer than ``timeout``, and answers ``False``
    (i.e. *not known to be missing*) for everything it cannot establish. The
    client is injectable so tests drive it without a network — the pattern
    :class:`~the_loop.reactions.GitHubReactor` and
    :class:`~the_loop.announce.SessionAnnouncer` already use.

    The question is the REST ``issues`` endpoint, which answers for issues
    **and** pull requests (on GitHub a pull request is an issue) — a ref carries
    no kind. A ref on GitHub Enterprise is asked of **its own** host: a 404 from
    the public GitHub about an enterprise work item would be an answer to a
    different question.
    """

    def __init__(
        self,
        api: Optional[GitHubApiConfig] = None,
        client: Optional[GitHubClient] = None,
        timeout: Optional[float] = DEFAULT_TIMEOUT,
        cache_size: int = DEFAULT_CACHE_SIZE,
    ):
        self.timeout = timeout
        self._client = resolve_client(api, client, timeout)
        self._cache_size = max(1, cache_size)
        # ref -> True (definitely gone) | False (definitely there). An answer the
        # check could not establish is NOT cached: a transient failure must not
        # freeze into a permanent verdict.
        self._cache: "OrderedDict[str, bool]" = OrderedDict()
        self._warned_missing_token = False

    # -- the question ----------------------------------------------------------

    def is_missing(self, item: WorkItemRef) -> bool:
        """``True`` only when the provider says this work item does not exist."""
        if item.provider != "github":
            # Nothing to ask, and nothing to conclude: a Jira ref is not absent
            # merely because GitHub cannot see it.
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
        try:
            self._client.get_issue(item.owner, item.repo, item.number, host=item.host)
        except GitHubApiError as exc:
            if exc.missing_token:
                if not self._warned_missing_token:
                    self._warned_missing_token = True
                    logger.warning(
                        "%s — work items derived from a branch name cannot be "
                        "verified, so they are routed as before (set the token to "
                        "have a branch-invented work item dropped)",
                        exc,
                    )
                return False
            if exc.not_found:
                logger.info("%s does not exist (%s)", item.ref, exc)
                self._remember(item.ref, True)
                return True
            logger.debug(
                "could not establish whether %s exists (%s); keeping it", item.ref, exc
            )
            return False
        except Exception as exc:  # noqa: BLE001 — unknown, never dropped
            logger.debug("could not ask whether %s exists: %s", item.ref, exc)
            return False
        self._remember(item.ref, False)
        return False

    def record_missing(self, item: WorkItemRef) -> None:
        """Remember that ``item`` does not exist, on evidence from elsewhere.

        The session announcement gets the same 404 when it comments on a work
        item that was never created (issue-269 R3.2). That is direct evidence;
        filing it here is what stops the next event carrying the same
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
