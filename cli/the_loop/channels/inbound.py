"""The inbound pipeline: map → drop own → authorize → classify → grant → publish.

Order is load-bearing (D6, issue-245; §5 of the issue-309 design). The **record on
the ledger lands before any delivery** because the work item is the source of truth
— a decision must reach the ticket even when no session is left to deliver to. The
record carries an envelope naming the channel and the person, so both ingresses know
it for what it is; a ``work-item.reply`` record also carries the self-authored
marker, so it is processed exactly once — here — and never again as a ticket event.

What a message *may become* is the channel's ``publish`` grant, read from the
catalog (:mod:`.events`). A message classifies into exactly one type, and a type the
channel is not granted is **dropped, never downgraded**: a control keyword typed on a
channel without the grant is not delivered to the agent as prose.

Two of the grantable types have no handler here at all. ``gate.feedback`` and
``control.command`` stop at the ledger record — unmarked, keywords intact — because
the ledger's own ingress is what classifies a gate answer and executes a control
keyword, through the very seams a typed GitHub comment goes through. That is how a
channel advances the loop: *through the ledger, never around it* (decision-103 D1).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

from .. import eventlog
from ..identity import principal_for
from ..standing import parse_standing_ref
from .base import ChannelError, Event, InboundReply
from .bus import publish
from .github import GitHubLedger
from .slack import (
    ACTION_PREFIX,
    SlackBotChannel,
    SlackChannelConfig,
    slack_state_path,
)
from .state import ChannelState

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "classify",
    "handle_socket_action",
    "handle_socket_event",
    "poll_once",
    "process_kickoff",
    "process_reply",
]


def _control_config(cli_config: Optional[Mapping]):
    from ..control import ControlConfig

    routing = (dict(cli_config or {}).get("routing") or {}) if cli_config else {}
    return ControlConfig.from_mapping(
        (routing or {}).get("control") or {} if isinstance(routing, Mapping) else {}
    )


def _at_human_gate(work_item: str, cli_config: Optional[Mapping]) -> bool:
    """Whether ``work_item``'s graph is parked at a human-actor node.

    A read of state the daemon already keeps — the session's checkout, through
    the registry, then the graph coupling's read-only ``context``. No session,
    no coupling, no graph: **not** at a gate, which is the fail-closed direction
    (the message is a reply, the default grant).
    """
    if not work_item or parse_standing_ref(work_item):
        return False
    try:
        from ..core.sessions import _registry_dir
        from ..graphlink import GraphLink, GraphLinkConfig
        from ..sessions import SessionRegistry, WorkItemRef

        config = dict(cli_config or {})
        routing = config.get("routing") or {}
        registry = SessionRegistry(_registry_dir(config, ""))
        item = WorkItemRef.parse(work_item)
        record = registry.record_owning(item)
        if record is None or not record.cwd:
            return False
        link = GraphLink(GraphLinkConfig.from_mapping(routing.get("graph") or {}))
        context = link.context(item, record.cwd)
    except Exception as exc:  # noqa: BLE001 — a graph fault is "not at a gate"
        logger.debug("could not read the graph for %s: %s", work_item, exc)
        return False
    if context is None:
        return False
    gate = getattr(context, "at_human_gate", False)
    return bool(gate() if callable(gate) else gate)


def classify(reply: InboundReply, cli_config: Optional[Mapping]) -> str:
    """The one event type this message is (R2.3), in a fixed order:

    1. a control keyword → ``control.command`` (an approval word inside a control
       comment must not become a gate answer);
    2. the work item parked at a human gate → ``gate.feedback``;
    3. otherwise → ``work-item.reply``.
    """
    if reply.top_level:
        return "work-item.create"
    from ..control import parse_command

    if parse_command(reply.text, _control_config(cli_config)).command:
        return "control.command"
    if _at_human_gate(reply.work_item, cli_config):
        return "gate.feedback"
    return "work-item.reply"


def _drop(reply: InboundReply, reason: str, level: str = "info", **fields) -> Dict:
    eventlog.emit(
        "channel.dropped",
        level=level,
        channel=reply.channel,
        reason=reason,
        work_item=reply.work_item or None,
        thread=reply.thread or None,
        **fields,
    )
    return {"outcome": reason}


def process_reply(
    reply: InboundReply,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    channel: Optional[SlackBotChannel] = None,
) -> Dict[str, Any]:
    """One reply through the pipeline. Returns the outcome; never raises."""
    if reply.top_level:
        return process_kickoff(
            reply, config, cli_config, channel=channel, post_comment=post_comment
        )
    if not reply.work_item:
        return _drop(reply, "unmapped")
    if reply.is_bot:
        # The Slack-side half of loop prevention (R4.5): a bot — the-loop's own
        # bot included — never speaks *to* the loop.
        return _drop(reply, "self-authored")
    if not config.authorized_users or reply.author not in set(config.authorized_users):
        # Fail closed (R5.1): an empty allow-list denies everyone, and an
        # unauthorized reply is neither delivered nor recorded — the record
        # would be a ticket write on an attacker's behalf.
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)

    event_type = classify(reply, cli_config)
    if event_type not in config.publish:
        # Dropped, never downgraded (R2.3): a keyword the channel may not run is
        # not handed to the agent as prose either.
        return _drop(
            reply,
            "unpublishable-event",
            level="warning",
            actor=reply.author,
            kind=event_type,
        )
    eventlog.emit(
        "channel.reply_received",
        channel=reply.channel,
        work_item=reply.work_item,
        actor=reply.author,
        kind=event_type,
    )
    actor = principal_for(config.principals, reply.channel, reply.author)
    event = Event(
        event_type=event_type,
        work_item=reply.work_item,
        text=reply.text,
        source=reply.channel,
        actor=actor,
        detail={"thread": reply.thread},
    )
    recorded = _record(event, reply, cli_config, post_comment)
    if event_type != "work-item.reply":
        # The record IS the request: the ledger's ingress classifies a gate
        # answer and executes a control keyword. Delivering here too would hand
        # the session the text twice and bypass the dispatcher's control seam.
        return {"outcome": "processed", "event": event_type, "mirrored": recorded}
    delivered = _deliver(reply, cli_config, deliver)
    return {
        "outcome": "processed",
        "event": event_type,
        "mirrored": recorded,
        "delivered": delivered,
    }


def _record(
    event: Event,
    reply: InboundReply,
    cli_config: Optional[Mapping],
    post_comment: Optional[Callable],
) -> bool:
    if parse_standing_ref(reply.work_item):
        # A standing session (issue-277) has no ticket, so there is nothing to
        # record onto. The paper trail does not vanish with the comment — it
        # moves to the event log, which is why this is recorded rather than
        # silently skipped.
        eventlog.emit(
            "channel.mirror_skipped",
            channel=reply.channel,
            work_item=reply.work_item,
            reason="standing-session",
        )
        return False
    ledger = GitHubLedger(cli_config, post_comment=post_comment)
    result = publish(event, cli_config, channels=[], ledger=ledger).record
    ok = bool(result and result.ok)
    if ok:
        eventlog.emit(
            "channel.mirrored",
            channel=reply.channel,
            work_item=reply.work_item,
            actor=reply.author,
            kind=event.event_type,
        )
    else:
        eventlog.emit(
            "channel.mirror_failed",
            level="warning",
            channel=reply.channel,
            work_item=reply.work_item,
            error=(result.error if result else None) or None,
        )
    return ok


def _standing_deliverer() -> Callable:
    """``core.standing.say_standing`` behind ``_deliver``'s calling convention.

    The two deliveries take the same five arguments and differ only in what
    identifies the target and whether a ticket is involved — so the adapter is
    here rather than as a branch inside :func:`_deliver`, which stays one code
    path with one set of failure semantics.
    """
    from ..core import standing as core_standing

    def deliver(ref, text, actor="", comment=True, config=None):
        del comment  # a standing session has no ticket to record a reply on
        return core_standing.say_standing(
            parse_standing_ref(ref) or ref, text, actor=actor, config=config
        )

    return deliver


def _deliver(
    reply: InboundReply,
    cli_config: Optional[Mapping],
    deliver: Optional[Callable],
) -> bool:
    if deliver is None and parse_standing_ref(reply.work_item):
        # The other namespace's delivery (issue-277). Bound late for the same
        # reason the work-item one is: a test or embedder patching
        # ``the_loop.core.standing.say_standing`` is honoured.
        deliver = _standing_deliverer()
    if deliver is None:
        # Call-time binding, so embedders and tests patching
        # ``the_loop.core.sessions.reply_session`` are always honoured.
        from ..core import sessions as core_sessions

        deliver = core_sessions.reply_session
    try:
        result = deliver(
            reply.work_item,
            reply.text,
            actor=f"{reply.channel}:{reply.author}",
            comment=False,  # the ledger record is the ticket's copy (D6)
            config=dict(cli_config or {}),
        )
    except (LookupError, ValueError) as exc:
        # reply_session's refusals: no session, paused, dead pane. The record
        # already carries the answer; record and move on (R5.4).
        eventlog.emit(
            "channel.dropped",
            level="warning",
            channel=reply.channel,
            reason="undeliverable",
            work_item=reply.work_item,
            error=str(exc),
        )
        return False
    except Exception as exc:  # transport trouble — same posture
        eventlog.emit(
            "channel.dropped",
            level="warning",
            channel=reply.channel,
            reason="undeliverable",
            work_item=reply.work_item,
            error=str(exc),
        )
        return False
    delivered = bool(result.get("delivered")) if isinstance(result, dict) else True
    return delivered


# -- kickoff (R6.5) ----------------------------------------------------------------


def process_kickoff(
    reply: InboundReply,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    *,
    channel: Optional[SlackBotChannel] = None,
    post_comment: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """A top-level message → ``work-item.create`` → the ledger opens the issue →
    the thread is bound to it and told the link. Never raises."""
    if reply.is_bot:
        return _drop(reply, "self-authored")
    if "work-item.create" not in config.publish:
        return _drop(reply, "unpublishable-event", kind="work-item.create")
    if not config.kickoff_repo:
        # Both the grant and a target (A6): there is no sensible inferred answer
        # to "which repository does this DM become an issue in".
        return _drop(reply, "kickoff-disabled", level="warning")
    if not config.authorized_users or reply.author not in set(config.authorized_users):
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)
    if not reply.text.strip():
        return _drop(reply, "unmapped", actor=reply.author)
    actor = principal_for(config.principals, reply.channel, reply.author)
    event = Event(
        event_type="work-item.create",
        work_item="",
        text=reply.text,
        source=reply.channel,
        actor=actor,
        detail={
            "repo": config.kickoff_repo,
            "labels": ",".join(config.kickoff_labels),
            "thread": reply.thread,
        },
    )
    ledger = GitHubLedger(
        cli_config, post_comment=post_comment, create_issue=create_issue
    )
    result = publish(event, cli_config, channels=[], ledger=ledger).record
    if not (result and result.ok and result.ref):
        return _drop(
            reply,
            "create-failed",
            level="warning",
            actor=reply.author,
            error=(result.error if result else None) or None,
        )
    bot = channel or SlackBotChannel(config, slack_state_path(cli_config))
    bot.bind(reply.thread, result.ref, reply.channel_id, origin="kickoff")
    link = f" — {result.url}" if result.url else ""
    bot.say(
        reply.thread,
        f"Opened {result.ref}{link}. This thread is now that work item's "
        "conversation — replies here reach it.",
        reply.channel_id,
    )
    eventlog.emit(
        "channel.created",
        channel=reply.channel,
        work_item=result.ref,
        actor=reply.author,
        thread=reply.thread,
    )
    return {"outcome": "created", "workItem": result.ref, "url": result.url}


# -- transports ------------------------------------------------------------------


def poll_once(
    cli_config: Optional[Mapping],
    *,
    client_factory: Optional[Callable] = None,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One read cycle over every bound thread — and, with the grant, the
    channel's top-level messages (R4.1, R6.5). Never raises."""
    config = SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled:
        return {"skipped": "channels.slack is not enabled", "replies": 0}
    if config.read_mode != "poll":
        return {
            "skipped": f"channels.slack.read.mode is {config.read_mode!r}, not 'poll'",
            "replies": 0,
        }
    channel = SlackBotChannel(
        config, slack_state_path(cli_config), client_factory=client_factory
    )
    try:
        replies = channel.fetch_replies()
        kickoffs = channel.fetch_kickoffs()
    except ChannelError as exc:
        logger.warning("channels poll skipped: %s", exc)
        return {"skipped": str(exc), "replies": 0}
    summary: Dict[str, Any] = {
        "replies": len(replies) + len(kickoffs),
        "processed": 0,
        "delivered": 0,
        "created": 0,
        "dropped": 0,
    }
    for reply in replies:
        outcome = process_reply(
            reply,
            config,
            cli_config,
            post_comment=post_comment,
            deliver=deliver,
            channel=channel,
        )
        # The cursor advances whatever the outcome: processed at most once
        # (R4.6). A failed record/delivery is a recorded failure, not a replay.
        channel.advance(reply.thread, reply.ts)
        if outcome["outcome"] == "processed":
            summary["processed"] += 1
            summary["delivered"] += 1 if outcome.get("delivered") else 0
        else:
            summary["dropped"] += 1
    for message in kickoffs:
        outcome = process_kickoff(
            message,
            config,
            cli_config,
            channel=channel,
            post_comment=post_comment,
            create_issue=create_issue,
        )
        # Advanced whatever happened: a retried create would open a second issue.
        channel.advance_kickoff(message.ts)
        if outcome["outcome"] == "created":
            summary["created"] += 1
        else:
            summary["dropped"] += 1
    return summary


def handle_socket_event(
    event: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One Socket Mode ``message`` event through the same pipeline (R4.2).

    The bindings decide relevance (R4.4): a message outside a bound thread is
    dropped as ``unmapped`` — unless it is a top-level message in the configured
    channel and the channel holds the ``work-item.create`` grant, in which case
    it is a kickoff candidate through the same function the poll read uses.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    state = ChannelState.load(state_path)
    ts = str(event.get("ts") or "")
    thread = str(event.get("thread_ts") or "")
    channel_id = str(event.get("channel") or "")
    is_bot = bool(event.get("bot_id")) or event.get("subtype") == "bot_message"
    if (not thread or thread == ts) and channel_id == config.channel:
        if config.kickoff_enabled and not state.work_item_for(ts):
            reply = InboundReply(
                channel="slack",
                work_item="",
                author=str(event.get("user") or ""),
                text=str(event.get("text") or ""),
                thread=ts,
                ts=ts,
                is_bot=is_bot,
                top_level=True,
                channel_id=channel_id,
            )
            return process_kickoff(
                reply,
                config,
                cli_config,
                post_comment=post_comment,
                create_issue=create_issue,
            )
    work_item = state.work_item_for(thread) or "" if thread else ""
    reply = InboundReply(
        channel="slack",
        work_item=work_item,
        author=str(event.get("user") or ""),
        text=str(event.get("text") or ""),
        thread=thread,
        ts=ts,
        is_bot=is_bot,
        channel_id=channel_id,
    )
    outcome = process_reply(
        reply, config, cli_config, post_comment=post_comment, deliver=deliver
    )
    if work_item and reply.ts:
        # Shared with the poll transport (R4.6): a mode switch cannot
        # double-process what the socket already handled. Under the state
        # lock (issue-312): a cursor advance never overwrites a binding a
        # writer in another process saved beside it.
        with ChannelState.locked(state_path) as fresh:
            fresh.advance(thread, reply.ts)
            fresh.save(state_path)
    return outcome


def handle_socket_action(
    payload: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
) -> Dict[str, Any]:
    """A Block Kit ``block_actions`` press → that member's reply carrying the
    button's ``value`` as its text (R4.3, A9).

    Only actions the-loop rendered (``action_id`` under :data:`ACTION_PREFIX`) are
    read; the value is *text*, judged by the ordinary pipeline with the ordinary
    authorization — a crafted payload buys nothing a typed message would not.
    """
    actions = [
        a
        for a in (payload.get("actions") or [])
        if isinstance(a, Mapping)
        and str(a.get("action_id") or "").startswith(ACTION_PREFIX)
        and str(a.get("value") or "").strip()
    ]
    if not actions:
        return {"outcome": "ignored"}
    message = payload.get("message") or {}
    container = payload.get("container") or {}
    thread = str(
        message.get("thread_ts")
        or container.get("thread_ts")
        or message.get("ts")
        or container.get("message_ts")
        or ""
    )
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    state = ChannelState.load(state_path)
    reply = InboundReply(
        channel="slack",
        work_item=state.work_item_for(thread) or "" if thread else "",
        author=str((payload.get("user") or {}).get("id") or ""),
        text=str(actions[0].get("value")),
        thread=thread,
        ts=str(payload.get("action_ts") or container.get("message_ts") or ""),
        channel_id=str((payload.get("channel") or {}).get("id") or ""),
    )
    return process_reply(
        reply, config, cli_config, post_comment=post_comment, deliver=deliver
    )
