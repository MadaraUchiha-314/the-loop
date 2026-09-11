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

import logging
from typing import Any, Callable, Dict, Mapping, Optional, Sequence, Tuple

from .. import eventlog
from ..identity import principal_for
from ..repos import declared_repositories
from ..standing import parse_standing_ref
from .base import ChannelError, Event, InboundReply, PostResult
from .bus import publish
from .github import GitHubLedger
from .kickoff import question_text, refusal_text, resolve_target
from .slack import (
    ACTION_PREFIX,
    SlackBotChannel,
    SlackChannelConfig,
    _ts_key,
    action_value,
    is_kickoff_repo_action,
    render_kickoff_question,
    render_reply_blocks,
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
    "process_kickoff_answer",
    "process_reply",
]


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


def _classify(
    reply: InboundReply, cli_config: Optional[Mapping], grants: Sequence[str]
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
    from ..control import parse_command

    if parse_command(reply.text, _control_config(cli_config)).command:
        return "control.command", "n/a"
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

    event_type, gate = _classify(reply, cli_config, config.publish)
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
        gate=gate,
    )
    # The acknowledgment (issue-325): after the last refusal, before the record,
    # on the message itself. Best-effort — `react` never raises.
    bot = channel or SlackBotChannel(config, slack_state_path(cli_config))
    bot.react(reply, "received")
    actor = principal_for(config.principals, reply.channel, reply.author)
    detail: Dict[str, Any] = {"thread": reply.thread}
    if gate == GATE_UNKNOWN and event_type == "gate.feedback":
        # The record must not claim an answer to a gate the pipeline never saw
        # (R2.2): the ledger phrases a deferred reply as a reply.
        detail["gate"] = GATE_UNKNOWN
    event = Event(
        event_type=event_type,
        work_item=reply.work_item,
        text=reply.text,
        source=reply.channel,
        actor=actor,
        detail=detail,
    )
    record = _record(event, reply, cli_config, post_comment)
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
    if event_type != "work-item.reply":
        # The record IS the request: the ledger's ingress classifies a gate
        # answer and executes a control keyword. Delivering here too would hand
        # the session the text twice and bypass the dispatcher's control seam.
        bot.react(reply, "completed" if landed else "error")
        return outcome
    delivered, error = _deliver(reply, cli_config, deliver)
    bot.react(reply, "completed" if landed and delivered else "error")
    outcome["delivered"] = delivered
    if error and "error" not in outcome:
        outcome["error"] = error
    return outcome


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
) -> Tuple[bool, str]:
    """``(delivered, error)`` — the error is the refusal's text when it was not."""
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
    if not config.authorized_users or reply.author not in set(config.authorized_users):
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
    with ChannelState.locked(bot.state_path) as state:
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
        with ChannelState.locked(bot.state_path) as state:
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
    if not config.authorized_users or reply.author not in set(config.authorized_users):
        return _drop(reply, "unauthorized-actor", level="warning", actor=reply.author)
    state = ChannelState.load(bot.state_path)
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
    with ChannelState.locked(bot.state_path) as fresh:
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
        with ChannelState.locked(bot.state_path) as fresh:
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
    client_factory: Optional[Callable] = None,
) -> Dict[str, Any]:
    """One Socket Mode ``message`` event through the same pipeline (R4.2).

    The bindings decide relevance (R4.4): a message outside a bound thread is
    dropped as ``unmapped`` — unless it is a top-level message in the configured
    channel and the channel holds the ``work-item.create`` grant, in which case
    it is a kickoff candidate through the same function the poll read uses.
    ``client_factory`` is the same injection point ``poll_once`` has (issue-325):
    the channel built here is what acknowledges the message.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    state_path = slack_state_path(cli_config)
    state = ChannelState.load(state_path)
    bot = SlackBotChannel(config, state_path, client_factory=client_factory)
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
                channel=bot,
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
    if work_item and ts and _ts_key(ts) <= _ts_key(state.cursor(thread)):
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
    state = ChannelState.load(state_path)
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
