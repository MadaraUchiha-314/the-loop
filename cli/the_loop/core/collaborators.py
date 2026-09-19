"""Core capability: work-item collaborators (issue-307).

The CLI half of the two verbs the control keywords already carry. It lives here,
beside :mod:`the_loop.core.sessions`'s control verbs, for the reason
``the-loop ask`` states for itself: the command layer is a renderer, so a route or
an MCP tool later is a **binding, not a port**.

Order is the one ``control_session`` established, and for the same reason: the
**local effect first**, the ticket comment last. The comment is a *report* of what
happened, so a failing ``gh`` never leaves the thread claiming a grant the-loop did
not make — and the grant itself is not lost because GitHub was unreachable.

Authorization on this path is **shell access to the machine running the-loop**,
exactly as it is for ``the-loop sessions start|stop|pause|resume|cleanup``. The
comment path's stricter test — a named login in ``routing.authorizedUsers`` — is the
webhook dispatcher's, because that is where an untrusted author can reach.

A collaborator may also be named by Slack (issue-389): ``--slack <id|@handle>``. A
handle is resolved to a member id through :class:`the_loop.channels.directory.
SlackDirectory` **before anything is written**, exactly as ``add-channel`` resolves
a channel name, and one that does not resolve refuses the whole call — the roster
stores ids only, so an unresolvable entry can never authorize whoever holds a
handle tomorrow (abuse case A11).

Spec: docs/specs/issue-307/design.md §5; docs/specs/issue-389/design.md §5.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .. import eventlog
from ..channels.directory import SlackDirectory, is_member_id
from ..collaborators import CollaboratorStore, normalize_login, slack_token
from ..comments import post_issue_comment
from ..control import ADD_COLLABORATOR, REMOVE_COLLABORATOR, command_comment
from ..sessions import WorkItemRef
from ..state import legacy_layout
from .sessions import _control_config, _layout, _local_actor

logger = logging.getLogger("the-loop.core.collaborators")

#: The two verbs this module applies — the same constants the comment path parses,
#: so the CLI cannot drift into a third spelling.
COLLABORATOR_VERBS = (ADD_COLLABORATOR, REMOVE_COLLABORATOR)

__all__ = ["COLLABORATOR_VERBS", "list_collaborators", "manage_collaborators"]


def _store(config: Optional[dict], portable_dir: str = "") -> CollaboratorStore:
    layout = _layout(config)
    return CollaboratorStore(
        portable_dir or layout.portable_dir, legacy=legacy_layout(layout)
    )


def list_collaborators(
    ref: str, config: Optional[dict] = None, portable_dir: str = ""
) -> Dict[str, Any]:
    """The work item's roster, as data (``ValueError`` on a malformed ref)."""
    work_item = WorkItemRef.parse(ref)
    return {
        "workItem": work_item.ref,
        "collaborators": [
            record.to_dict() for record in _store(config, portable_dir).list(work_item)
        ],
    }


def manage_collaborators(
    ref: str,
    verb: str,
    logins: List[str],
    comment: bool = True,
    config: Optional[dict] = None,
    portable_dir: str = "",
    slack: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Apply ``verb`` to each of ``logins`` and ``slack`` on one work item, end to end.

    Every login is validated, and every Slack handle resolved, before **anything**
    is written, so a typo in the third name does not leave the first two
    half-applied: the call either refuses (exit 2, nothing changed, nothing posted)
    or applies all of them. Each entry of either list is one grant; the CLI does
    not know that ``@dana`` and ``--slack @dana`` are one person, and says so by
    posting one comment per grant.
    """
    if verb not in COLLABORATOR_VERBS:
        raise ValueError(
            f"unknown collaborator verb {verb!r} (one of {COLLABORATOR_VERBS})"
        )
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    # Each subject is `(login, slack)` with exactly one of the two set.
    canonical: List[Tuple[str, str]] = []
    for raw in logins:
        login = normalize_login(raw)
        if not login:
            raise ValueError(
                f"not a GitHub login: {raw!r} (expected @login — letters, digits and "
                "single interior hyphens, at most 39 characters)"
            )
        if (login, "") not in canonical:
            canonical.append((login, ""))
    directory = None
    for raw in slack or []:
        text = str(raw or "").strip()
        if is_member_id(text):
            member = text  # an id costs no lookup — and no token
        else:
            # A handle becomes an id here, before anything is written, through
            # the same directory `add-channel` resolves a channel name with. A
            # miss refuses the call: the roster stores ids only (A11).
            if directory is None:
                directory = SlackDirectory(config)
            member = directory.user_id(text)
            if not member:
                raise ValueError(
                    f"no Slack member with the handle {text!r} that this bot can "
                    "see — check the spelling and make sure the app carries the "
                    "`users:read` scope. Their member id (U…, under 'Copy member "
                    "ID' in their profile) always works"
                )
        if ("", member) not in canonical:
            canonical.append(("", member))
    if not canonical:
        raise ValueError(
            "name at least one collaborator, e.g. @octocat or --slack U0123ABCD"
        )

    store = _store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []
    applied: List[str] = []
    unchanged: List[str] = []

    for login, member in canonical:
        label = f"@{login}" if login else slack_token(member)
        if verb == ADD_COLLABORATOR:
            changed = store.add(
                work_item, login=login, slack=member, actor=actor, source="cli"
            )
            effect = "granted" if changed else "already-granted"
        else:
            changed = store.remove(work_item, login=login, slack=member)
            effect = "revoked" if changed else "not-a-collaborator"
        (applied if changed else unchanged).append(label)
        messages.append(
            {
                "stream": "out" if changed else "err",
                "text": _line(effect, label, work_item),
            }
        )
        eventlog.emit(
            "control.command",
            work_item=work_item.ref,
            command=verb,
            source="cli",
            actor=actor or None,
            collaborator=login or None,
            slack=member or None,
            effect=effect,
        )

    if comment and applied:
        # Only what actually changed is announced: a comment saying "granted" for a
        # login that was already on the roster would put a second grant in the thread
        # that never happened.
        _announce(work_item, verb, actor, applied, messages, config)

    roster = store.list(work_item)
    return {
        "verb": verb,
        "workItem": work_item.ref,
        "applied": applied,
        "unchanged": unchanged,
        "collaborators": [record.login for record in roster if record.login],
        "slackIds": [record.slack for record in roster if record.slack],
        # Nothing to do is not a failure of the machine, but it is not what the
        # operator asked for either — the same exit-1 "noop" the control verbs use.
        "exitCode": 0 if applied else 1,
        "messages": messages,
        "output": "\n".join(message["text"] for message in messages),
    }


def _line(effect: str, label: str, work_item: WorkItemRef) -> str:
    """``label`` is the subject as a person reads it: ``@dana`` or ``slack:U…``."""
    if effect == "granted":
        return (
            f"{label} is now a collaborator on {work_item.ref}: their comments on it "
            "reach the session as input (they cannot start, stop or approve anything)"
        )
    if effect == "revoked":
        return f"{label} is no longer a collaborator on {work_item.ref}"
    if effect == "already-granted":
        return f"{label} is already a collaborator on {work_item.ref}; nothing changed"
    return f"{label} is not a collaborator on {work_item.ref}; nothing changed"


def _announce(
    work_item: WorkItemRef,
    verb: str,
    actor: str,
    labels: List[str],
    messages: List[Dict[str, str]],
    cli_conf: Optional[dict] = None,
) -> None:
    """Record the grant on the ticket (best-effort — never fails the grant).

    ``labels`` are the subjects as the keyword spells them (``@dana``,
    ``slack:U…``), which is what :func:`command_comment` takes.
    """
    config = _control_config(cli_conf)
    for label in labels:
        body = command_comment(
            verb,
            config,
            actor=actor,
            subject=label,
            invocation=f"the-loop {verb}",
        )
        ok, error = post_issue_comment(work_item, body, gh_binary=config.gh_binary)
        if ok:
            messages.append(
                {
                    "stream": "out",
                    "text": (
                        f"commented {config.keyword(verb)!r} {label} on {work_item.ref}"
                    ),
                }
            )
            eventlog.emit(
                "control.announced",
                work_item=work_item.ref,
                command=verb,
                collaborator=label,
            )
            continue
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"note: could not comment on {work_item.ref} ({error}); the "
                    "roster was still updated locally"
                ),
            }
        )
        eventlog.emit(
            "control.announce_failed",
            level="warning",
            work_item=work_item.ref,
            command=verb,
            collaborator=label,
            error=error,
        )
