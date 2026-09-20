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
from typing import Any, Dict, List, Optional, Tuple

from .. import eventlog
from ..comments import post_issue_comment
from ..control import ADD_CHANNEL, REMOVE_CHANNEL, command_comment
from ..sessions import WorkItemRef
from ..state import legacy_layout
from ..workchannels import (
    DEFAULT_LISTEN,
    LISTEN_MODES,
    ChannelRef,
    ChannelTakenError,
    CollaborationChannelStore,
    describe_refusal,
    parse_channel_ref,
    resolve_channel_ref,
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
    listen: str = DEFAULT_LISTEN,
) -> Dict[str, Any]:
    """Apply ``verb`` to each of ``channels`` on one work item, end to end.

    Every ref is validated before **anything** is written, so a typo in the second
    channel does not leave the first half-applied: the call either refuses (exit 2,
    nothing changed, nothing posted) or applies all of them. ``listen`` is the mode
    a declaration is written with (issue-389 R2.1); re-declaring a room with another
    mode replaces it.
    """
    if verb not in CHANNEL_VERBS:
        raise ValueError(f"unknown channel verb {verb!r} (one of {CHANNEL_VERBS})")
    if listen not in LISTEN_MODES:
        raise ValueError(
            f"unknown listen mode {listen!r} (one of {', '.join(LISTEN_MODES)})"
        )
    work_item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    canonical: List[Tuple[ChannelRef, str]] = []
    for raw in channels:
        channel = parse_channel_ref(raw)
        if channel is None:
            raise ValueError(describe_refusal(raw))
        # A name becomes an id here, before anything is written (PR #376 review).
        # Inside the same validate-everything-first loop as the grammar check, so
        # a second channel that cannot be resolved leaves the first unapplied.
        resolved, name = resolve_channel_ref(channel, config)
        if all(resolved != entry for entry, _ in canonical):
            canonical.append((resolved, name))
    if not canonical:
        raise ValueError("name at least one channel, e.g. slack@#tmp-issue-375")

    store = _store(config, portable_dir)
    actor = _local_actor()
    messages: List[Dict[str, str]] = []
    applied: List[str] = []
    unchanged: List[str] = []

    for channel, name in canonical:
        replaced = None
        if verb == ADD_CHANNEL:
            try:
                changed, replaced = store.add(
                    work_item,
                    channel,
                    actor=actor,
                    source="cli",
                    name=name,
                    listen=listen,
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
                "text": _line(effect, channel, work_item, replaced, listen),
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
            listen=listen if verb == ADD_CHANNEL else None,
            effect=effect,
        )

    if comment and applied:
        _announce(work_item, verb, actor, applied, messages, config, listen)
    if verb == ADD_CHANNEL and applied:
        _confirm_room(work_item, config, messages)

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


def _line(
    effect: str,
    channel: ChannelRef,
    work_item: WorkItemRef,
    replaced,
    listen: str = DEFAULT_LISTEN,
) -> str:
    if effect == "declared":
        moved = f" (it was {replaced.ref})" if replaced else ""
        hears = (
            "every message there reaches the work item"
            if listen == "all"
            else "messages there reach the work item when the-loop is mentioned"
        )
        return (
            f"{channel.ref} is now {work_item.ref}'s collaboration channel{moved}, "
            f"listening to {listen}: its updates are posted there, and {hears}"
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


def _confirm_room(
    work_item: WorkItemRef, cli_conf: Optional[dict], messages: List[Dict[str, str]]
) -> None:
    """Open the work item's conversation in the room just declared (issue-397 O1),
    so the room hears that it is now the conversation at the declaration rather
    than at the item's first update. Best-effort, exactly as the dispatcher's
    :meth:`_confirm_room`: a config with no ``channels`` section opens nothing,
    the bus's open is idempotent, and a failure is reported, never raised — the
    declaration stands either way.
    """
    if not cli_conf or not cli_conf.get("channels"):
        return
    from ..channels.bus import open_conversation

    try:
        results = open_conversation(work_item.ref, cli_conf)
    except Exception as exc:  # noqa: BLE001 — a confirmation never undoes a declaration
        logger.warning("could not confirm %s's room: %s", work_item.ref, exc)
        return
    for result in results:
        if result.ok:
            messages.append(
                {
                    "stream": "out",
                    "text": f"confirmed the room on {result.channel}: {work_item.ref}'s "
                    "conversation is open there",
                }
            )
        else:
            messages.append(
                {
                    "stream": "err",
                    "text": f"could not confirm the room on {result.channel}: "
                    f"{result.error} (the declaration stands; the room hears "
                    "about it at the next update)",
                }
            )


def _announce(
    work_item: WorkItemRef,
    verb: str,
    actor: str,
    channels: List[str],
    messages: List[Dict[str, str]],
    cli_conf: Optional[dict] = None,
    listen: str = DEFAULT_LISTEN,
) -> None:
    """Record the declaration on the ticket (best-effort — never fails the write).

    The mode is spelled back only when it is not the default: the thread then
    reads exactly as the person would have typed it, and a room declared without
    a mode reads as one.
    """
    config = _control_config(cli_conf)
    for ref in channels:
        body = command_comment(
            verb,
            config,
            actor=actor,
            subject=ref,
            invocation=f"the-loop {verb}",
            listen=listen if (verb == ADD_CHANNEL and listen != DEFAULT_LISTEN) else "",
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
