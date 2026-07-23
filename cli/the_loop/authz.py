"""Authorized-actor guard — the prompt-injection *and* self-reply boundary.

the-loop reacts to work items it has been told to orchestrate (via a label), but
the *content* it then ingests — issue/PR bodies, comments, reviews — is written
by whoever is on GitHub, not necessarily the operator. Treating that content as
instructions is a prompt-injection vector: anyone who can comment on a labelled
issue could steer the agent.

The remediation: only actions by **authorized users** (GitHub logins listed in
config) are allowed to be an input the-loop acts on. This is enforced at *both*
trigger paths — the webhook router and the poller — via :func:`is_authorized`.

Model (each operator runs their own instance for themselves):

* A human-authored action (comment, review, label, an issue/PR the-loop would
  start on) is actionable only if its author/actor is in the allowlist.
* An action with no identifiable human actor (e.g. a CI status/`workflow_run`
  event) is allowed — it carries status, not free-form instructions, and cannot
  be forged past the webhook HMAC / the trusted `gh` API.
* An **empty** allowlist fails closed for human-authored actions (and is warned
  about at startup): nothing human-authored is actioned until it is configured.

## Self-reply guard (issue-64)

The spawned harness (Claude Code / Cursor) posts its own replies through the
operator's own `gh`/API credentials (decision-023's operating model: no
separate bot token). That means a reply the-loop itself just posted is, by
*author*, indistinguishable from one the operator typed — `is_authorized`
alone would happily let the-loop's own comment re-enter the loop as new input,
resuming the session, which may reply again, forever.

GitHub's comment/review objects carry no queryable custom metadata field for
this — the only channel available is the body text itself. The remediation is
a stable marker embedded in the body of every comment/review/reply the-loop
posts (`SELF_COMMENT_MARKER`, checked by :func:`is_self_authored`). Both
trigger paths drop a self-marked comment *before* the authorized-actor check
even runs — it is dropped regardless of who technically posted it.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

logger = logging.getLogger("the-loop.authz")

# Embedded (as an invisible HTML comment, so it never clutters the rendered
# issue/PR/review thread) in the body of every comment, review or reply the
# harness posts on the-loop's behalf. See `reference/collaboration.md` — every
# such post additionally carries a *visible* human-readable attribution line;
# this marker is the fixed, exact-match part machine code relies on, so it
# must never change once shipped (older comments must stay recognizable).
SELF_COMMENT_MARKER = "<!-- the-loop:agent-comment -->"


def is_self_authored(body: Optional[str]) -> bool:
    """Whether ``body`` carries the-loop's own authorship marker.

    True for any comment/review/reply the-loop itself posted, regardless of
    which GitHub login posted it — the router/poller use this to drop it
    before it can re-enter the loop as if a human had written it (issue-64).
    """
    return bool(body) and SELF_COMMENT_MARKER in body


def resolve_authorized_users(
    configured: Sequence[str], owner: Optional[str]
) -> List[str]:
    """The effective allowlist: the explicit config, else the repo owner.

    Falling back to ``ticketing.github.owner`` keeps the common single-operator
    setup working without extra config (the operator acts on their own items),
    while still blocking third parties. When neither is available the list is
    empty and the guards fail closed — callers should warn about that.
    """
    users = [str(u) for u in configured if u]
    if users:
        return users
    return [owner] if owner else []


def is_authorized(actor: Optional[str], authorized: Sequence[str]) -> bool:
    """Whether ``actor``'s action may be an input the-loop acts on.

    ``actor is None`` (no identifiable human actor — e.g. a CI event) is allowed.
    A named actor is allowed only when present in ``authorized``; an empty
    allowlist therefore denies every human-authored action (fail closed).
    """
    if not actor:
        return True
    return actor in set(authorized)
