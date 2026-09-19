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

Whether a reply answers a gate is read from the graph **through the dispatcher's own
coupling** (issue-321, decision-109): the same control policy, control store and
registry the ingress reads with. A gate the pipeline *cannot* read — no session
record, no checkout, a fault — is not "no gate": with the ``gate.feedback`` grant the
reply is recorded unmarked and left to the ledger's ingress, which can; without the
grant it stays the marked mirror it always was.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from .. import eventlog
from ..identity import principal_for
from ..repos import declared_repositories
from ..standing import parse_standing_ref
from .base import ChannelError, Event, InboundReply, PostResult
from .bus import publish
from .github import GitHubLedger
from .kickoff import question_text, refusal_text, resolve_target
from .once import first_sight
from .slack import (
    ACTION_PREFIX,
    DECISION_VIEW_CALLBACK,
    GITHUB_COMMENT_LIMIT,
    MENTION_SHORTCUTS,
    decision_view,
    SlackBotChannel,
    SlackChannelConfig,
    _ts_key,
    action_value,
    is_kickoff_repo_action,
    kickoff_cursor_key,
    render_kickoff_question,
    render_reply_blocks,
    slack_state_path,
)
from .state import ChannelState, ChannelStores
from .verbs import KINDS, compose_keyword, help_text, parse_verb, strip_mention

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "BINDING_ACTS",
    "DELIVERED",
    "INPUT_ACTS",
    "Speaker",
    "classify",
    "handle_message_action",
    "handle_socket_action",
    "handle_socket_event",
    "handle_view_submission",
    "input_decision",
    "poll_once",
    "process_kickoff",
    "process_kickoff_answer",
    "process_reply",
    "speaker_for",
]

#: The acts a work item's collaborator may perform beside an authorized user
#: (issue-389 R7.2, decision-133 D7): they are *input*, which is what a
#: collaborator was defined to give (issue-307). Everything else binds the work
#: item and is an authorized user's alone.
INPUT_ACTS = frozenset({"work-item.reply", "context.added", "help"})
BINDING_ACTS = frozenset(
    {"decision.recorded", "control.command", "gate.feedback", "work-item.create"}
)

#: The event types the channel delivers into the session itself, after the
#: ledger record (issue-389 R3.7): the two acts join the reply. A gate answer and
#: a control keyword stop at their unmarked record, as before.
DELIVERED = frozenset({"work-item.reply", "context.added", "decision.recorded"})

#: The verbs' event types.
_VERB_EVENTS = {
    "record-context": "context.added",
    "record-decision": "decision.recorded",
}


def _control_config(cli_config: Optional[Mapping]):
    from ..control import ControlConfig

    routing = (dict(cli_config or {}).get("routing") or {}) if cli_config else {}
    return ControlConfig.from_mapping(
        (routing or {}).get("control") or {} if isinstance(routing, Mapping) else {}
    )


def _graph_reader(cli_config: Optional[Mapping]):
    """The dispatcher's own coupling, built from the same config (issue-321).

    ``RoutingConfig.from_mapping`` over ``routing`` and the state layout — what
    both daemons build their dispatcher from — then the registry at its
    ``registry_dir``, the ``ControlStore`` on its ``portable_dir`` and the
    ``GraphLink`` with the control config and the allow-list: the four arguments
    ``Dispatcher.__init__`` passes, in the same order. A second construction that
    drifted from that one *was* issue-321: a link with no control store, which
    under the default policy (``control.requireStartCommand``) reports every
    work item as never started and so never at a gate. A test pins the two
    constructions together.

    Imported lazily, as the read always was: ``webhook.dispatcher`` is needed
    only once a reply arrives, and the poll watcher and ``channels listen`` run
    without it until then.
    """
    from ..control import ControlStore
    from ..core.sessions import _layout, _routing
    from ..graphlink import GraphLink
    from ..sessions import SessionRegistry
    from ..webhook.dispatcher import RoutingConfig

    config = dict(cli_config or {})
    routing = RoutingConfig.from_mapping(dict(_routing(config)), _layout(config))
    registry = SessionRegistry(routing.registry_dir)
    link = GraphLink(
        routing.graph,
        routing.control,
        ControlStore(routing.portable_dir, legacy=routing.legacy),
        routing.authorized_users,
    )
    return routing, registry, link


def _at_human_gate(work_item: str, cli_config: Optional[Mapping]) -> Optional[bool]:
    """Whether ``work_item``'s graph is parked at a human-actor node — or ``None``
    when the pipeline **cannot tell** (issue-321).

    A read of state the daemon already keeps — the session's checkout, through
    the registry, then the coupling's read-only ``context`` — made through the
    dispatcher's own construction of that coupling (:func:`_graph_reader`).

    Three answers, because "cannot tell" is not "no": ``True`` at a human gate;
    ``False`` when the graph says it is not, when the coupling is off (nothing
    drives a graph, so nothing is parked at a gate) or for a standing session
    (no ticket, no graph); ``None`` for no session record, a record with no
    checkout, no context, or a fault. Folding ``None`` into ``False`` chose the
    marked record — the one shape no reader of the gate ever accepts — for
    exactly the case where the pipeline knew least. :func:`_classify` decides
    what ``None`` becomes.
    """
    if not work_item or parse_standing_ref(work_item):
        return False
    try:
        from ..sessions import WorkItemRef

        routing, registry, link = _graph_reader(cli_config)
        if not routing.graph.enabled:
            return False
        item = WorkItemRef.parse(work_item)
        record = registry.record_owning(item)
        if record is None or not record.cwd:
            logger.debug("no session record for %s: gate unknown", work_item)
            return None
        context = link.context(item, record.cwd)
    except Exception as exc:  # noqa: BLE001 — a graph fault is "cannot tell"
        logger.debug("could not read the graph for %s: %s", work_item, exc)
        return None
    if context is None:
        return None
    gate = getattr(context, "at_human_gate", False)
    return bool(gate() if callable(gate) else gate)


#: What the graph read returned, as `channel.reply_received` records it.
GATE_OPEN, GATE_NONE, GATE_UNKNOWN = "open", "none", "unknown"


def input_decision(addressed: bool, hears_messages: bool) -> str:
    """The one table of issue-389 §1: whether a message is input.

    ``addressed`` — it arrived as an ``app_mention``; ``hears_messages`` — its
    conversation takes plain messages (a DM with the bot, an ``all`` room).
    Returns ``"input"``, or the drop reason: ``not-addressed`` for a plain
    message where the mention is the address, ``duplicate`` for a mention's
    copy where the plain message is already the input.
    """
    if addressed:
        return "duplicate" if hears_messages else "input"
    return "input" if hears_messages else "not-addressed"


class Speaker:
    """Who a member is to this work item (issue-389 R7): on the allow-list, on
    the work item's roster, both, or neither."""

    __slots__ = ("authorized", "collaborator", "login")

    def __init__(self, authorized: bool, collaborator: bool, login: str = ""):
        self.authorized = authorized
        self.collaborator = collaborator
        self.login = login

    def may(self, event_type: str) -> bool:
        if self.authorized:
            return True
        return self.collaborator and event_type in INPUT_ACTS


def _roster(cli_config: Optional[Mapping], bot: Optional[SlackBotChannel]):
    """The collaborator roster beside the channel's own stores, or ``None``."""
    if bot is None or bot.stores is None:
        return None
    from ..collaborators import CollaboratorStore

    return CollaboratorStore(bot.stores.portable_dir)


def speaker_for(
    author: str,
    work_item: str,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    bot: Optional[SlackBotChannel] = None,
) -> Speaker:
    """``author`` (a member id) against the two lists, in that order: the
    allow-list (:func:`_authorized`) and — only for the work item the message
    was attributed to (R7.5) — that item's roster by Slack id. A roster that
    cannot be read, a store with no such method, or a standing session's
    thread read as *not a collaborator*: fail closed."""
    authorized = _authorized(author, config, cli_config)
    collaborator = False
    login = ""
    if not authorized and author and work_item and not parse_standing_ref(work_item):
        roster = _roster(cli_config, bot)
        try:
            if roster is not None and roster.is_collaborator_slack(author, work_item):
                collaborator = True
                for record in roster.list(work_item):
                    if getattr(record, "slack", "") == author:
                        login = str(getattr(record, "login", "") or "")
                        break
        except (AttributeError, OSError, ValueError) as exc:  # fail closed
            logger.debug("could not read %s's roster: %s", work_item, exc)
            collaborator = False
    return Speaker(authorized, collaborator, login)


def _principal(reply: InboundReply, config: SlackChannelConfig, speaker: Speaker):
    """The person a record names: the allow-list's entry, else the roster's ids
    (R7.4) — resolved from config or the roster, never from the message."""
    from ..identity import Principal

    named = principal_for(config.principals, reply.channel, reply.author)
    if named is not None:
        return named
    if speaker.collaborator:
        ids = {reply.channel: reply.author}
        if speaker.login:
            ids["github"] = speaker.login
        return Principal(ids=ids, name=speaker.login or "")
    return None


def _classify(
    reply: InboundReply,
    cli_config: Optional[Mapping],
    grants: Sequence[str],
    *,
    collaborator_only: bool = False,
) -> Tuple[str, str]:
    """The one event type this message is (R2.3) and what the gate read returned,
    in a fixed order:

    1. a control keyword → ``control.command`` (an approval word inside a control
       comment must not become a gate answer; the graph is not read);
    2. the work item parked at a human gate → ``gate.feedback``;
    3. the pipeline **cannot tell** (issue-321) → ``gate.feedback`` when the channel
       holds that grant — recorded unmarked for the ledger's ingress, which judges
       it with the graph it actually keeps — and ``work-item.reply`` when it does
       not: the grant stays the only thing that lets a message become a gate
       answer;
    4. otherwise → ``work-item.reply``.

    The grant is a parameter of step 3 alone: a gate the read *saw* is a gate
    answer whatever the grants (the grant check after classification drops it),
    and a graph that *said* "not at a gate" is a reply whatever the grants.
    """
    if reply.top_level:
        return "work-item.create", "n/a"
    # The grammar is read after the mention alone (R3.1): a plain message in a
    # DM or an `all` room that happens to start with a verb is a reply.
    verb = parse_verb(reply.text) if reply.addressed else None
    if verb is not None:
        return _VERB_EVENTS.get(verb.name, verb.name), "n/a"
    from ..control import parse_command

    if parse_command(reply.text, _control_config(cli_config)).command:
        return "control.command", "n/a"
    if collaborator_only:
        # A collaborator cannot answer a gate (issue-307: input only), so their
        # words are a reply by construction — whatever the graph is waiting on,
        # and even when it cannot be read (R7.2).
        return "work-item.reply", GATE_NONE
    gate = _at_human_gate(reply.work_item, cli_config)
    if gate:
        return "gate.feedback", GATE_OPEN
    if gate is None:
        if "gate.feedback" in set(grants):
            logger.info(
                "%s: the gate could not be read; the reply is left to the ledger",
                reply.work_item,
            )
            return "gate.feedback", GATE_UNKNOWN
        return "work-item.reply", GATE_UNKNOWN
    return "work-item.reply", GATE_NONE


def classify(
    reply: InboundReply, cli_config: Optional[Mapping], grants: Sequence[str] = ()
) -> str:
    """The one event type this message is — :func:`_classify` without the gate
    word. ``grants`` is the channel's ``publish`` list; without it a gate the
    pipeline cannot read is a reply, the 13.3.0 answer."""
    return _classify(reply, cli_config, grants)[0]


def _authorized(author: str, config: SlackChannelConfig, cli_config=None) -> bool:
    """Whether ``author`` (a member id) is on the channel's allow-list.

    ``routing.authorizedUsers[].slack`` may name a person by **member id**
    (``U0456GHIJ``) or by **handle** (``@dana``) since PR #376's review. An id is
    compared directly, as it always was; a handle is resolved through the cached
    directory and compared to the resolved id, so what this returns is still an
    exact match on an immutable identifier.

    **Fail closed twice over.** An empty list authorizes nobody, and an entry that
    cannot be resolved — no such handle, no token, a missing ``users:read`` scope
    — authorizes nobody *in particular*: it simply contributes no id, so the
    failure direction is fewer people, never more.

    The resolution costs nothing in the common case: an id short-circuits before
    any lookup, and a handle that resolved once is served from the file cache
    until it is evicted, so the hot path stays a set membership test.
    """
    if not author or not config.authorized_users:
        return False
    declared = set(config.authorized_users)
    if author in declared:
        return True
    from .directory import SlackDirectory, is_member_id

    handles = [entry for entry in declared if not is_member_id(entry)]
    if not handles:
        return False
    index = SlackDirectory.beside(
        slack_state_path(cli_config), token_env=config.bot_token_env
    )
    return any(index.user_id(handle) == author for handle in handles)


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
    bot = channel or SlackBotChannel(config, slack_state_path(cli_config))
    # The grammar after the mention (issue-389 R3.1): the bot's own `<@…>`
    # token comes off the text wherever it sits, a leading verb is the act, and
    # a leading control verb is composed into the CONFIGURED keyword exactly as
    # the slash command composes it — so `parse_command` reads a real keyword.
    text, found = strip_mention(reply.text, bot.own_user_id())
    addressed = found or reply.addressed
    verb = parse_verb(text) if addressed else None
    if addressed and verb is None:
        text = compose_keyword(text, _control_config(cli_config))
    if text != reply.text or addressed != reply.addressed:
        reply = replace(reply, text=text, addressed=addressed)
    # Two lists, consulted by act (R7.2): input from the allow-list and the
    # roster, a binding act from the allow-list alone. A stranger is dropped
    # in silence BEFORE anything is classified (A1; issue-321 A2: a stranger's
    # "approved" reads no graph) — R5.1: an empty list denies everyone. A
    # collaborator attempting a binding act is told so, because they are on
    # the roster and learn nothing they did not know (R5.3).
    speaker = speaker_for(reply.author, reply.work_item, config, cli_config, bot)
    if not speaker.authorized and not speaker.collaborator:
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)
    event_type, gate = _classify(
        reply, cli_config, config.publish, collaborator_only=not speaker.authorized
    )
    if not speaker.may(event_type):
        bot.react(reply, "error")
        _tell(
            bot,
            reply,
            f"`{verb.name if verb else event_type}` needs an authorized user of "
            "the-loop; as a collaborator on this work item you may add context "
            "(`record-context`) and reply.",
        )
        return _drop(
            reply,
            "unauthorized-act",
            level="warning",
            actor=reply.author,
            kind=event_type,
        )
    if event_type in ("context.added", "decision.recorded") and parse_standing_ref(
        reply.work_item
    ):
        # A standing session has no ticket (decision-111): there is nothing to
        # record on, and the standing deliverer takes no frame. Said, not
        # swallowed as `undeliverable`.
        bot.react(reply, "error")
        _tell(
            bot,
            reply,
            "This thread belongs to a standing session, which has no ticket to "
            "record on. Nothing was recorded; a plain reply still reaches it.",
        )
        return _drop(reply, "no-ticket", actor=reply.author, kind=event_type)
    if event_type == "help":
        # Taught, not recorded (R3.2): the grammar and this channel's grants,
        # only to the member who asked.
        answered = _tell(bot, reply, help_text(config))
        return {"outcome": "answered", "event": "help", "answered": answered}
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
    if verb is not None and verb.name == "record-decision" and not verb.rest.strip():
        # No model summarises a thread (R5.2): a decision is the text typed.
        bot.react(reply, "error")
        _tell(
            bot,
            reply,
            "`record-decision` needs the decision itself: "
            "`@the-loop record-decision [product|design|tech:] <what was decided> "
            "[— why: <rationale>]`. Nothing was recorded.",
        )
        return _drop(reply, "empty-decision", actor=reply.author)
    eventlog.emit(
        "channel.reply_received",
        channel=reply.channel,
        work_item=reply.work_item,
        actor=reply.author,
        kind=event_type,
        gate=gate,
    )
    # The acknowledgment (issue-325): after the last refusal, before the record,
    # on the message itself. Best-effort — `react` never raises.
    bot.react(reply, "received")
    actor = _principal(reply, config, speaker)
    detail: Dict[str, Any] = {"thread": reply.thread}
    if gate == GATE_UNKNOWN and event_type == "gate.feedback":
        # The record must not claim an answer to a gate the pipeline never saw
        # (R2.2): the ledger phrases a deferred reply as a reply.
        detail["gate"] = GATE_UNKNOWN
    text = reply.text
    snapshot_key = ""
    snapshot_newest = ""
    if event_type == "context.added":
        # The thread, snapshotted (R4.1–R4.5): what is new since the last
        # `record-context` on it, capped, scrubbed by the ledger on the way in.
        snapshot_key = f"{reply.channel_id}:{reply.thread}"
        with ChannelState.locked(bot.state_path, bot.stores) as state:
            noted = state.snapshot_for(snapshot_key)
        since = str((noted or {}).get("last") or "")
        try:
            # The typed mention is the act, not the context: left out when it
            # is a reply inside the thread. A top-level mention is the message
            # being recorded, and a shortcut's message is content the member
            # chose — both stay (finding 8).
            skip = reply.ts if found and reply.ts != reply.thread else ""
            snapshot = bot.snapshot_thread(
                reply.channel_id, reply.thread, since, skip=skip
            )
        except ChannelError as exc:
            bot.react(reply, "error")
            _tell(bot, reply, f"Could not read the thread: {exc}")
            return _drop(reply, "snapshot-failed", level="warning", error=str(exc))
        if snapshot.count == 0:
            bot.react(reply, "completed")
            _tell(
                bot,
                reply,
                "Nothing new in this thread since it was last recorded as context.",
            )
            eventlog.emit(
                "channel.snapshot_empty",
                channel=reply.channel,
                work_item=reply.work_item,
                thread=reply.thread,
            )
            return {"outcome": "nothing-new", "event": event_type}
        if len(snapshot.text) > GITHUB_COMMENT_LIMIT:
            bot.react(reply, "error")
            _tell(
                bot,
                reply,
                "This thread is too large to record in one comment even after the "
                "cap; record it in parts, or link it instead.",
            )
            return _drop(reply, "snapshot-too-large", level="warning")
        text = snapshot.text
        snapshot_newest = snapshot.newest
        detail.update(
            {
                "thread": snapshot.permalink or reply.thread,
                "count": str(snapshot.count),
                "truncated": "yes" if snapshot.truncated else "",
            }
        )
    elif event_type == "decision.recorded" and verb is not None:
        text = verb.rest
        if verb.kind in KINDS:
            detail["kind"] = verb.kind
        if verb.rationale:
            detail["rationale"] = verb.rationale
        detail["thread"] = _thread_permalink(bot, reply) or reply.thread
    event = Event(
        event_type=event_type,
        work_item=reply.work_item,
        text=text,
        source=reply.channel,
        actor=actor,
        detail=detail,
    )
    record = _record(event, reply, cli_config, post_comment)
    if snapshot_key and record and record.ok:
        with ChannelState.locked(bot.state_path, bot.stores) as state:
            noted = state.snapshot_for(snapshot_key)
            total = int((noted or {}).get("count") or 0) + int(detail.get("count") or 0)
            state.note_snapshot(snapshot_key, reply.work_item, snapshot_newest, total)
            state.save(bot.state_path)
        eventlog.emit(
            "channel.context_recorded",
            channel=reply.channel,
            work_item=reply.work_item,
            actor=reply.author,
            thread=reply.thread,
            count=int(detail.get("count") or 0),
        )
    elif event_type == "decision.recorded" and record and record.ok:
        eventlog.emit(
            "channel.decision_recorded",
            channel=reply.channel,
            work_item=reply.work_item,
            actor=reply.author,
            thread=reply.thread,
            kind=detail.get("kind") or None,
        )
    recorded = bool(record and record.ok)
    # A standing session has no ticket: a reply's skipped mirror is not a
    # failure, so what "lands" for it is the delivery alone (decision-111 D4). A
    # relayed type there has no ledger to reach, and did not land.
    landed = recorded or (
        event_type == "work-item.reply" and bool(parse_standing_ref(reply.work_item))
    )
    # The outcome names where the record lives and what went wrong (issue-337):
    # the press report links the one and says the other. Absent keys mean "no
    # record" / "no error", so every pre-existing reader sees what it saw.
    outcome: Dict[str, Any] = {
        "outcome": "processed",
        "event": event_type,
        "mirrored": recorded,
    }
    if recorded and record is not None and record.url:
        outcome["url"] = record.url
    if record is not None and not record.ok and record.error:
        outcome["error"] = record.error
    if event_type not in DELIVERED:
        # The record IS the request: the ledger's ingress classifies a gate
        # answer and executes a control keyword. Delivering here too would hand
        # the session the text twice and bypass the dispatcher's control seam.
        bot.react(reply, "completed" if landed else "error")
        return outcome
    kind = {"context.added": "context", "decision.recorded": "decision"}.get(
        event_type, "reply"
    )
    frame_detail = {
        **{k: str(v) for k, v in detail.items() if v},
        "url": (record.url if record else "") or "",
        "person": (actor.label if actor else "") or f"{reply.channel}:{reply.author}",
    }
    delivered, error = _deliver(
        replace(reply, text=text), cli_config, deliver, kind=kind, detail=frame_detail
    )
    bot.react(reply, "completed" if landed and delivered else "error")
    outcome["delivered"] = delivered
    if error and "error" not in outcome:
        outcome["error"] = error
    if kind != "reply" and recorded and record is not None:
        # The one visible receipt in the thread (R3.6): what landed, and where.
        what = (
            f"📎 recorded {detail.get('count')} message(s) as context"
            if kind == "context"
            else "📌 recorded the decision"
        )
        link = f" — {record.url}" if record.url else ""
        bot.say(reply.thread, f"{what} on `{reply.work_item}`{link}", reply.channel_id)
    return outcome


def _thread_permalink(bot: SlackBotChannel, reply: InboundReply) -> str:
    """The permalink of the message a decision was recorded on, best-effort."""
    if not reply.channel_id or not reply.ts:
        return ""
    try:
        return str(
            bot._client()  # noqa: SLF001 — the channel's own client
            .chat_getPermalink(channel=reply.channel_id, message_ts=reply.ts)
            .get("permalink")
            or ""
        )
    except Exception:  # noqa: BLE001 — a link is a nicety
        return ""


def _record(
    event: Event,
    reply: InboundReply,
    cli_config: Optional[Mapping],
    post_comment: Optional[Callable],
) -> Optional[PostResult]:
    """The ledger's record of ``event`` — its :class:`PostResult`, or ``None``
    for a standing session, which has nothing to record onto."""
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
        return None
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
    return result


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
    *,
    kind: str = "reply",
    detail: Optional[Mapping[str, str]] = None,
) -> Tuple[bool, str]:
    """``(delivered, error)`` — the error is the refusal's text when it was not.

    ``kind`` and ``detail`` select the frame a recorded act is typed under
    (issue-389 R3.7); a plain reply passes neither, so every existing deliverer
    — the tests' seams included — is called exactly as before."""
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
    extra: Dict[str, Any] = {}
    if kind != "reply":
        extra = {"kind": kind, "detail": dict(detail or {})}
    try:
        result = deliver(
            reply.work_item,
            reply.text,
            actor=f"{reply.channel}:{reply.author}",
            comment=False,  # the ledger record is the ticket's copy (D6)
            config=dict(cli_config or {}),
            **extra,
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
        return False, str(exc)
    except Exception as exc:  # transport trouble — same posture
        eventlog.emit(
            "channel.dropped",
            level="warning",
            channel=reply.channel,
            reason="undeliverable",
            work_item=reply.work_item,
            error=str(exc),
        )
        return False, str(exc)
    delivered = bool(result.get("delivered")) if isinstance(result, dict) else True
    return delivered, "" if delivered else "the session did not take the reply"


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
    the thread is bound to it and told the link. Never raises.

    The repository is the message's to name (issue-341): a first-line ``<repo>:``
    prefix resolved against the declared set, ``kickoff.repo`` as the fallback, and
    a prefix that resolves to none or to several refused in the thread — never
    guessed (decision-120).
    """
    if reply.is_bot:
        return _drop(reply, "self-authored")
    if "work-item.create" not in config.publish:
        return _drop(reply, "unpublishable-event", kind="work-item.create")
    if not _authorized(reply.author, config, cli_config):
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)
    if not reply.text.strip():
        return _drop(reply, "unmapped", actor=reply.author)
    bot = channel or SlackBotChannel(config, slack_state_path(cli_config))
    bot.react(reply, "received")  # issue-325: accepted, about to become an issue
    # WHICH repository is the message's to name (issue-341), resolved against the
    # set the operator declared and nothing else. This sits BELOW the allow-list
    # on purpose: a refusal names the declared repositories, and an unlisted
    # member is told nothing at all (R2.6).
    target = resolve_target(reply.text, config, cli_config)
    if target.ok:
        return _open_work_item(
            reply,
            config,
            cli_config,
            repo=target.repo,
            text=target.text,
            bot=bot,
            post_comment=post_comment,
            create_issue=create_issue,
        )
    # Not resolved. If a pick could answer it, ASK (issue-349, decision-122 D3);
    # otherwise refuse exactly as 14.0.0 did. `empty-message` is the one outcome
    # no pick can answer, and it is the one `askable` leaves out.
    # The options ARE `target.candidates`, already built by the resolver: the
    # whole declared set for `no-target`/`unknown-repo`, and for `ambiguous-repo`
    # only what the prefix matched — the narrow question the member already
    # half-answered (R1.2). The same list the refusal names, so the two renderings
    # can never disagree about what is on offer.
    if target.askable and config.kickoff_picker and target.candidates:
        return _ask_which_repository(reply, config, target, bot)
    bot.react(reply, "error")
    bot.say(reply.thread, refusal_text(target), reply.channel_id)
    return _drop(
        reply,
        f"kickoff-{target.outcome}",
        level="warning",
        actor=reply.author,
        kind=target.prefix or None,
    )


def _ask_which_repository(
    reply: InboundReply,
    config: SlackChannelConfig,
    target,
    bot: SlackBotChannel,
) -> Dict[str, Any]:
    """Hold the message and ask which repository it goes in (R1.1, R3.1).

    Nothing is created, recorded or bound — a question is not a decision. The
    message is parked under the state lock **before** it is posted, so a second
    read of the same message (a poll cycle beside the listener, a Slack retry)
    finds a question already outstanding and does not ask twice (R3.7). If the
    post then fails the record is dropped again: a question nobody can see must
    not suppress the next one.

    The key is the message's own ``ts``. For a top-level message that is also its
    ``thread``, which is what makes the record findable from a press: a
    ``block_actions`` payload for a reply in the thread carries the ROOT's ts, and
    nothing else of the message it answers.
    """
    options = target.candidates
    with ChannelState.locked(bot.state_path, bot.stores) as state:
        if state.pending_for(reply.ts):
            return _drop(reply, "kickoff-already-asked", actor=reply.author)
        state.ask(reply.ts, reply.channel_id, reply.author, target.text, options)
        state.save(bot.state_path)
    said = question_text(target)
    if not bot.say(
        reply.thread,
        said,
        reply.channel_id,
        blocks=render_kickoff_question(said, options),
    ):
        with ChannelState.locked(bot.state_path, bot.stores) as state:
            state.forget(reply.ts)
            state.save(bot.state_path)
        bot.react(reply, "error")
        return _drop(reply, "kickoff-ask-failed", level="warning", actor=reply.author)
    eventlog.emit(
        "channel.kickoff_asked",
        channel=reply.channel,
        actor=reply.author,
        thread=reply.thread,
        kind=target.outcome,
        count=len(options),
    )
    return {"outcome": "asked", "options": len(options)}


def _open_work_item(
    reply: InboundReply,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    *,
    repo: str,
    text: str,
    bot: SlackBotChannel,
    post_comment: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """`work-item.create` → the ledger opens the issue → the thread is bound to it
    and told the link. The tail of the kickoff, shared by the two ways of reaching
    it: a prefix that resolved, and a pick that answered the question (R4.3, R4.4).

    ``repo`` is always a DECLARED slug — the resolver's or the picker's — so the
    one rule that matters here holds by construction on both paths: nothing of the
    member's text ever becomes a repository argument.
    """
    actor = principal_for(config.principals, reply.channel, reply.author)
    event = Event(
        event_type="work-item.create",
        work_item="",
        text=text,
        source=reply.channel,
        actor=actor,
        detail={
            "repo": repo,
            "labels": ",".join(config.kickoff_labels),
            "thread": reply.thread,
        },
    )
    ledger = GitHubLedger(
        cli_config, post_comment=post_comment, create_issue=create_issue
    )
    result = publish(event, cli_config, channels=[], ledger=ledger).record
    if not (result and result.ok and result.ref):
        bot.react(reply, "error")
        return _drop(
            reply,
            "create-failed",
            level="warning",
            actor=reply.author,
            error=(result.error if result else None) or None,
        )
    bot.bind(reply.thread, result.ref, reply.channel_id, origin="kickoff")
    link = f" — {result.url}" if result.url else ""
    # The reply that asks for `the-loop start` typed back carries the Start
    # button where a press can be received (issue-337 R1.2): the value is the
    # configured keyword, so the press is exactly the typed keyword.
    said = (
        f"Opened {result.ref}{link}. This thread is now that work item's "
        "conversation — replies here reach it."
    )
    bot.say(
        reply.thread,
        said,
        reply.channel_id,
        blocks=render_reply_blocks(said, config.command_buttons_for("start")),
    )
    eventlog.emit(
        "channel.created",
        channel=reply.channel,
        work_item=result.ref,
        actor=reply.author,
        thread=reply.thread,
    )
    bot.react(reply, "completed")
    return {"outcome": "created", "workItem": result.ref, "url": result.url}


def process_kickoff_answer(
    reply: InboundReply,
    config: SlackChannelConfig,
    cli_config: Optional[Mapping],
    *,
    bot: SlackBotChannel,
    post_comment: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
) -> Dict[str, Any]:
    """A repository pick → the work item the question was holding (issue-349).

    ``reply.text`` is the pressed value and ``reply.thread`` is the message the
    question was asked about — the key the record is held under. Four gates, in
    this order, and the order is the point:

    1. **Authorized**, the same fail-closed allow-list every inbound goes through.
    2. **The message's own author** (decision-122 D5). The issue is opened as the
       person who wrote it, so another member — authorized or not — does not get
       to decide where their message lands.
    3. **A live record.** Expired, already-answered and never-asked are one read:
       there is nothing to answer.
    4. **A value that was offered AND is still declared.** Two bounds, not one —
       the offered set stops a real repository that was never on *this* question,
       and the declared re-check stops one the operator has since removed. What
       reaches the ledger is the matched ``DeclaredRepo.declared``, never the
       pressed string.

    Gates 1 and 2 sit above the record read so an unauthorized presser learns
    nothing, not even that a question exists. Never raises.

    Above all four is the channel's own permission, re-read at press time rather
    than trusted from when the question went out: an operator who revokes
    ``work-item.create`` (or leaves Socket Mode) while a question is outstanding
    has revoked it for the answer too. This is the only gate a *pending record*
    could otherwise smuggle a member past.
    """
    if not config.kickoff_picker:
        return _drop(
            reply, "unpublishable-event", level="warning", kind="work-item.create"
        )
    if not _authorized(reply.author, config, cli_config):
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)
    state = ChannelState.load(bot.state_path, bot.stores)
    record = state.pending_for(reply.thread)
    if record and record.get("author") != reply.author:
        # Not theirs to direct: the record stands, untouched, for its author.
        return _drop(reply, "not-your-kickoff", level="warning", actor=reply.author)
    if not record:
        return _drop(reply, "no-pending-kickoff", actor=reply.author)
    chosen = reply.text.strip()
    declared = {entry.declared: entry for entry in declared_repositories(cli_config)}
    if chosen not in set(record.get("options") or ()) or chosen not in declared:
        return _drop(
            reply,
            "undeclared-repository",
            level="warning",
            actor=reply.author,
        )
    # The acknowledgment (issue-325 R1.5): after the last refusal, before the
    # record, on the message the press came from — here, the question itself.
    bot.react(reply, "received")
    # Claim before publishing (R3.4): the pop is inside the lock and the create is
    # outside it, so a second press of the same question finds nothing to answer
    # and exactly one issue is opened.
    with ChannelState.locked(bot.state_path, bot.stores) as fresh:
        claimed = fresh.claim(reply.thread)
        if not claimed:
            return _drop(reply, "no-pending-kickoff", actor=reply.author)
        fresh.save(bot.state_path)
    outcome = _open_work_item(
        reply,
        config,
        cli_config,
        repo=declared[chosen].declared,
        text=str(claimed.get("text") or ""),
        bot=bot,
        post_comment=post_comment,
        create_issue=create_issue,
    )
    if outcome.get("outcome") != "created":
        # The question stays answerable (R3.5) — which is the same posture the
        # press report takes, keeping the buttons on a press that did not land.
        with ChannelState.locked(bot.state_path, bot.stores) as fresh:
            fresh.restore(reply.thread, claimed)
            fresh.save(bot.state_path)
    return outcome


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
    channel's top-level messages (R4.1, R6.5). Never raises.

    Runs in ``poll`` mode (the daemons' background reader, cron) **and** in
    ``socket`` mode (issue-334): the listener runs it once after connecting,
    and an operator may run ``the-loop channels poll`` beside the listener as a
    reconciliation — the cursors are shared, so nothing is processed twice.
    Only ``off`` refuses.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled:
        return {"skipped": "channels.slack is not enabled", "replies": 0}
    if config.read_mode == "off":
        return {
            "skipped": "channels.slack.read.mode is 'off' — nothing is read",
            "replies": 0,
        }
    channel = SlackBotChannel(
        config, slack_state_path(cli_config), client_factory=client_factory
    )
    try:
        replies = channel.fetch_replies()
        declared = channel.fetch_channel_messages()
        kickoffs = channel.fetch_kickoffs()
    except ChannelError as exc:
        logger.warning("channels poll skipped: %s", exc)
        return {"skipped": str(exc), "replies": 0}
    # A message in a declared collaboration channel is a message ON that work
    # item (issue-375), so it goes through the reply pipeline — the same
    # classification, grants, ledger record and delivery a thread reply gets.
    # Its cursor is the ROOM's, not a thread's, which is why it is advanced
    # separately below.
    seen = {(reply.channel_id, reply.ts) for reply in replies}
    declared = [msg for msg in declared if (msg.channel_id, msg.ts) not in seen]
    summary: Dict[str, Any] = {
        "replies": len(replies) + len(declared) + len(kickoffs),
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
    for message in declared:
        outcome = process_reply(
            message,
            config,
            cli_config,
            post_comment=post_comment,
            deliver=deliver,
            channel=channel,
        )
        # The room's cursor, not the message's thread: the next cycle asks Slack
        # for what came after this message in the channel (R3.6).
        channel.advance(kickoff_cursor_key(message.channel_id), message.ts)
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
    client_factory: Optional[Callable] = None,
    addressed: bool = False,
) -> Dict[str, Any]:
    """One Socket Mode ``message`` event through the same pipeline (R4.2).

    The bindings decide relevance (R4.4): a message outside a bound thread is
    dropped as ``unmapped`` — unless it is a top-level message in the configured
    channel and the channel holds the ``work-item.create`` grant, in which case
    it is a kickoff candidate through the same function the poll read uses, or it
    is in a channel a work item **declared** (issue-375), in which case it is a
    message on that work item wherever in the channel it was typed.
    ``client_factory`` is the same injection point ``poll_once`` has (issue-325):
    the channel built here is what acknowledges the message.

    ``addressed`` says the event is an ``app_mention`` (issue-389 R1.1): the
    mention is the address, so a plain ``message`` is input only where the
    conversation hears plain messages — a direct message with the bot, a room
    declared ``--listen all`` — and is otherwise dropped ``not-addressed``
    before the kickoff branch, authorization or any reaction, with no cursor
    moved; a mention's copy in such a conversation is the ``duplicate``.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    bot = SlackBotChannel(config, state_path, client_factory=client_factory)
    state = ChannelState.load(state_path, bot.stores)
    ts = str(event.get("ts") or "")
    thread = str(event.get("thread_ts") or "")
    channel_id = str(event.get("channel") or "")
    is_bot = bool(event.get("bot_id")) or event.get("subtype") == "bot_message"
    # Whose room is this? (issue-375) Read BEFORE the kickoff branch, because a
    # declared channel never opens a work item: a dedicated room has one subject,
    # and a message in it is a message on that subject. A bound thread still wins
    # over the room below — a work item whose conversation the-loop opened in this
    # channel keeps it, which is what stops a declaration on the CENTRAL channel
    # re-attributing every other work item's thread in it.
    room_work_item = (
        bot.stores.declared_work_item(channel_id) if bot.stores is not None else ""
    )
    decision = input_decision(addressed, bot.hears_messages(channel_id))
    if decision != "input":
        return _drop(
            InboundReply(
                channel="slack",
                work_item=room_work_item
                or (state.work_item_for(thread) or "" if thread else ""),
                author=str(event.get("user") or ""),
                text="",
                thread=thread,
                ts=ts,
                channel_id=channel_id,
            ),
            decision,
            level="debug",
        )
    if (not thread or thread == ts) and channel_id == config.channel:
        if (
            config.kickoff_enabled
            and not room_work_item
            and not state.work_item_for(ts)
        ):
            # The mention is the address, not the ask (issue-389 R1.5): the
            # issue is opened from the words after it.
            said = str(event.get("text") or "")
            if addressed:
                said, _ = strip_mention(said, bot.own_user_id())
            reply = InboundReply(
                channel="slack",
                work_item="",
                author=str(event.get("user") or ""),
                text=said,
                thread=ts,
                ts=ts,
                is_bot=is_bot,
                top_level=True,
                channel_id=channel_id,
                addressed=addressed,
            )
            return process_kickoff(
                reply,
                config,
                cli_config,
                channel=bot,
                post_comment=post_comment,
                create_issue=create_issue,
            )
    bound = state.work_item_for(thread) or "" if thread else ""
    work_item = bound or room_work_item
    # From the ROOM rather than from a binding (issue-375): a top-level message
    # in a declared channel is its own thread, so the record and any reply
    # the-loop posts hang off the message itself.
    from_room = not bound and bool(room_work_item)
    thread = thread or (ts if from_room else "")
    # Which cursor says whether this was already processed. A message that IS
    # the root of its own thread has no thread cursor to be older than — the
    # thread-cursor default is the root's own ts — so the ROOM's cursor answers
    # for it, the same one the poll transport advances (R3.6). Everything else
    # keeps the thread cursor it always had.
    cursor_key = (
        kickoff_cursor_key(channel_id) if from_room and thread == ts else thread
    )
    seen = (
        state.cursors.get(cursor_key, "")
        if cursor_key.startswith("channel:")
        else state.cursor(cursor_key)
    )
    reply = InboundReply(
        channel="slack",
        work_item=work_item,
        author=str(event.get("user") or ""),
        text=str(event.get("text") or ""),
        thread=thread,
        ts=ts,
        is_bot=is_bot,
        channel_id=channel_id,
        addressed=addressed,
    )
    if work_item and ts and seen and _ts_key(ts) <= _ts_key(seen):
        # Already processed — by the catch-up read after a reconnect, or by a
        # poll cycle — and now redelivered by Slack's retry (issue-334). The
        # shared cursor is the at-most-once contract across both transports.
        return _drop(reply, "duplicate")
    outcome = process_reply(
        reply,
        config,
        cli_config,
        post_comment=post_comment,
        deliver=deliver,
        channel=bot,
    )
    if work_item and reply.ts:
        # Shared with the poll transport (R4.6): a mode switch cannot
        # double-process what the socket already handled. Under the state
        # lock (issue-312): a cursor advance never overwrites a binding a
        # writer in another process saved beside it.
        with ChannelState.locked(state_path, ChannelStores.beside(state_path)) as fresh:
            fresh.advance(cursor_key, reply.ts)
            fresh.save(state_path)
    return outcome


#: What a shortcut's or a modal's `private_metadata` may name: a conversation
#: id and Slack timestamps, nothing else (A3).
_CHANNEL_ID_RE = re.compile(r"^[CGD][A-Z0-9_-]{1,20}$")
_TS_RE = re.compile(r"^\d+\.\d+$")


def _tell(bot: SlackBotChannel, reply: InboundReply, text: str) -> bool:
    """An ephemeral to the member, in the thread they are in (finding 9)."""
    return bot.post_ephemeral(reply.channel_id, reply.author, text, reply.thread)


def _shortcut_reply(
    payload: Mapping[str, Any], text: str, state: ChannelState, bot: SlackBotChannel
) -> Optional[InboundReply]:
    """The typed-mention equivalent of a shortcut payload (R6.2, R6.4): the
    payload's own ``user.id`` as the author, the message's channel and ts, its
    thread when it is in one, ``text`` as what the member "typed". ``None``
    when the payload names no message worth attributing."""
    user = str((payload.get("user") or {}).get("id") or "")
    channel_id = str((payload.get("channel") or {}).get("id") or "")
    message = payload.get("message") or {}
    ts = str(message.get("ts") or "")
    thread = str(message.get("thread_ts") or "") or ts
    if not (user and _CHANNEL_ID_RE.match(channel_id) and _TS_RE.match(ts)):
        return None
    if thread != ts and not _TS_RE.match(thread):
        return None
    room = bot.stores.declared_work_item(channel_id) if bot.stores is not None else ""
    work_item = (state.work_item_for(thread) if thread != ts else "") or room or ""
    if not work_item and thread == ts:
        work_item = state.work_item_for(ts) or room or ""
    return InboundReply(
        channel="slack",
        work_item=work_item,
        author=user,
        text=text,
        thread=thread,
        ts=ts,
        channel_id=channel_id,
        addressed=True,  # a shortcut is the typed mention (R6.2)
    )


def _shortcut_outcome(
    bot: SlackBotChannel, reply: InboundReply, outcome: Mapping
) -> None:
    """Tell the member what their shortcut did — ephemerally, since a shortcut
    has no message of their own to react on (R6.5). Silence for a refusal below
    the allow-list (A1)."""
    what = str(outcome.get("outcome") or "")
    if what in ("unauthorized-actor", "unmapped"):
        # Nothing for a member the-loop does not know, and nothing that says
        # the-loop is listening where nothing is bound (A1, A8).
        return
    if what == "processed" and not outcome.get("mirrored"):
        said = "Could not record: " + str(outcome.get("error") or "the ledger refused")
    elif what == "processed":
        url = str(outcome.get("url") or "")
        said = "Recorded" + (f" — {url}" if url else "") + "."
        if outcome.get("delivered") is False:
            said += " The session could not take it; the record stands."
    elif what == "nothing-new":
        said = "Nothing new in that thread since it was last recorded."
    elif what in ("empty-decision", "unauthorized-act", "snapshot-too-large"):
        return  # already told, on the same channel, by the pipeline
    else:
        said = f"Nothing recorded ({what})."
    _tell(bot, reply, said)


def handle_message_action(
    payload: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    client_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """A message shortcut (issue-389 R6): *Add to the-loop as context* is exactly
    ``@the-loop record-context`` typed on that message; *Record a decision*
    opens the modal, whose submission is :func:`handle_view_submission`. The
    callback id is the only thing read from the payload's shape; the member is
    the payload's ``user.id``; a trigger acts once. Never raises.
    """
    callback = str(payload.get("callback_id") or "")
    verb = MENTION_SHORTCUTS.get(callback)
    if not verb:
        return {"outcome": "ignored"}
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    bot = SlackBotChannel(config, state_path, client_factory=client_factory)
    state = ChannelState.load(state_path, bot.stores)
    reply = _shortcut_reply(payload, verb, state, bot)
    trigger = str(payload.get("trigger_id") or "")
    member = str((payload.get("user") or {}).get("id") or "")
    if reply is None:
        return _drop(
            InboundReply("slack", "", member, "", "", "", channel_id=""),
            "bad-metadata",
        )
    if not first_sight(trigger):
        return _drop(reply, "duplicate")
    eventlog.emit(
        "channel.shortcut_received",
        channel="slack",
        work_item=reply.work_item or None,
        actor=member,
        shortcut=callback,
    )
    if verb == "record-decision":
        # The modal, only for a member who may record a decision (R7.2, A1, A3):
        # the same speaker check the typed form meets, so an unlisted member
        # sees nothing and a collaborator is told the act is not theirs.
        if not reply.work_item:
            return _drop(reply, "unmapped")
        speaker = speaker_for(member, reply.work_item, config, cli_config, bot)
        if not speaker.authorized and not speaker.collaborator:
            return _drop(reply, "unauthorized-actor", level="warning", actor=member)
        if not speaker.may("decision.recorded"):
            _tell(
                bot,
                reply,
                "Recording a decision needs an authorized user of the-loop; as a "
                "collaborator you may add context and reply.",
            )
            return _drop(reply, "unauthorized-act", level="warning", actor=member)
        if "decision.recorded" not in config.publish:
            # Known before the form opens (R2.3): a modal whose submission
            # would be dropped is not offered.
            _tell(
                bot,
                reply,
                "This channel may not record decisions: `decision.recorded` is "
                "not in its publish grants.",
            )
            return _drop(
                reply, "unpublishable-event", actor=member, kind="decision.recorded"
            )
        metadata = json.dumps(
            {"channel": reply.channel_id, "ts": reply.ts, "thread_ts": reply.thread},
            separators=(",", ":"),
        )
        text = str((payload.get("message") or {}).get("text") or "")
        opened = bot.open_view(trigger, decision_view(text, metadata))
        if not opened:
            _tell(
                bot,
                reply,
                "Could not open the decision form — try the shortcut again, or type "
                "`@the-loop record-decision <what was decided>`.",
            )
        return {"outcome": "modal-opened" if opened else "modal-failed"}
    outcome = process_reply(
        reply,
        config,
        cli_config,
        post_comment=post_comment,
        deliver=deliver,
        channel=bot,
    )
    _shortcut_outcome(bot, reply, outcome)
    return outcome


def handle_view_submission(
    payload: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    client_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """The decision modal's submission (issue-389 R6.3): composed into exactly
    ``record-decision <kind>: <text> — why: <rationale>`` typed by the
    submitting member on the message the shortcut was used on, and handed to
    the pipeline. The metadata is validated as a channel id and timestamps
    before use (A3); a view acts once. Never raises.
    """
    view = payload.get("view") or {}
    if str(view.get("callback_id") or "") != DECISION_VIEW_CALLBACK:
        return {"outcome": "ignored"}
    member = str((payload.get("user") or {}).get("id") or "")
    try:
        metadata = json.loads(str(view.get("private_metadata") or ""))
    except ValueError:
        metadata = None
    if not isinstance(metadata, dict):
        return _drop(InboundReply("slack", "", member, "", "", ""), "bad-metadata")
    channel_id = str(metadata.get("channel") or "")
    ts = str(metadata.get("ts") or "")
    thread = str(metadata.get("thread_ts") or "") or ts
    if not (member and _CHANNEL_ID_RE.match(channel_id) and _TS_RE.match(ts)):
        return _drop(InboundReply("slack", "", member, "", "", ""), "bad-metadata")
    if not _TS_RE.match(thread):
        return _drop(InboundReply("slack", "", member, "", "", ""), "bad-metadata")
    values = (view.get("state") or {}).get("values") or {}

    def field(block: str, action: str, key: str = "value") -> str:
        element = (values.get(block) or {}).get(action) or {}
        if key == "selected":
            return str(((element.get("selected_option") or {}).get("value")) or "")
        return str(element.get("value") or "")

    text = " ".join(field("decision", "text").split())
    kind = field("kind", "select", "selected")
    rationale = " ".join(field("rationale", "text").split())
    composed = "record-decision "
    if kind:
        composed += f"{kind}: "
    composed += text
    if rationale:
        composed += f" — why: {rationale}"
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    bot = SlackBotChannel(config, state_path, client_factory=client_factory)
    state = ChannelState.load(state_path, bot.stores)
    reply = _shortcut_reply(
        {
            "user": {"id": member},
            "channel": {"id": channel_id},
            "message": {"ts": ts, "thread_ts": thread if thread != ts else ""},
        },
        composed,
        state,
        bot,
    )
    if reply is None:
        return _drop(InboundReply("slack", "", member, "", "", ""), "bad-metadata")
    if not first_sight(str(view.get("id") or "")):
        return _drop(reply, "duplicate")
    eventlog.emit(
        "channel.view_submitted",
        channel="slack",
        work_item=reply.work_item or None,
        actor=member,
        kind=kind or None,
    )
    outcome = process_reply(
        reply,
        config,
        cli_config,
        post_comment=post_comment,
        deliver=deliver,
        channel=bot,
    )
    _shortcut_outcome(bot, reply, outcome)
    return outcome


def handle_socket_action(
    payload: Mapping[str, Any],
    cli_config: Optional[Mapping],
    *,
    post_comment: Optional[Callable] = None,
    deliver: Optional[Callable] = None,
    create_issue: Optional[Callable] = None,
    client_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """A Block Kit ``block_actions`` press → that member's reply carrying the
    button's ``value`` as its text (R4.3, A9).

    Only actions the-loop rendered (``action_id`` under :data:`ACTION_PREFIX`) are
    read; the value is *text*, judged by the ordinary pipeline with the ordinary
    authorization — a crafted payload buys nothing a typed message would not.
    Since issue-349 one ``action_id`` is routed *before* that pipeline:
    the repository picker's, whose value is an **argument** to a work item that
    does not exist yet. ``create_issue`` is its injection seam, the same one
    :func:`handle_socket_event` has for the kickoff itself.
    An Execute / Start button's value is the configured keyword (issue-337), so
    its press is a typed keyword: ``control.command`` under that grant, recorded
    unmarked, executed by the ledger's ingress. The reply's ``ts`` is the
    **pressed message's** — the only message a press has, where the
    acknowledgment lands (issue-325 R1.5) and where the outcome is written back
    (:meth:`SlackBotChannel.report_press`, issue-337 R2) once the pipeline
    *processed* the press; a dropped press leaves it untouched. The action path
    advances no cursor, so nothing else reads it.
    """
    actions = [
        a
        for a in (payload.get("actions") or [])
        if isinstance(a, Mapping)
        and str(a.get("action_id") or "").startswith(ACTION_PREFIX)
        and action_value(a)
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
    state = ChannelState.load(state_path, ChannelStores.beside(state_path))
    action_id = str(actions[0].get("action_id") or "")
    reply = InboundReply(
        channel="slack",
        work_item=state.work_item_for(thread) or "" if thread else "",
        author=str((payload.get("user") or {}).get("id") or ""),
        text=action_value(actions[0]),
        thread=thread,
        ts=str(
            container.get("message_ts")
            or message.get("ts")
            or payload.get("action_ts")
            or ""
        ),
        channel_id=str((payload.get("channel") or {}).get("id") or ""),
    )
    bot = SlackBotChannel(config, state_path, client_factory=client_factory)
    if is_kickoff_repo_action(action_id):
        # The one press that is an ARGUMENT rather than an answer or a keyword
        # (issue-349): there is no work item yet, so `process_reply` would drop it
        # as `unmapped`. Routed above it, leaving every existing path untouched.
        outcome = process_kickoff_answer(
            reply,
            config,
            cli_config,
            bot=bot,
            post_comment=post_comment,
            create_issue=create_issue,
        )
        # Written back onto the question for a press that got past the ALLOW-LIST
        # — whether it then opened the work item, failed to, or was refused by one
        # of the three gates below it. decision-111 D1 ("a refusal leaves no
        # mark") is kept where it bites: an unauthorized press edits nothing and
        # its presser learns nothing, not even that a question exists. Above that
        # line decision-120 D2's narrowing applies — an authorized refusal
        # answers — because a member who taps an expired question and sees
        # absolutely nothing happen is the failure this work item exists to end.
        # The report is in place on a message they can already see, so it
        # discloses nothing new, and a press that did not land keeps its picker.
        if outcome.get("outcome") != "unauthorized-actor":
            bot.report_press(
                reply,
                message if isinstance(message, Mapping) else {},
                action_id,
                outcome,
            )
        return outcome
    outcome = process_reply(
        reply,
        config,
        cli_config,
        post_comment=post_comment,
        deliver=deliver,
        channel=bot,
    )
    if outcome.get("outcome") == "processed":
        bot.report_press(
            reply,
            message if isinstance(message, Mapping) else {},
            action_id,
            outcome,
        )
    return outcome
