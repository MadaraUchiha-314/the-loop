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

The actor authorized is **whoever performed the action** — the commenter, the
reviewer, the labeller — never a bystander. The poll path has one place where no
such actor exists: a listing carries a work item's label but not who applied it,
so *starting work on the item itself* is gated on the item's author instead, or
on an authorized user's recorded arming command. That proxy governs spawning and
nothing else; a comment is always judged by its own author (issue-197,
decision-074).

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

The **producer** side of that contract is :func:`mark_self_authored`, which
lives here rather than at the call sites so the string the-loop writes and the
string it recognises are the same 30 lines of code. It applies to *every*
producer, not only the spawned harness: the CLI daemon's own comments (the
interactive-session announcement, `the_loop.announce`) are posted with the same
credentials and were, until issue-104, fed straight back into the session they
announced.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .identity import Principal

logger = logging.getLogger("the-loop.authz")

# Embedded (as an invisible HTML comment, so it never clutters the rendered
# issue/PR/review thread) in the body of every comment, review or reply the
# harness posts on the-loop's behalf. See `reference/collaboration.md` — every
# such post additionally carries a *visible* human-readable attribution line;
# this marker is the fixed, exact-match part machine code relies on, so it
# must never change once shipped (older comments must stay recognizable).
SELF_COMMENT_MARKER = "<!-- the-loop:agent-comment -->"

# The *visible* half of the same contract: a short attribution line so a human
# reading the thread also knows who wrote the comment (the marker itself is an
# invisible HTML comment). See `reference/collaboration.md`.
SELF_COMMENT_ATTRIBUTION = "🤖 _the-loop, autonomous comment_"

# Jira's form of the same contract (issue-475, design §C6, R4.6). An HTML comment
# does not survive ADF — Jira has no hidden text — so on Jira the marker is a
# VISIBLE sentinel carried by the attribution line itself. Like the GitHub
# marker, it must never change once shipped. The ingress backs it with a second,
# independent test: a comment whose author is the service account
# (``JiraComment.is_self``) is the-loop's own whatever its text says.
JIRA_SELF_MARKER = "[the-loop:agent-comment]"
JIRA_SELF_ATTRIBUTION = f"🤖 the-loop, autonomous comment · {JIRA_SELF_MARKER}"

#: What :func:`mark_self_authored` appends, so the Jira form can replace it.
_GITHUB_STAMP = f"{SELF_COMMENT_ATTRIBUTION}\n{SELF_COMMENT_MARKER}"

# The relay marker (issue-475, design addendum to §C7/§C8). On GitHub a relay — a
# gate answer or control command an authorized person gave on another channel,
# recorded on the work item by the ledger — is posted UNMARKED under the
# operator's own credentials, so both ingresses read it back as the operator's
# authorized words. On Jira the ledger writes as a dedicated service account, and
# every comment by that account is the-loop's own (the author test). So a relay
# carries this visible marker INSTEAD of the agent marker, and the Jira ingress
# accepts a service-account comment that carries it (and not the agent marker) as
# authorized — the operator's identity, exactly as on GitHub. On anyone else's
# comment the marker is just text and grants nothing (:func:`jira_comment_origin`).
# Like the self-marker, it must never change once shipped.
JIRA_RELAY_MARKER = "[the-loop:relay]"
JIRA_RELAY_ATTRIBUTION = f"🗣️ relayed by the-loop · {JIRA_RELAY_MARKER}"

#: How a human gate (``classify-feedback``, the phase-selection reply) names a
#: Jira comment's author: ``jira:<accountId>`` — a namespace no GitHub login can
#: enter (a login has no ``:``), so a GitHub account named like a Jira id never
#: passes a gate as that person, and the reverse (issue-475).
JIRA_GATE_PREFIX = "jira:"
#: The author a gate sees for a Jira relay: the operator's words, as an unmarked
#: relay is on GitHub. Outside both namespaces above, so nothing else can claim it.
JIRA_RELAY_GATE_AUTHOR = "jira-relay:operator"

#: What :func:`jira_comment_origin` answers.
ORIGIN_SELF = "self"
ORIGIN_RELAY = "relay"
ORIGIN_HUMAN = "human"


def is_self_authored(body: Optional[str], provider: str = "github") -> bool:
    """Whether ``body`` carries the-loop's own authorship marker.

    True for any comment/review/reply the-loop itself posted, regardless of
    which login posted it — the router/poller use this to drop it before it can
    re-enter the loop as if a human had written it (issue-64).

    Which marker counts depends on where the body was read (issue-475): the
    GitHub marker (an HTML comment, invisible, so nobody quotes it by accident)
    everywhere; the Jira one (the visible ``[the-loop:agent-comment]``) only for a
    body read from Jira, ``provider="jira"`` — on GitHub that text is just text a
    person may quote, and a quoted marker must not silence their comment.
    """
    if not body:
        return False
    if SELF_COMMENT_MARKER in body:
        return True
    return provider == "jira" and JIRA_SELF_MARKER in body


def mark_self_authored(body: str) -> str:
    """``body`` stamped as the-loop's own: visible attribution + the marker.

    The **producer** half of the marker contract, deliberately living next to
    its consumer (:func:`is_self_authored`) so what the-loop writes and what it
    recognises can never drift apart. Idempotent: a body that already carries
    the marker is returned unchanged.

    Apply this ONLY to text the-loop itself composed — never to payload-derived
    text or another author's comment. The marker asserts authorship, and both
    trigger paths silently drop whatever carries it (issue-104).
    """
    if body and SELF_COMMENT_MARKER in body:
        return body
    return f"{body.rstrip()}\n\n{SELF_COMMENT_ATTRIBUTION}\n{SELF_COMMENT_MARKER}\n"


def mark_self_authored_on_jira(body: str) -> str:
    """``body`` stamped as the-loop's own **for Jira** (issue-475, R4.6).

    The GitHub stamp (:func:`mark_self_authored`) is replaced by the one visible
    line Jira keeps — :data:`JIRA_SELF_ATTRIBUTION`, which carries
    :data:`JIRA_SELF_MARKER` — and an unmarked body gets that line appended.
    Idempotent. The same rule as the GitHub producer: apply it only to text
    the-loop composed.
    """
    if JIRA_SELF_MARKER in body:
        return body
    text = (
        body.replace(f"\n\n{_GITHUB_STAMP}", "")
        .replace(_GITHUB_STAMP, "")
        .replace(SELF_COMMENT_MARKER, "")
    )
    return f"{text.rstrip()}\n\n{JIRA_SELF_ATTRIBUTION}\n"


def mark_relayed_on_jira(body: str) -> str:
    """A relay's body for Jira: the relay marker, never the agent marker.

    Apply it only to a relay the ledger composed (``relay_body``): the record of
    an authorized person's gate answer or control command from another channel.
    Idempotent. Keywords in the body are left intact — the ingress acts on them.
    """
    if JIRA_RELAY_MARKER in body:
        return body
    return f"{body.rstrip()}\n\n{JIRA_RELAY_ATTRIBUTION}\n"


def jira_comment_origin(
    body: Optional[str], author_id: str, service_account: str
) -> str:
    """Whose words a Jira comment is: :data:`ORIGIN_SELF`, ``RELAY`` or ``HUMAN``.

    * any self-marker (the Jira one, or GitHub's) → the-loop's own, whoever posted;
    * by the service account (``service_account``, from ``myself``) → a **relay**
      when it carries :data:`JIRA_RELAY_MARKER`, else the-loop's own;
    * anyone else → a human's, judged by its own author — a relay marker typed by
      a person grants nothing.

    ``service_account`` empty (``myself`` could not be read) makes nothing a
    relay: the comment is then judged as a person's, by an author that is on no
    allow-list unless the operator put it there.
    """
    text = body or ""
    if is_self_authored(text, provider="jira"):
        return ORIGIN_SELF
    if service_account and author_id == service_account:
        return ORIGIN_RELAY if JIRA_RELAY_MARKER in text else ORIGIN_SELF
    return ORIGIN_HUMAN


def is_authorized_on(
    provider: str, actor: Optional[str], principals: Sequence["Principal"]
) -> bool:
    """Whether ``actor`` is on the allow-list **for** ``provider`` (issue-475, R7).

    The exact id against :func:`~the_loop.identity.ids_for` on that provider's
    channel. On ``jira`` the id is the Cloud ``accountId`` or the Data Center
    user ``key``, and a **missing** actor is unauthorized: GitHub's "no actor is a
    CI event" exemption (:func:`is_authorized`) does not carry over (R7.2). On
    ``github`` this is :func:`is_authorized` over the GitHub logins, unchanged.
    """
    from .identity import ids_for

    if provider == "github":
        return is_authorized(actor, ids_for(principals, "github"))
    if not actor:
        return False
    return actor in set(ids_for(principals, provider))


def gate_authorized_users(
    github_logins: Sequence[str],
    principals: Sequence["Principal"],
    jira: bool = False,
) -> List[str]:
    """The identities a human gate accepts: the GitHub logins, as always, then —
    with Jira configured or Jira ids listed — every listed Jira id as
    ``jira:<id>`` and :data:`JIRA_RELAY_GATE_AUTHOR` (issue-475).

    A GitHub-only deployment gets exactly ``github_logins``.
    """
    from .identity import ids_for

    out = list(github_logins)
    jira_ids = ids_for(principals, "jira")
    if not (jira or jira_ids):
        return out
    out += [f"{JIRA_GATE_PREFIX}{native}" for native in jira_ids]
    out.append(JIRA_RELAY_GATE_AUTHOR)
    return out


def resolve_authorized_users(configured: Sequence) -> List[str]:
    """The effective allowlist: the **GitHub logins** in ``routing.authorizedUsers``.

    Since issue-309 an entry is a person — a bare login, or a mapping of channel name
    to native id (:mod:`the_loop.identity`) — and this function is what keeps every
    login consumer unchanged: it returns exactly the ``github`` ids, in order, and a
    person named on other channels only contributes nothing here.

    Deliberately has no fallback to the plugin config's ``ticketing.github.owner``
    (issue-63 review): who may trigger the daemon is a CLI-config concern, same as
    which repos it watches — the plugin config is for the Claude/Cursor plugin only.
    An empty list fails closed — callers should warn about that.
    """
    from .identity import github_logins, parse_authorized_users

    return github_logins(parse_authorized_users(list(configured or [])))


def is_authorized(actor: Optional[str], authorized: Sequence[str]) -> bool:
    """Whether ``actor``'s action may be an input the-loop acts on.

    ``actor is None`` (no identifiable human actor — e.g. a CI event) is allowed.
    A named actor is allowed only when present in ``authorized``; an empty
    allowlist therefore denies every human-authored action (fail closed).
    """
    if not actor:
        return True
    return actor in set(authorized)
