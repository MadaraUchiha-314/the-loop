"""The inbound pipeline: map → drop own → authorize → mirror → deliver (D6).

Order is load-bearing. The mirror lands **before** delivery because the work
item is the source of truth — a decision must reach the ticket even when no
session is left to deliver to. The mirror carries the self-authored marker, so
both ingress paths drop it before their authz checks even run (issue-64/104):
the reply is processed exactly once, here, and never again as a ticket event.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

from .. import eventlog
from ..authz import mark_self_authored
from ..redact import defang_control_keywords, scrub
from ..standing import parse_standing_ref
from .base import ChannelError, InboundReply
from .slack import SlackBotChannel, SlackChannelConfig, slack_state_path
from .state import ChannelState

logger = logging.getLogger("the-loop.channels")

__all__ = ["handle_socket_event", "poll_once", "process_reply"]


def _control_keywords(cli_config: Optional[Mapping]) -> tuple:
    """Every control keyword this deployment recognises — defaults + configured."""
    from ..control import DEFAULT_KEYWORDS

    configured = (
        (dict(cli_config or {}).get("routing") or {}).get("control") or {}
    ).get("keywords") or {}
    keywords = dict(DEFAULT_KEYWORDS)
    if isinstance(configured, Mapping):
        keywords.update({str(k): str(v) for k, v in configured.items()})
    return tuple(keywords.values())


def _gh_binary(cli_config: Optional[Mapping]) -> str:
    section = (
        (dict(cli_config or {}).get("integrations") or {}).get("github") or {}
    ).get("cli") or {}
    return str(section.get("binary", "gh"))


def _mirror_body(reply: InboundReply, cli_config: Optional[Mapping]) -> str:
    """The-loop's own record of the reply — quoted, scrubbed, defanged, marked.

    The marker is licensed here because the-loop composed this comment (a
    report quoting the channel user, the ``_reply_report`` precedent) — and it
    is load-bearing: an unmarked copy of the answer would be forwarded by the
    poller into the very session the pipeline already delivered it to.
    """
    safe = defang_control_keywords(scrub(reply.text), _control_keywords(cli_config))
    quoted = "\n".join(f"> {line}" for line in (safe.splitlines() or [""]))
    return mark_self_authored(
        f"🗣️ **the-loop** — reply from `{reply.author}` on the **{reply.channel}** "
        "channel, recorded here as the answer of record:\n\n" + quoted
    )


def process_reply(
    reply: InboundReply,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One reply through the pipeline. Returns the outcome; never raises."""
    if not reply.work_item:
        eventlog.emit(
            "channel.dropped",
            channel=reply.channel,
            reason="unmapped",
            thread=reply.thread or None,
        )
        return {"outcome": "unmapped"}
    if reply.is_bot:
        # The Slack-side half of loop prevention (R4.5): a bot — the-loop's own
        # bot included — never speaks *to* the loop.
        eventlog.emit(
            "channel.dropped",
            channel=reply.channel,
            reason="self-authored",
            work_item=reply.work_item,
        )
        return {"outcome": "self-authored"}
    if not config.authorized_users or reply.author not in set(config.authorized_users):
        # Fail closed (R5.1): an empty allow-list denies everyone, and an
        # unauthorized reply is neither delivered nor mirrored — the mirror
        # would be a ticket write on an attacker's behalf.
        eventlog.emit(
            "channel.dropped",
            level="warning",
            channel=reply.channel,
            reason="unauthorized-actor",
            actor=reply.author,
            work_item=reply.work_item,
        )
        return {"outcome": "unauthorized-actor"}

    eventlog.emit(
        "channel.reply_received",
        channel=reply.channel,
        work_item=reply.work_item,
        actor=reply.author,
    )
    mirrored = _mirror(reply, cli_config, post_comment)
    delivered = _deliver(reply, cli_config, deliver)
    return {"outcome": "processed", "mirrored": mirrored, "delivered": delivered}


def _mirror(
    reply: InboundReply,
    cli_config: Optional[Mapping],
    post_comment: Optional[Callable],
) -> bool:
    from ..workitem import WorkItemRef

    if parse_standing_ref(reply.work_item):
        # A standing session (issue-277) has no ticket, so there is nothing to
        # mirror onto. The paper trail does not vanish with the comment — it
        # moves to the event log, which is why this is recorded rather than
        # silently skipped.
        eventlog.emit(
            "channel.mirror_skipped",
            channel=reply.channel,
            work_item=reply.work_item,
            reason="standing-session",
        )
        return False
    try:
        item = WorkItemRef.parse(reply.work_item)
    except ValueError as exc:
        eventlog.emit(
            "channel.mirror_failed",
            level="warning",
            channel=reply.channel,
            work_item=reply.work_item,
            error=str(exc),
        )
        return False
    if post_comment is None:
        from .. import comments

        post_comment = comments.post_issue_comment
    try:
        ok, error = post_comment(
            item, _mirror_body(reply, cli_config), gh_binary=_gh_binary(cli_config)
        )
    except Exception as exc:  # the writer is best-effort by contract
        ok, error = False, str(exc)
    if ok:
        eventlog.emit(
            "channel.mirrored",
            channel=reply.channel,
            work_item=reply.work_item,
            actor=reply.author,
        )
    else:
        eventlog.emit(
            "channel.mirror_failed",
            level="warning",
            channel=reply.channel,
            work_item=reply.work_item,
            error=error or None,
        )
    return bool(ok)


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
            comment=False,  # the mirror is the ticket record (D6)
            config=dict(cli_config or {}),
        )
    except (LookupError, ValueError) as exc:
        # reply_session's refusals: no session, paused, dead pane. The mirror
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


def poll_once(
    cli_config: Optional[Mapping],
    *,
    client_factory: Optional[Callable] = None,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One read cycle over every bound thread (R4.1). Never raises."""
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
    except ChannelError as exc:
        logger.warning("channels poll skipped: %s", exc)
        return {"skipped": str(exc), "replies": 0}
    summary: Dict[str, Any] = {
        "replies": len(replies),
        "processed": 0,
        "delivered": 0,
        "dropped": 0,
    }
    for reply in replies:
        outcome = process_reply(
            reply, config, cli_config, post_comment=post_comment, deliver=deliver
        )
        # The cursor advances whatever the outcome: processed at most once
        # (R4.6). A failed mirror/delivery is a recorded failure, not a replay.
        channel.advance(reply.thread, reply.ts)
        if outcome["outcome"] == "processed":
            summary["processed"] += 1
            summary["delivered"] += 1 if outcome.get("delivered") else 0
        else:
            summary["dropped"] += 1
    return summary


def handle_socket_event(
    event: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One Socket Mode ``message`` event through the same pipeline (R4.2).

    The bindings decide relevance (R4.4): a message outside a bound thread —
    including every top-level channel message — is dropped as ``unmapped``.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    state = ChannelState.load(state_path)
    thread = str(event.get("thread_ts") or "")
    work_item = state.work_item_for(thread) or "" if thread else ""
    reply = InboundReply(
        channel="slack",
        work_item=work_item,
        author=str(event.get("user") or ""),
        text=str(event.get("text") or ""),
        thread=thread,
        ts=str(event.get("ts") or ""),
        is_bot=bool(event.get("bot_id")) or event.get("subtype") == "bot_message",
    )
    outcome = process_reply(
        reply, config, cli_config, post_comment=post_comment, deliver=deliver
    )
    if work_item and reply.ts:
        # Shared with the poll transport (R4.6): a mode switch cannot
        # double-process what the socket already handled.
        state.advance(thread, reply.ts)
        state.save(state_path)
    return outcome
