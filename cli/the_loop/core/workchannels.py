"""Core capability: a work item's collaboration channels (issue-375).

The CLI half of the two control keywords, beside
:mod:`the_loop.core.collaborators` and shaped exactly like it: the command layer
is a renderer, so a control-plane route or an MCP tool later is a **binding, not a
port**.

Order is ``control_session``'s, for its reason: the **local effect first**, the
ticket comment last, so a failing ``gh`` never leaves the thread claiming a
declaration the-loop did not make.

Authorization on this path is **shell access to the machine running the-loop**, as
it is for every other CLI verb. The comment path's stricter test — a named login in
``routing.authorizedUsers`` — is the webhook dispatcher's, because that is where an
untrusted author can reach.

Spec: docs/specs/issue-375/design.md §4.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .. import eventlog
from ..comments import post_issue_comment
from ..control import ADD_CHANNEL, REMOVE_CHANNEL, command_comment
from ..sessions import WorkItemRef
from ..state import legacy_layout
from ..workchannels import (
    ChannelRef,
    ChannelTakenError,
    CollaborationChannelStore,
    describe_refusal,
    parse_channel_ref,
)
from .sessions import _control_config, _layout, _local_actor

logger = logging.getLogger("the-loop.core.workchannels")

#: The two verbs this module applies — the same constants the comment path parses,
#: so the CLI cannot drift into a third spelling.
CHANNEL_VERBS = (ADD_CHANNEL, REMOVE_CHANNEL)

__all__ = ["CHANNEL_VERBS", "list_channels", "manage_channels"]


def _store(config: Optional[dict], portable_dir: str = "") -> CollaborationChannelStore:
    layout = _layout(config)
    return CollaborationChannelStore(
        portable_dir or layout.portable_dir, legacy=legacy_layout(layout)
    )


def list_channels(
    ref: str, config: Optional[dict] = None, portable_dir: str = ""
) -> Dict[str, Any]:
    """The work item's declared channels, as data (``ValueError`` on a bad ref)."""
    work_item = WorkItemRef.parse(ref)
    return {
        "workItem": work_item.ref,
        "channels": [
            record.to_dict() for record in _store(config, portable_dir).list(work_item)
        ],
    }


def manage_channels(
    ref: str,
    verb: str,
    channels: List[str],
    comment: bool = True,
    config: Optional[dict] = None,
    portable_dir: str = "",
) -> Dict[str, Any]:
    """Apply ``verb`` to each of ``channels`` on one work item, end to end.

    Every ref is validated before **anything** is written, so a typo in the second
    channel does not leave the first half-applied: the call either refuses (exit 2,
    nothing changed, nothing posted) or applies all of them.
    """
    if verb not in CHANNEL_VERBS:
        raise ValueError(f"unknown channel verb {verb!r} (one of {CHANNEL_VERBS})")
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    canonical: List[ChannelRef] = []
    for raw in channels:
        channel = parse_channel_ref(raw)
        if channel is None:
            raise ValueError(describe_refusal(raw))
        if channel not in canonical:
            canonical.append(channel)
    if not canonical:
        raise ValueError("name at least one channel, e.g. slack@C0123ABCD")

    store = _store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []
    applied: List[str] = []
    unchanged: List[str] = []

    for channel in canonical:
        replaced = None
        if verb == ADD_CHANNEL:
            try:
                changed, replaced = store.add(
                    work_item, channel, actor=actor, source="cli"
                )
            except ChannelTakenError as exc:
                # Not the caller's typo but not a state change either: reported as
                # a refusal of THIS channel, with the rest of the list untouched.
                raise ValueError(str(exc)) from None
            effect = "declared" if changed else "already-declared"
        else:
            changed = store.remove(work_item, channel)
            effect = "undeclared" if changed else "not-a-channel"
        (applied if changed else unchanged).append(channel.ref)
        messages.append(
            {
                "stream": "out" if changed else "err",
                "text": _line(effect, channel, work_item, replaced),
            }
        )
        eventlog.emit(
            "control.command",
            work_item=work_item.ref,
            command=verb,
            source="cli",
            actor=actor or None,
            channel=channel.ref,
            replaced=replaced.ref if replaced else None,
            effect=effect,
        )

    if comment and applied:
        _announce(work_item, verb, actor, applied, messages, config)

    return {
        "verb": verb,
        "workItem": work_item.ref,
        "applied": applied,
        "unchanged": unchanged,
        "channels": [record.ref for record in store.list(work_item)],
        # Nothing to do is not a failure of the machine, but it is not what the
        # operator asked for either — the same exit-1 "noop" the control verbs use.
        "exitCode": 0 if applied else 1,
        "messages": messages,
        "output": "\n".join(message["text"] for message in messages),
    }


def _line(effect: str, channel: ChannelRef, work_item: WorkItemRef, replaced) -> str:
    if effect == "declared":
        moved = f" (it was {replaced.ref})" if replaced else ""
        return (
            f"{channel.ref} is now {work_item.ref}'s collaboration channel{moved}: its "
            "updates are posted there, and messages there from authorized users reach "
            "the work item"
        )
    if effect == "undeclared":
        return (
            f"{channel.ref} is no longer {work_item.ref}'s collaboration channel; "
            "its conversation goes back to the central channel"
        )
    if effect == "already-declared":
        return (
            f"{channel.ref} is already {work_item.ref}'s collaboration channel; "
            "nothing changed"
        )
    return f"{channel.ref} is not declared on {work_item.ref}; nothing changed"


def _announce(
    work_item: WorkItemRef,
    verb: str,
    actor: str,
    channels: List[str],
    messages: List[Dict[str, str]],
    cli_conf: Optional[dict] = None,
) -> None:
    """Record the declaration on the ticket (best-effort — never fails the write)."""
    config = _control_config(cli_conf)
    for ref in channels:
        body = command_comment(
            verb, config, actor=actor, subject=ref, invocation=f"the-loop {verb}"
        )
        ok, error = post_issue_comment(work_item, body, gh_binary=config.gh_binary)
        if ok:
            messages.append(
                {
                    "stream": "out",
                    "text": f"commented {config.keyword(verb)!r} {ref} on {work_item.ref}",
                }
            )
            eventlog.emit(
                "control.announced",
                work_item=work_item.ref,
                command=verb,
                channel=ref,
            )
            continue
        messages.append(
            {
                "stream": "err",
                "text": (
                    f"note: could not comment on {work_item.ref} ({error}); the "
                    "declaration was still recorded locally"
                ),
            }
        )
        eventlog.emit(
            "control.announce_failed",
            level="warning",
            work_item=work_item.ref,
            command=verb,
            channel=ref,
            error=error,
        )
