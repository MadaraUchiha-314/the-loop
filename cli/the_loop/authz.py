"""Authorized-actor guard — the prompt-injection boundary (issue-34 review).

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
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

logger = logging.getLogger("the-loop.authz")


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
