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

Spec: docs/specs/issue-307/design.md §5.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .. import eventlog
from ..collaborators import CollaboratorStore, normalize_login
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
) -> Dict[str, Any]:
    """Apply ``verb`` to each of ``logins`` on one work item, end to end.

    Every login is validated before **anything** is written, so a typo in the third
    name does not leave the first two half-applied: the call either refuses (exit 2,
    nothing changed, nothing posted) or applies all of them.
    """
    if verb not in COLLABORATOR_VERBS:
        raise ValueError(
            f"unknown collaborator verb {verb!r} (one of {COLLABORATOR_VERBS})"
        )
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    canonical: List[str] = []
    for raw in logins:
        login = normalize_login(raw)
        if not login:
            raise ValueError(
                f"not a GitHub login: {raw!r} (expected @login — letters, digits and "
                "single interior hyphens, at most 39 characters)"
            )
        if login not in canonical:
            canonical.append(login)
    if not canonical:
        raise ValueError("name at least one collaborator, e.g. @octocat")

    store = _store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []
    applied: List[str] = []
    unchanged: List[str] = []

    for login in canonical:
        if verb == ADD_COLLABORATOR:
            changed = store.add(work_item, login, actor=actor, source="cli")
            effect = "granted" if changed else "already-granted"
        else:
            changed = store.remove(work_item, login)
            effect = "revoked" if changed else "not-a-collaborator"
        (applied if changed else unchanged).append(login)
        messages.append(
            {
                "stream": "out" if changed else "err",
                "text": _line(effect, login, work_item),
            }
        )
        eventlog.emit(
            "control.command",
            work_item=work_item.ref,
            command=verb,
            source="cli",
            actor=actor or None,
            collaborator=login,
            effect=effect,
        )

    if comment and applied:
        # Only what actually changed is announced: a comment saying "granted" for a
        # login that was already on the roster would put a second grant in the thread
        # that never happened.
        _announce(work_item, verb, actor, applied, messages, config)

    return {
        "verb": verb,
        "workItem": work_item.ref,
        "applied": applied,
        "unchanged": unchanged,
        "collaborators": [record.login for record in store.list(work_item)],
        # Nothing to do is not a failure of the machine, but it is not what the
        # operator asked for either — the same exit-1 "noop" the control verbs use.
        "exitCode": 0 if applied else 1,
        "messages": messages,
        "output": "\n".join(message["text"] for message in messages),
    }


def _line(effect: str, login: str, work_item: WorkItemRef) -> str:
    if effect == "granted":
        return (
            f"@{login} is now a collaborator on {work_item.ref}: their comments on it "
            "reach the session as input (they cannot start, stop or approve anything)"
        )
    if effect == "revoked":
        return f"@{login} is no longer a collaborator on {work_item.ref}"
    if effect == "already-granted":
        return f"@{login} is already a collaborator on {work_item.ref}; nothing changed"
    return f"@{login} is not a collaborator on {work_item.ref}; nothing changed"


def _announce(
    work_item: WorkItemRef,
    verb: str,
    actor: str,
    logins: List[str],
    messages: List[Dict[str, str]],
    cli_conf: Optional[dict] = None,
) -> None:
    """Record the grant on the ticket (best-effort — never fails the grant)."""
    config = _control_config(cli_conf)
    for login in logins:
        body = command_comment(
            verb,
            config,
            actor=actor,
            subject=login,
            invocation=f"the-loop {verb}",
        )
        ok, error = post_issue_comment(work_item, body, gh_binary=config.gh_binary)
        if ok:
            messages.append(
                {
                    "stream": "out",
                    "text": (
                        f"commented {config.keyword(verb)!r} @{login} on "
                        f"{work_item.ref}"
                    ),
                }
            )
            eventlog.emit(
                "control.announced",
                work_item=work_item.ref,
                command=verb,
                collaborator=login,
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
            collaborator=login,
            error=error,
        )
