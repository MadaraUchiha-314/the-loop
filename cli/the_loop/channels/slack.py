"""The Slack bot channel — writes and reads through the official SDK (D5, D7).

Distinct from :mod:`the_loop.graph.integrations`: that layer carries the-loop's own
one-shot calls. This is a **bot**: a token with an identity, able to post into a
channel, thread a conversation per work item, read the replies back — and, since
issue-309, render every event with Block Kit, carry Approve / Request changes
buttons where a press can be received, and open a work item from a top-level
message when granted. Since issue-337 it also renders **Execute** / **Start**
command buttons on the messages that expect those keywords typed back, and
writes a press's outcome onto the pressed message.

The thread is the **work item's** (issue-312, decision-105): the first event for
a work item opens a root that names it — under the state file's lock, so two
writers open one thread — and every event, that first one included, is a reply
into it. Which thread a work item is in is a keyed record
(``ChannelState.conversations``), listed by ``the-loop channels threads``.
Since issue-317 the thread is opened **when the work item starts** — the
dispatcher's spawn path asks every channel to :meth:`SlackBotChannel.open` its
conversation, root only, no reply — and the first event replies into it; a start
that could not open one leaves the lazy path above as the fallback.

Tokens are read from the environment **at call time** (the ``_SlackBase._url()``
rule: a provider outlives many transitions and must see the environment as it
is), named by config, never held as values (R3.1).
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from .. import eventlog, strings
from ..cli_config import gateway_block
from ..identity import Principal, ids_for, parse_authorized_users
from .directory import is_conversation_id
from .base import (
    DEFAULT_EVENTS,
    DEFAULT_PUBLISH,
    VERBOSITIES,
    ChannelError,
    Event,
    InboundReply,
    PostResult,
)
from .events import (
    APPROVAL_EVENTS,
    GATE_ANSWERED,
    PUBLISHABLE_EVENTS,
    SUBSCRIBABLE_EVENTS,
)
from . import placement, room_policy, sessionnotes, status as status_reactor
from .preamble import Preamble, change_of, mention_line, recap_line, wait_key
from .delivery import (
    THREAD_OF_TOP,
    Delivered,
    MessagePlan,
    deliver,
    plan_message,
    post_message,
    summary_of,
    with_retry,
)
from .render import LongForm, render_long_form
from .shortform import build_short_form, long_form_adds
from .state import ROOM_MODE, ChannelState, ChannelStores
from . import attachments

logger = logging.getLogger("the-loop.channels")

#: The deprecated keys of ``channels.slack`` (issue-549 R1.3), and the ones this
#: process has already warned about: each is named once, however often the
#: config is read.
DEPRECATED_SLACK_KEYS: Tuple[str, ...] = ("maxChars", "longMessages")
_DEPRECATED_WARNED: Set[str] = set()


def _warn_deprecated(section: Mapping[str, Any]) -> None:
    """Warn once per process for each deprecated key ``section`` still sets."""
    for key in DEPRECATED_SLACK_KEYS:
        if key in section and key not in _DEPRECATED_WARNED:
            _DEPRECATED_WARNED.add(key)
            logger.warning(strings.t("channels.slack.deprecated-key", key=key))


__all__ = [
    "ACTION_PREFIX",
    "DECISION_VIEW_CALLBACK",
    "GITHUB_COMMENT_LIMIT",
    "MENTION",
    "decision_view",
    "MENTION_SHORTCUTS",
    "SNAPSHOT_CHAR_CAP",
    "SNAPSHOT_MESSAGE_CAP",
    "Snapshot",
    "mention_findings",
    "APPROVE_VALUE",
    "GATE_ACTIONS",
    "GATE_BLOCK_PREFIX",
    "approve_on_github_line",
    "gate_node_of",
    "gate_answered_line",
    "BUTTON_CHOICE_LIMIT",
    "KICKOFF_REFUSALS",
    "BUTTON_NAMES",
    "CHANGES_VALUE",
    "COMMAND_BUTTONS",
    "COMMAND_DESCRIPTIONS",
    "KICKOFF_COMMANDS",
    "KICKOFF_REPO_ACTION",
    "OPTION_LIMIT",
    "DEFAULT_APP_TOKEN_ENV",
    "DEFAULT_BOT_TOKEN_ENV",
    "DEFAULT_REACTIONS",
    "PHASE_SELECTION_MARKER",
    "CHECKBOX_LIMIT",
    "EXECUTE_ACTION",
    "PHASE_BOX_ACTION",
    "SELECTION_BLOCK",
    "SURFACE_BOX_ACTION",
    "SURFACE_TOKEN",
    "WITHOUT",
    "SelectionRow",
    "SelectionRows",
    "apply_without",
    "compose_selection_execute",
    "github_checklist_line",
    "is_phase_selection",
    "selection_control_blocks",
    "selection_rows",
    "without_clause",
    "EMPTY_CLAUSE",
    "UNKNOWN_PHASE",
    "UNSKIPPABLE_PHASE",
    "read_summary",
    "REACTION_STATES",
    "READ_MODES",
    "CONVERSATION_KINDS",
    "ConversationKind",
    "DEFAULT_CATCH_UP_SECONDS",
    "DEFAULT_SPLIT_CHECK_BEATS",
    "MAX_SPLIT_CHECK_BEATS",
    "MIN_CATCH_UP_SECONDS",
    "kind_from_info",
    "kind_summary",
    "kinds_from_id",
    "probe_subscription",
    "subscription_findings",
    "unchecked_advice",
    "EVENTS_UNVERIFIABLE_CAVEAT",
    "HEARTBEAT_MARKER",
    "SPLIT_CAVEAT",
    "SPLIT_REMEDY",
    "expected_bot_events",
    "heartbeat_nonce",
    "heartbeat_text",
    "SlackBotChannel",
    "SlackChannelConfig",
    "SlackReactionConfig",
    "build_client",
    "catch_up",
    "action_value",
    "expected_commands",
    "is_kickoff_repo_action",
    "kickoff_cursor_key",
    "render_short_blocks",
    "render_kickoff_question",
    "render_reply_blocks",
    "render_root",
    "report_subscription",
    "run_socket_listener",
    "slack_state_path",
]

DEFAULT_BOT_TOKEN_ENV = "THE_LOOP_SLACK_BOT_TOKEN"
DEFAULT_APP_TOKEN_ENV = "THE_LOOP_SLACK_APP_TOKEN"
#: Slack refuses a section over 3000 characters; the cap never exceeds this.
_SECTION_LIMIT = 2900
_HEADER_LIMIT = 150

#: ``gateway`` (issue-503): Slack arrives through the gateway client, and this instance
#: never opens a Socket Mode connection of its own.
READ_MODES: Tuple[str, ...] = ("poll", "socket", "gateway", "off")

#: How often socket mode re-reads the bound threads on top of the one read it
#: runs at connect (issue-362, R3). The reconcile bounds EVERY cause of a missed
#: envelope — a subscription the app does not carry, a Socket Mode reconnect gap,
#: an acknowledgement that raced a restart — not only this ticket's.
DEFAULT_CATCH_UP_SECONDS = 900
#: A reconcile is a safety net, not a second poll transport: each cycle is one
#: ``conversations.history`` plus one ``conversations.replies`` per bound thread.
MIN_CATCH_UP_SECONDS = 60
#: How many heartbeats the listener's own split check posts per cycle
#: (issue-413). The doctor pays three because an operator is waiting on its one
#: run; the watch runs forever, so it buys the same confidence with time instead
#: of messages — two beats detect a split with probability 0.75 per check, which
#: is 99.6% within four checks (one hour at the default cadence).
DEFAULT_SPLIT_CHECK_BEATS = 2
#: The ceiling — a check is a measurement, not a broadcast.
MAX_SPLIT_CHECK_BEATS = 5


@dataclass(frozen=True)
class ConversationKind:
    """One kind of Slack conversation, and what an app needs to hear from it.

    Slack emits a **different message event per kind** and delivers only what the
    app subscribed to, so a channel's kind and the app's subscriptions are one
    fact, not two. Before issue-362 the-loop's manifest carried two of the four
    and nothing related them to the configured channel — which is how a DM could
    be configured, posted into and reported healthy while nothing typed in it was
    ever delivered.
    """

    label: str
    scope: str
    event: str


#: The four kinds, keyed as ``conversations.info`` distinguishes them.
CONVERSATION_KINDS: Dict[str, ConversationKind] = {
    "public": ConversationKind(
        strings.t("channels.slack.kind.public"), "channels:history", "message.channels"
    ),
    "private": ConversationKind(
        strings.t("channels.slack.kind.private"), "groups:history", "message.groups"
    ),
    "im": ConversationKind(
        strings.t("channels.slack.kind.im"), "im:history", "message.im"
    ),
    "mpim": ConversationKind(
        strings.t("channels.slack.kind.mpim"), "mpim:history", "message.mpim"
    ),
}

#: The snapshot `record-context` takes of a thread (issue-389 R4.5): the first
#: `SNAPSHOT_MESSAGE_CAP` messages or `SNAPSHOT_CHAR_CAP` characters, whichever
#: comes first, with the thread's link for the rest. No model summarises.
#: A member mention inside a message's text, drawn by name in a snapshot.
_MENTION_IN_TEXT_RE = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")

SNAPSHOT_MESSAGE_CAP = 150
SNAPSHOT_CHAR_CAP = 40_000
#: GitHub's own ceiling on a comment body; a scrubbed snapshot still over it is
#: refused rather than cut in silence (A9).
GITHUB_COMMENT_LIMIT = 65_000


@dataclass(frozen=True)
class Snapshot:
    """A thread as `record-context` records it: the rendered lines, how many
    messages they cover, the newest ts covered, the thread's permalink, and
    whether the cap cut anything."""

    text: str
    count: int
    newest: str
    permalink: str = ""
    truncated: bool = False


#: The mention (issue-389, decision-133 D1): not a conversation kind but the one
#: event the address arrives as, in every kind the bot is a member of — except a
#: direct message, where Slack does not dispatch it and ``message.im`` stays the
#: input. Measured by the same probe the kinds are, so a missing scope is a
#: finding rather than a silent channel.
MENTION = ConversationKind(
    strings.t("channels.slack.kind.mention"), "app_mentions:read", "app_mention"
)

#: The two message shortcuts the manifest declares (issue-389 R6.1), keyed by
#: ``callback_id`` → the verb each stands for. A shortcut is exactly the typed
#: mention (decision-133 D8): the listener composes that verb and hands it to
#: the pipeline, so the id is the only thing read from the payload's shape.
MENTION_SHORTCUTS: Dict[str, str] = {
    "the-loop:record-context": "record-context",
    "the-loop:record-decision": "record-decision",
}

#: What a conversation id's FIRST CHARACTER can mean (issue-362, decision D2).
#: ``D`` is unambiguous; ``G`` is a legacy private channel or a group DM; ``C`` is
#: public or — since Slack's conversations model — private. Enough to diagnose the
#: reported case with **no network call**, which is what lets ``channels status``
#: keep its contract of calling nothing.
KIND_PREFIXES: Dict[str, Tuple[str, ...]] = {
    "D": ("im",),
    "G": ("private", "mpim"),
    "C": ("public", "private"),
}


def kinds_from_id(channel_id: str) -> Tuple[str, ...]:
    """The kinds a conversation id **could** be, from its prefix — ``()`` when the
    id is unset or is not a conversation id at all (a name, a typo)."""
    first = (channel_id or "").strip()[:1].upper()
    return KIND_PREFIXES.get(first, ())


def kind_from_info(info: Mapping[str, Any]) -> str:
    """The authoritative kind, from a ``conversations.info`` channel object.

    The order is the content: an mpim is also flagged ``is_group`` and
    ``is_private``, and a private channel is also flagged ``is_channel``, so the
    narrowest test has to come first.
    """
    if info.get("is_im"):
        return "im"
    if info.get("is_mpim"):
        return "mpim"
    if info.get("is_private"):
        return "private"
    return "public"


def kind_summary(channel_id: str) -> str:
    """One line for ``channels status``: what this id is, and what it needs."""
    kinds = kinds_from_id(channel_id)
    if not kinds:
        return strings.t("channels.slack.kind-summary.unrecognised")
    labels = " or ".join(CONVERSATION_KINDS[kind].label for kind in kinds)
    scopes = " / ".join(CONVERSATION_KINDS[kind].scope for kind in kinds)
    events = " / ".join(CONVERSATION_KINDS[kind].event for kind in kinds)
    return strings.t(
        "channels.slack.kind-summary.needs",
        labels=labels,
        scopes=scopes,
        events=events,
    )


def unchecked_advice(channel_id: str) -> Tuple[str, ...]:
    """What to say about a channel whose app has **not** been probed (R2.1).

    Only a ``D…`` is called out. It is the one prefix Slack leaves unambiguous
    *and* the one the-loop's manifest could not serve at all before issue-362, so
    a default installation configured with a DM is certainly broken. ``C…`` and
    ``G…`` are ambiguous, and a warning that fires on the configuration most
    operators run is a warning people learn to route around.
    """
    if kinds_from_id(channel_id) != ("im",):
        return ()
    entry = CONVERSATION_KINDS["im"]
    return (
        strings.t(
            "channels.slack.finding.unchecked-dm",
            channel_id=channel_id,
            label=entry.label,
            scope=entry.scope,
            event=entry.event,
        ),
    )


def subscription_findings(
    channel_id: str,
    kinds: Sequence[str],
    scopes: Optional[Sequence[str]],
) -> Tuple[str, ...]:
    """What is **measured** to be wrong with this channel's subscription (R2.5).

    Pure, so the words are asserted once and both callers — ``channels status
    --probe`` and the listener's start-up probe — say the same thing.

    ``scopes`` is the bot token's granted scopes; ``None`` means they could not be
    read (an SDK that did not surface ``x-oauth-scopes``), and yields **no**
    finding rather than a wrong one. A finding needs **every** candidate kind's
    scope to be missing, because ``C…`` and ``G…`` cover two kinds each and only
    ``conversations.info`` can say which. For what to say when nothing was
    probed at all, see :func:`unchecked_advice`.
    """
    if not kinds or scopes is None:
        return ()
    entries = [CONVERSATION_KINDS[kind] for kind in kinds]
    granted = {str(scope).strip() for scope in scopes}
    if any(entry.scope in granted for entry in entries):
        return ()
    labels = " or ".join(entry.label for entry in entries)
    missing_scopes = " / ".join(entry.scope for entry in entries)
    missing_events = " / ".join(entry.event for entry in entries)
    return (
        strings.t(
            "channels.slack.finding.subscription",
            channel_id=channel_id,
            labels=labels,
            missing_scopes=missing_scopes,
            missing_events=missing_events,
        ),
    )


def mention_findings(scopes: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """What is **measured** to be wrong with hearing a mention (issue-389 R1.8).

    ``None`` — the scopes could not be read — yields no finding rather than a
    wrong one, exactly as :func:`subscription_findings`. Pure, so the sentence
    is the same in ``channels status --probe`` and the listener's log.
    """
    if scopes is None:
        return ()
    granted = {str(scope).strip() for scope in scopes}
    if MENTION.scope in granted:
        return ()
    return (
        strings.t(
            "channels.slack.finding.mention", scope=MENTION.scope, event=MENTION.event
        ),
    )


#: The scope a file download needs (issue-416). Read-only, like the directory
#: scopes: it lets the bot fetch a file it can already see in a conversation.
FILES_SCOPE = "files:read"


def attachment_findings(scopes: Optional[Sequence[str]]) -> Tuple[str, ...]:
    """What is **measured** to be wrong with fetching a file (issue-416 R5.2).

    ``None`` — the scopes could not be read — yields no finding rather than a
    wrong one, exactly as :func:`mention_findings`. Without the scope the-loop
    still forwards a message with a file: the file is named and linked, never
    fetched, and the session is told why.
    """
    if scopes is None:
        return ()
    granted = {str(scope).strip() for scope in scopes}
    if FILES_SCOPE in granted:
        return ()
    return (strings.t("channels.slack.finding.attachments", scope=FILES_SCOPE),)


def _granted_scopes(response: Any) -> Optional[Tuple[str, ...]]:
    """The bot token's scopes off a Web API response's ``x-oauth-scopes`` header.

    Slack returns it on every call and it carries no secret (bugfix §AC3).
    ``slack_sdk`` lowercases header names and may hand back a string or a list;
    anything else is **unknown**, which yields no findings rather than a wrong one.
    """
    headers = getattr(response, "headers", None)
    if headers is None and isinstance(response, Mapping):
        headers = response.get("headers")
    if not isinstance(headers, Mapping):
        return None
    raw = headers.get("x-oauth-scopes") or headers.get("X-OAuth-Scopes")
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(item) for item in raw)
    if not isinstance(raw, str):
        return None
    return tuple(scope.strip() for scope in raw.split(",") if scope.strip())


#: Why the probe can name the expected events but never confirm them (issue-393
#: R2.1). Slack's Web API has no method that lists an app's event subscriptions:
#: `auth.test` says which SCOPES were granted, and nothing says which EVENTS the
#: installed app asked for. So an app imported from an older manifest — scopes
#: complete, `app_mention` never subscribed — reads as healthy on every probe
#: while hearing nothing. One fixed sentence, printed beside the scope probe.
EVENTS_UNVERIFIABLE_CAVEAT = strings.t("channels.slack.probe.events-unverifiable")


def expected_bot_events() -> Tuple[str, ...]:
    """The bot events the packaged manifest subscribes to (issue-393 R2.1).

    Read from the in-repo ``slack-app-manifest.yaml`` — the one place the
    subscription is declared, and what an operator imports verbatim — so the
    diagnostic can at least say what the installed app is *expected* to carry.
    ``()`` when the manifest cannot be read: a caveat about events nobody can
    name is worse than silence.
    """
    try:
        import yaml

        # Lazy: `.commands` imports this module at load time.
        from .commands import manifest_text

        data = yaml.safe_load(manifest_text()) or {}
        events = ((data.get("settings") or {}).get("event_subscriptions") or {}).get(
            "bot_events"
        ) or []
        return tuple(str(event).strip() for event in events if str(event).strip())
    except Exception as exc:  # noqa: BLE001 — a diagnostic never fails its caller
        logger.debug("slack: could not read the manifest's bot events: %s", exc)
        return ()


#: The fixed text `the-loop doctor slack` posts to find a second Socket Mode
#: consumer (issue-393 F2 / R2.2), followed by one random nonce and nothing else
#: — never config content. The listener recognises it by this prefix on a
#: bot-posted message and records the receipt instead of reading it as input.
HEARTBEAT_MARKER = "the-loop doctor heartbeat"
_HEARTBEAT_NONCE_RE = re.compile(r"^[a-f0-9]{8,32}$")

#: The caveat every split report carries, word for word. A shortfall is a
#: measurement of an absence, and the absence has innocent causes.
SPLIT_CAVEAT = strings.t("channels.slack.split.caveat")

#: The remedy, in the order an operator should try it — the same sentence in the
#: event, in `status`, in `channels status` and in `doctor slack`, so it is read
#: once and recognised afterwards. The second half is what the issue-413
#: incident actually needed: the phantom consumer's host was never found, and
#: restarting the healthy service changed nothing — only rotating the app-level
#: token fenced the other consumer out.
SPLIT_REMEDY = strings.t("channels.slack.split.remedy")


def heartbeat_text(nonce: str) -> str:
    """The heartbeat message for ``nonce``: marker, one space, the nonce."""
    return f"{HEARTBEAT_MARKER} {nonce}"


def heartbeat_nonce(event: Mapping[str, Any]) -> str:
    """The nonce when ``event`` is the doctor's own heartbeat, else ``""``.

    Only a **bot-posted** message counts (``bot_id`` set, or the ``bot_message``
    subtype): a member typing the marker gets an ordinary message, read through
    the ordinary pipeline, and can neither forge a receipt nor hide a message
    from the-loop by prefixing it.
    """
    if not (event.get("bot_id") or event.get("subtype") == "bot_message"):
        return ""
    text = str(event.get("text") or "").strip()
    prefix = HEARTBEAT_MARKER + " "
    if not text.startswith(prefix):
        return ""
    nonce = text[len(prefix) :].strip()
    return nonce if _HEARTBEAT_NONCE_RE.match(nonce) else ""


def probe_subscription(
    config: "SlackChannelConfig",
    *,
    client_factory: Optional[Callable[[str], Any]] = None,
    channel_id: str = "",
    cli_config: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Ask the installed app what the configured channel is and what it may read.

    Two fixed calls (bugfix §AC4): ``conversations.info`` on the operator's own
    configured channel, and ``auth.test`` for the granted scopes. ``channel_id``
    lets a caller that already resolved the configured value pass the id in; left
    out, a configured **name** is resolved here (PR #376 review). Returns either
    ``{"skipped": why}`` or ``{"kind", "scopes", "findings", "events"}``; it
    never raises, because a diagnostic that fails is not an error (R2.3).
    ``events`` is what the manifest is *expected* to carry (issue-393 R2.1) —
    named, not verified: see :data:`EVENTS_UNVERIFIABLE_CAVEAT`. ``cli_config``
    places the name lookup's directory cache under its ``state.root``; left out,
    the cache resolves against the working directory (issue-422).
    """
    if not config.channel:
        return {"skipped": strings.t("channels.slack.probe.no-channel")}
    token = os.environ.get(config.bot_token_env) or ""
    if not token:
        return {
            "skipped": strings.t(
                "channels.slack.probe.no-bot-token", env=config.bot_token_env
            )
        }
    factory = client_factory or build_client
    # `conversations.info` takes an id; the operator may have declared a NAME
    # (PR #376 review). Resolved here so the diagnostic reports on the channel
    # they meant rather than skipping with an opaque API error.
    channel_id = channel_id or config.channel
    if not is_conversation_id(channel_id):
        from .directory import SlackDirectory

        channel_id = SlackDirectory(
            cli_config, token_env=config.bot_token_env, client_factory=client_factory
        ).conversation_id(channel_id)
        if not channel_id:
            return {
                "skipped": strings.t(
                    "channels.slack.probe.unresolved-channel", channel=config.channel
                )
            }
    try:
        client = factory(token)
        info = (client.conversations_info(channel=channel_id) or {}).get(
            "channel"
        ) or {}
        kind = kind_from_info(info)
        scopes = _granted_scopes(client.auth_test())
    except Exception as exc:  # noqa: BLE001 — a diagnostic never fails its caller
        return {"skipped": f"{type(exc).__name__}: {exc}"}
    return {
        "kind": kind,
        "scopes": scopes,
        # The kind's finding first, then the mention's (issue-389 R1.8): two
        # different absences, each named on its own line.
        "findings": subscription_findings(channel_id, (kind,), scopes)
        + mention_findings(scopes)
        + attachment_findings(scopes),
        # Expected, not measured (issue-393 R2.1) — the caller prints the caveat.
        "events": expected_bot_events(),
    }


#: Block Kit action ids the-loop renders — and the only ones it acts on.
ACTION_PREFIX = "the-loop:"
#: The gate pair's actions block id: this prefix and the gate's node, so a press
#: names the gate it answers (issue-549 abuse case 8).
GATE_BLOCK_PREFIX = f"{ACTION_PREFIX}gate:"
#: The two buttons that answer a gate.
GATE_ACTIONS = (f"{ACTION_PREFIX}approve", f"{ACTION_PREFIX}changes")
#: Slack's ceiling on a ``block_id``.
_BLOCK_ID_LIMIT = 255
#: The button values, which are the words `classify-feedback` already reads.
APPROVE_VALUE = "approved"
CHANGES_VALUE = "changes requested"
_BUTTON_VALUES = (APPROVE_VALUE, CHANGES_VALUE)
#: Slack's ceiling on a button's ``value`` (issue-393 B9): a stated default longer
#: than this is clipped rather than refused — the reply still carries the answer.
_BUTTON_VALUE_LIMIT = 2000

#: The command buttons (issue-337): control command → the label a member sees.
#: Fixed; the button's VALUE is the configured keyword, read from
#: ``routing.control.keywords`` so a press is exactly a typed keyword.
COMMAND_BUTTONS: Dict[str, str] = strings.section("slack.command-button")
#: The loops a newly opened work item is offered, in render order (issue-529):
#: the ad-hoc loop first, the full PDLC second, so neither is the default.
KICKOFF_COMMANDS: Tuple[str, ...] = ("do", "start")
#: What each offered loop runs, one line under the reply (issue-529 R1.2). Fixed
#: words, never the member's text; a command without one renders no line.
COMMAND_DESCRIPTIONS: Dict[str, str] = strings.section("slack.command-description")

#: The repository picker (issue-349): the one action whose value is an ARGUMENT to
#: something the-loop has not done yet, rather than an answer to a gate or a
#: keyword typed back. Buttons and the select menu share it, so the handler has one
#: branch to read rather than two.
KICKOFF_REPO_ACTION = f"{ACTION_PREFIX}kickoff-repo"
#: At or below this many repositories the question is buttons; above it, a select
#: menu. Five is where a row of buttons stops being one glance on a phone.
BUTTON_CHOICE_LIMIT = 5
#: Slack's own ceiling for a static select. Past it the question offers the first
#: `OPTION_LIMIT` in declaration order and names the `<repo>: ` prefix for the rest.
OPTION_LIMIT = 100
#: Slack's ceiling for one option's (or button's) visible text.
_OPTION_TEXT_LIMIT = 75

#: action_id → the name the press outcome line uses — never the payload's own
#: button text (R2.6).
BUTTON_NAMES: Dict[str, str] = {
    f"{ACTION_PREFIX}approve": strings.t("slack.button.approve"),
    f"{ACTION_PREFIX}changes": strings.t("slack.button.changes"),
    KICKOFF_REPO_ACTION: strings.t("slack.button.kickoff-repo"),
    **{
        f"{ACTION_PREFIX}command:{command}": label
        for command, label in COMMAND_BUTTONS.items()
    },
}
#: The phase-selection hook's own marker (``graph/hooks/selection.py``) — the one
#: message that asks for ``the-loop execute`` typed back, recognised in its
#: ``comment.agent`` mirror. Pinned to the hook's constant by a test; spelled here
#: so rendering a Slack message never imports the graph.
PHASE_SELECTION_MARKER = "<!-- the-loop:phase-selection -->"


# -- the phase-selection control (issue-393 R9) --------------------------------------
#
# The checklist the hook posts on the ticket asks for boxes to be ticked; Slack
# cannot tick a mirrored comment, so in a room that can receive a press the same
# question is drawn as Block Kit checkboxes — the phases pre-ticked as the
# checklist ticks them, the outer-loop question as an element of its own (R9.2),
# Execute beside them. Pressing Execute composes the very reply a person types
# on GitHub with the list in it: the keyword, then `- [x]` / `- [ ]` rows — so
# the gate's one parser (`selection._parse_selection`) reads a Slack selection
# exactly as it reads a typed one, and no second freeze path exists.

#: One checklist row — the hook's ``_CHECK_LINE`` (``graph/hooks/selection.py``)
#: with the rest of the line captured. Spelled here for the reason the marker
#: is (rendering imports no graph) and pinned to the hook's grammar by a test.
_CHECKLIST_ROW = re.compile(
    r"^\s*(?:>\s*)*[-*]\s*\[(?P<mark>[ xX])\]\s*`?(?P<token>[A-Za-z0-9][A-Za-z0-9._-]*)`?"
    r"(?P<about>[^\n]*)",
    re.MULTILINE,
)
#: A protected phase's row — a bare bullet naming a node and nothing else, the
#: shape of the checklist's "these phases always run" list.
_PLAIN_ROW = re.compile(
    r"^[ \t]*[-*][ \t]+(?P<token>[A-Za-z0-9][A-Za-z0-9._-]*)[ \t]*$", re.MULTILINE
)
#: A token a row may carry — what a checkbox ``value`` and a reply's name are
#: validated against before either is written into a record.
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,74}$")

#: The checklist's rows that are NOT phases: the hook's ``SURFACE_TOKEN`` and
#: ``CLAUDE_ARTIFACT_TOKEN`` (issue-471), ``CLAUDE_DOC_TOKEN`` (issue-536),
#: ``EXPLAINER_TOKEN`` (issue-488), and the prefixes of its
#: ``PR_SESSIONS_TOKENS`` / ``HARNESS_PREFIX`` / ``MODEL_PREFIX`` / ``EFFORT_PREFIX``
#: rows. Pinned to the hook's by a test, like the marker.
SURFACE_TOKEN = "outer-loop-on-pull-request"
CLAUDE_ARTIFACT_TOKEN = "claude-artifact"
CLAUDE_DOC_TOKEN = "claude-doc"
EXPLAINER_TOKEN = "explainer"
_NON_PHASE_PREFIXES = (
    "pr-sessions-",
    "harness-",
    "model-",
    "effort-",
    f"{EXPLAINER_TOKEN}-",
)


def _is_setting_token(token: str) -> bool:
    """Whether a checklist row is a setting rather than a phase."""
    return token in (
        SURFACE_TOKEN,
        CLAUDE_ARTIFACT_TOKEN,
        CLAUDE_DOC_TOKEN,
        EXPLAINER_TOKEN,
    ) or token.startswith(_NON_PHASE_PREFIXES)


#: The control's own ids. A block id under :data:`SELECTION_BLOCK` is part of the
#: control — the state a press carries is keyed by it, and the press report takes
#: it away once the press landed (it acted once, like the button).
SELECTION_BLOCK = f"{ACTION_PREFIX}selection"
PHASE_BOX_ACTION = f"{ACTION_PREFIX}phase-box"
SURFACE_BOX_ACTION = f"{ACTION_PREFIX}surface-box"
EXECUTE_ACTION = f"{ACTION_PREFIX}command:execute"
#: Slack's ceiling on one checkboxes element's options; a longer list is chunked.
CHECKBOX_LIMIT = 10
#: The reply grammar's one word (R9.3, F1): ``<execute keyword> without <n, …>``.
WITHOUT = "without"
#: Why a typed `without` reply was refused (issue-405 P1) — the drop label the
#: caller records, one per family: a name or number the checklist does not
#: offer (or a word that is not a name at all), a protected phase, a clause that
#: names nothing. `checklist-unreadable` is the caller's own, fourth family.
UNKNOWN_PHASE = "unknown-phase"
UNSKIPPABLE_PHASE = "unskippable-phase"
EMPTY_CLAUSE = "empty-clause"
#: What the split words of a clause are stripped of before they are read as a
#: name or number: quoting, brackets, trailing punctuation — and (issue-405 P1)
#: Slack's own markup, because `*5*` is 5 and `_design_` is design.
_ITEM_WRAPPERS = "`'\"“”.:!?()[]{}*_~"
#: The question's emoji — one state emoji per message (R11.1), the one a question
#: carries in the voice table.
_SELECTION_EMOJI = "🤔"


@dataclass(frozen=True)
class SelectionRow:
    """One box of the checklist: its token, its tick, and the words beside it."""

    token: str
    ticked: bool
    about: str = ""


@dataclass(frozen=True)
class SelectionRows:
    """What a phase-selection checklist offers, read off its own text.

    ``phases`` are the selectable phase rows in checklist order — the order the
    reply grammar's numbers count; ``surface`` the outer-loop row when the loop
    asks it; ``others`` the rows that are neither (sessions, model, effort);
    ``always`` the protected phases named as plain bullets.
    """

    phases: Tuple[SelectionRow, ...]
    surface: Optional[SelectionRow] = None
    others: Tuple[SelectionRow, ...] = ()
    always: Tuple[str, ...] = ()

    def phase(self, name: str) -> Optional[SelectionRow]:
        """The phase row ``name`` names, case-insensitively — ``None`` for none."""
        wanted = name.strip().strip("`").lower()
        for row in self.phases:
            if row.token.lower() == wanted:
                return row
        return None


def _about(rest: str) -> str:
    """The words after a row's token, without the dash that joins them."""
    return " ".join(rest.strip().lstrip("—-–:").split())


def is_phase_selection(event: Event) -> bool:
    """Whether ``event`` is the checklist's mirror — the hook's own comment,
    carrying its marker. A human's comment never is, whatever it quotes."""
    return event.event_type == "comment.agent" and PHASE_SELECTION_MARKER in event.text


def selection_rows(text: str) -> Optional[SelectionRows]:
    """The rows of a phase-selection checklist body — ``None`` for any other text.

    Read off the checklist's own markdown, because the phase names exist nowhere
    else the channel can see: the rows are the hook's rendering of the graph the
    work item walks, and this is their one transcription. A token appearing twice
    keeps its first row.
    """
    if PHASE_SELECTION_MARKER not in (text or ""):
        return None
    phases: List[SelectionRow] = []
    others: List[SelectionRow] = []
    surface: Optional[SelectionRow] = None
    seen: set = set()
    for match in _CHECKLIST_ROW.finditer(text):
        token = match.group("token")
        if token in seen:
            continue
        seen.add(token)
        row = SelectionRow(
            token, bool(match.group("mark").strip()), _about(match.group("about"))
        )
        if token == SURFACE_TOKEN:
            surface = row
        elif _is_setting_token(token):
            others.append(row)
        else:
            phases.append(row)
    always = tuple(
        dict.fromkeys(
            match.group("token")
            for match in _PLAIN_ROW.finditer(text)
            if match.group("token") not in seen
        )
    )
    return SelectionRows(tuple(phases), surface, tuple(others), always)


def _row_line(token: str, ticked: bool, *, code: bool = False) -> str:
    """One checklist row as the hook writes it — a phase bare, any other token in
    backticks — which is exactly the shape its parser reads back."""
    name = f"`{token}`" if code else token
    return f"- [{'x' if ticked else ' '}] {name}"


def _mrkdwn(text: str) -> Dict[str, Any]:
    return {"type": "mrkdwn", "text": text}


def _checkbox_option(number: int, row: SelectionRow) -> Dict[str, Any]:
    """One option: numbered as the reply grammar counts it, the token as its
    value, the checklist's own words (or the opt-in note) as its description."""
    option: Dict[str, Any] = {
        "text": _mrkdwn(f"{number}. `{row.token}`"[:_OPTION_TEXT_LIMIT]),
        "value": row.token,
    }
    about = row.about or (
        "" if row.ticked else strings.t("channels.slack.selection.optional")
    )
    if about:
        option["description"] = _mrkdwn(about[:_OPTION_TEXT_LIMIT])
    return option


def selection_control_blocks(rows: SelectionRows, keyword: str) -> List[Dict[str, Any]]:
    """The checklist as a control (R9.1, R9.2): the question, one checkboxes
    element per ten phases (pre-ticked as the checklist is), the outer-loop
    question as its own element, and a note on what is NOT chosen here.

    No Execute button here — the caller draws it in the message's actions block,
    as it does today, so a press is the same press.
    """
    opt_in = any(not row.ticked for row in rows.phases)
    lead = (
        strings.t("channels.slack.selection.lead", emoji=_SELECTION_EMOJI)
        + (strings.t("channels.slack.selection.lead-opt-in") if opt_in else "")
        + strings.t("channels.slack.selection.lead-end")
    )
    blocks: List[Dict[str, Any]] = [{"type": "section", "text": _mrkdwn(lead)}]
    for index in range(0, len(rows.phases), CHECKBOX_LIMIT):
        chunk = rows.phases[index : index + CHECKBOX_LIMIT]
        group = index // CHECKBOX_LIMIT
        label = (
            strings.t("channels.slack.selection.phases-label")
            if group == 0
            else strings.t("channels.slack.selection.phases-label-continued")
        )
        options = [
            _checkbox_option(index + offset + 1, row)
            for offset, row in enumerate(chunk)
        ]
        element: Dict[str, Any] = {
            "type": "checkboxes",
            "action_id": f"{PHASE_BOX_ACTION}:{group}",
            "options": options,
        }
        initial = [option for option, row in zip(options, chunk) if row.ticked]
        if initial:
            element["initial_options"] = initial
        blocks.append(
            {
                "type": "section",
                "block_id": f"{SELECTION_BLOCK}:phases-label:{group}",
                "text": _mrkdwn(label),
            }
        )
        blocks.append(
            {
                "type": "actions",
                "block_id": f"{SELECTION_BLOCK}:phases:{group}",
                "elements": [element],
            }
        )
    if rows.surface is not None:
        option = {
            "text": _mrkdwn(strings.t("channels.slack.selection.surface-option")),
            "value": SURFACE_TOKEN,
        }
        element = {
            "type": "checkboxes",
            "action_id": SURFACE_BOX_ACTION,
            "options": [option],
        }
        if rows.surface.ticked:
            element["initial_options"] = [option]
        blocks.append(
            {
                "type": "section",
                "block_id": f"{SELECTION_BLOCK}:surface-label",
                "text": _mrkdwn(strings.t("channels.slack.selection.surface-question")),
            }
        )
        blocks.append(
            {
                "type": "actions",
                "block_id": f"{SELECTION_BLOCK}:surface",
                "elements": [element],
            }
        )
    notes: List[str] = []
    if rows.always:
        notes.append(
            strings.t(
                "channels.slack.selection.always-run",
                nodes=", ".join(f"`{node}`" for node in rows.always),
            )
        )
    notes.append(strings.t("channels.slack.selection.defaults-note", keyword=keyword))
    blocks.append({"type": "context", "elements": [_mrkdwn(" ".join(notes))]})
    return blocks


def github_checklist_line(url: str, keyword: str) -> str:
    """What a room that cannot carry the control is told instead (R9.4): the
    checklist is edited on GitHub — linked — and the reply is said there."""
    on_github = strings.t("channels.slack.checklist.on-github")
    where = f"<{url}|{on_github}>" if url else on_github
    say = (
        strings.t("channels.slack.checklist.reply-keyword", keyword=keyword)
        if keyword
        else strings.t("channels.slack.checklist.reply-execute")
    )
    return strings.t("channels.slack.checklist.edited-on-github", where=where, say=say)


def _control_groups(
    message: Mapping[str, Any],
) -> List[Tuple[str, str, List[Tuple[str, bool]]]]:
    """``(block_id, action_id, [(token, initially ticked), …])`` for every
    checkboxes element of the control in ``message``, in message order — read
    off the blocks the bot itself posted, values validated as tokens."""
    groups: List[Tuple[str, str, List[Tuple[str, bool]]]] = []
    for block in message.get("blocks") or []:
        if not isinstance(block, Mapping) or block.get("type") != "actions":
            continue
        block_id = str(block.get("block_id") or "")
        if not block_id.startswith(SELECTION_BLOCK):
            continue
        for element in block.get("elements") or []:
            if not isinstance(element, Mapping) or element.get("type") != "checkboxes":
                continue
            action_id = str(element.get("action_id") or "")
            if not (
                action_id.startswith(PHASE_BOX_ACTION)
                or action_id == SURFACE_BOX_ACTION
            ):
                continue
            initial = {
                str(o.get("value") or "")
                for o in element.get("initial_options") or []
                if isinstance(o, Mapping)
            }
            options = [
                (str(o.get("value")), str(o.get("value")) in initial)
                for o in element.get("options") or []
                if isinstance(o, Mapping) and _TOKEN_RE.match(str(o.get("value") or ""))
            ]
            if options:
                groups.append((block_id, action_id, options))
    return groups


def _chosen(state: Any, block_id: str, action_id: str) -> Optional[set]:
    """The values ticked in one element per the press's ``state`` — ``None`` when
    the state does not carry that element at all (or not in a readable shape)."""
    if not isinstance(state, Mapping):
        return None
    values = state.get("values")
    if not isinstance(values, Mapping):
        return None
    block = values.get(block_id)
    if not isinstance(block, Mapping):
        return None
    element = block.get(action_id)
    if not isinstance(element, Mapping):
        return None
    selected = element.get("selected_options")
    if not isinstance(selected, list):
        return None
    return {
        str(option.get("value") or "")
        for option in selected
        if isinstance(option, Mapping)
    }


def compose_selection_execute(
    keyword: str, message: Mapping[str, Any], state: Any
) -> str:
    """The reply an Execute press composes on the control (R9.1).

    The keyword, then one `- [x]` / `- [ ]` row per box the message offered,
    ticked as the press's ``state.values`` says — the list a person puts in an
    execute comment on GitHub, which the gate reads over the checklist. A
    message without the control composes the bare keyword, as it always did.

    Fail-closed, the gate's own way: an element the state does not carry (a
    partial or malformed payload) keeps the ticks it was drawn with — every
    default-on phase runs, no opt-in does, the outer loop stays on the work
    item — so a broken press can only ever ask for *more* process. A value the
    message never offered is not a box and is ignored.
    """
    groups = _control_groups(message)
    if not groups:
        return keyword
    lines: List[str] = []
    for block_id, action_id, options in groups:
        chosen = _chosen(state, block_id, action_id)
        for token, initial in options:
            ticked = initial if chosen is None else token in chosen
            lines.append(
                _row_line(token, ticked, code=(action_id == SURFACE_BOX_ACTION))
            )
    return f"{keyword}\n\n" + "\n".join(lines)


def _clean_item(raw: str) -> str:
    """One split word of a clause, as the name or number it is (issue-405 P1):
    invisible format characters (a zero-width space a client pasted in) removed,
    then quoting, brackets, punctuation and Slack markup around it stripped."""
    bare = "".join(ch for ch in raw if unicodedata.category(ch) != "Cf")
    return bare.strip().strip(_ITEM_WRAPPERS)


def without_clause(text: str, keyword: str) -> Optional[List[str]]:
    """The names and numbers after ``<keyword> without`` in ``text`` — ``[]`` for
    a clause naming nothing, ``None`` when the text carries no such clause.

    The clause is the rest of the keyword's **line** — every word of it, so a
    word that is not a phase refuses the reply rather than being skipped over
    (abuse case 4) — read after a connector's signature is dropped
    (:func:`~.verbs.strip_signature`, issue-405 P1: the live message did not
    end where the operator's list ended) and with each word cleaned of the
    markup a client wraps a name in (:func:`_clean_item`).
    """
    if not keyword or not text:
        return None
    from .verbs import strip_signature

    pattern = (
        r"(?<![\w:-])"
        + re.escape(keyword)
        + r"[ \t]+"
        + WITHOUT
        + r"(?![\w-])(?P<rest>[^\n]*)"
    )
    match = re.search(pattern, strip_signature(text), re.IGNORECASE)
    if match is None:
        return None
    items = []
    for raw in re.split(r"[\s,;]+", match.group("rest")):
        item = _clean_item(raw)
        if item and item.lower() not in ("and", "&", "the", "phase", "phases"):
            items.append(item)
    return items


def _is_name(item: str) -> bool:
    """Whether ``item`` is token-shaped — what a refusal may echo and a row may
    carry; anything else (prose, markup, a broadcast, an overlong string) is not."""
    return bool(_TOKEN_RE.match(item)) and len(item) <= 40


def _safe_name(item: str) -> str:
    """``item`` as a refusal may echo it: a token, in backticks — anything else
    (prose, markup, a broadcast) is named as *that*, never repeated."""
    return (
        f"`{item}`" if _is_name(item) else strings.t("channels.slack.without.that-name")
    )


def read_summary(items: Sequence[str]) -> List[str]:
    """``items`` as the drop record may carry them (issue-405 P1): a name
    verbatim, anything else as its length only — the diagnostic the report asked
    for, without a broadcast, a mention or prose reaching the event log."""
    return [
        item if _is_name(item) else f"<non-token: {len(item)} chars>" for item in items
    ]


def _offered(rows: SelectionRows) -> str:
    listed = ", ".join(f"{n}. `{row.token}`" for n, row in enumerate(rows.phases, 1))
    return strings.t("channels.slack.without.offered", listed=listed)


def apply_without(
    rows: SelectionRows, items: Sequence[str], keyword: str
) -> Tuple[str, str, str]:
    """``(composed reply, refusal, reason)`` for ``execute without <items>`` (R9.3).

    The checklist as it stands, every row kept as ticked, with the named phases
    — by number in checklist order, or by name — unticked; the keyword first,
    the list after, the reply the gate reads over the checklist. **Any item that
    is not one of the offered phases refuses the whole reply** with the reason
    (abuse case 4): a typo, a protected phase, a row that is not a phase — none
    of them may quietly freeze a selection other than the one that was asked.
    ``reason`` is the refusal's family (:data:`UNKNOWN_PHASE`,
    :data:`UNSKIPPABLE_PHASE`, :data:`EMPTY_CLAUSE`; ``""`` when composed), the
    drop label the caller records (issue-405 P1). A word that is not a name at
    all is refused by its **position**, so the operator learns which word broke
    the line without the word being repeated.
    """
    if not items:
        return (
            "",
            strings.t("channels.slack.without.empty", without=WITHOUT) + _offered(rows),
            EMPTY_CLAUSE,
        )
    drop: set = set()
    for position, item in enumerate(items, 1):
        if item.isdigit():
            number = int(item)
            if not 1 <= number <= len(rows.phases):
                return (
                    "",
                    strings.t("channels.slack.without.no-such-number", number=number)
                    + _offered(rows),
                    UNKNOWN_PHASE,
                )
            drop.add(rows.phases[number - 1].token)
            continue
        if not _is_name(item):
            return (
                "",
                strings.t(
                    "channels.slack.without.not-a-name",
                    position=position,
                    without=WITHOUT,
                )
                + _offered(rows),
                UNKNOWN_PHASE,
            )
        row = rows.phase(item)
        if row is None:
            if item.lower() in {node.lower() for node in rows.always}:
                return (
                    "",
                    strings.t(
                        "channels.slack.without.unskippable", name=_safe_name(item)
                    )
                    + _offered(rows),
                    UNSKIPPABLE_PHASE,
                )
            return (
                "",
                strings.t("channels.slack.without.unknown", name=_safe_name(item))
                + _offered(rows),
                UNKNOWN_PHASE,
            )
        drop.add(row.token)
    lines = [
        _row_line(row.token, row.ticked and row.token not in drop)
        for row in rows.phases
    ]
    if rows.surface is not None:
        lines.append(_row_line(SURFACE_TOKEN, rows.surface.ticked, code=True))
    lines += [_row_line(row.token, row.ticked, code=True) for row in rows.others]
    return f"{keyword}\n\n" + "\n".join(lines), "", ""


def build_client(token: str):
    """The real SDK client. Module-level so tests substitute it in one place."""
    from slack_sdk import WebClient  # type: ignore[import-not-found]

    return WebClient(token=token)


# -- where outbound Slack goes (issue-519) ----------------------------------------


@dataclass(frozen=True)
class PostingPath:
    """Where this instance's Slack calls go (issue-519, R4): ``local`` — its own bot
    token (``detail`` is the variable's name); ``gateway`` — the gateway makes them
    (``detail`` is its URL); ``none`` — nothing can post (``detail`` says why, in the
    words `start`, `status`, `channels status` and `doctor slack` all print)."""

    kind: str
    detail: str


def posting_path(
    config: "SlackChannelConfig",
    cli_config: Optional[Mapping[str, Any]],
    *,
    gateway_posting: Optional[str] = None,
) -> PostingPath:
    """Own token first (R4.1); else the gateway when a usable block is present and the
    gateway reports posting ``on`` — or could not be asked (``None``/``unknown``), in
    which case the call itself is the probe (R4.2); else ``none`` with the reason
    (R4.3). One resolver, so posting and the operator's wording cannot disagree."""
    if os.environ.get(config.bot_token_env):
        return PostingPath("local", config.bot_token_env)
    block = gateway_block(cli_config) if cli_config is not None else None
    if block is None:
        return PostingPath(
            "none",
            strings.t("channels.slack.posting.no-gateway", env=config.bot_token_env),
        )
    if gateway_posting in (None, "on", "unknown"):
        return PostingPath("gateway", block.url)
    return PostingPath(
        "none",
        strings.t(
            "channels.slack.posting.gateway-off",
            env=config.bot_token_env,
            url=block.url,
            posting=gateway_posting,
        ),
    )


def outbound_client(
    config: "SlackChannelConfig",
    cli_config: Optional[Mapping[str, Any]],
    client_factory: Optional[Callable[[str], Any]] = None,
) -> Any:
    """The client every outbound Slack call uses (issue-519, R4.2): the SDK client on
    the local token, a :class:`~the_loop.channels.slack_gateway.GatewaySlackClient`
    behind a gateway, else today's :class:`ChannelError` with the gateway hint (R4.3).
    A ``client_factory`` (a test's fake) is honoured on either live path."""
    path = posting_path(config, cli_config)
    if path.kind == "local":
        factory = client_factory or build_client
        return factory(os.environ.get(config.bot_token_env) or "")
    if path.kind == "gateway":
        if client_factory is not None:
            return client_factory("")
        from .slack_gateway import GatewaySlackClient

        return GatewaySlackClient.from_cli_config(cli_config or {})
    raise ChannelError(
        f"slack: no bot token — export {config.bot_token_env} "
        "(an xoxb- bot token with chat:write, and channels.history for reads), "
        "or point this instance at a gateway with slack.post.enabled"
    )


def slack_state_path(cli_config: Optional[Mapping[str, Any]]) -> Path:
    """Where this channel's bindings live — ``<state.root>/channels/slack.json``."""
    from ..state import layout_from_config

    return Path(layout_from_config(dict(cli_config or {})).channels_dir) / "slack.json"


def _files_of(message: Mapping[str, Any]) -> Tuple[Mapping[str, Any], ...]:
    """The file objects on a Slack message, as sent (issue-416); a message
    without any — or with a malformed ``files`` — carries the empty tuple."""
    raw = message.get("files")
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(f for f in raw if isinstance(f, Mapping))


def kickoff_cursor_key(channel_id: str) -> str:
    """The cursor key for a channel's top-level read — beside the thread cursors,
    prefixed so it can never collide with a thread ts."""
    return f"channel:{channel_id}"


#: The three moments the channel acknowledges on the accepted message (issue-325):
#: ``received`` after the last refusal and before the record, then ``completed``
#: or ``error`` from the outcome — the lifecycle `routing.reactions` marks on GitHub.
REACTION_STATES: Tuple[str, ...] = ("received", "completed", "error")
#: Slack's own palette, which has the ✅ GitHub's does not (decision-111 D3).
DEFAULT_REACTIONS: Dict[str, str] = {
    "received": "eyes",
    "completed": "white_check_mark",
    "error": "warning",
}
#: A Slack emoji name — built-in or a workspace's custom one — as `reactions.add`
#: takes it: no colons, no skin-tone suffix needed for a reaction.
_EMOJI_NAME_RE = re.compile(r"^[a-z0-9_+-]{1,100}$")


@dataclass(frozen=True)
class SlackReactionConfig:
    """The parsed ``channels.slack.reactions`` block (issue-325). Mirrors the
    *contract* of ``routing.reactions`` — on by default, one name per state, ``""``
    skips a state, best-effort — not its values: the two palettes differ."""

    enabled: bool = True
    received: str = DEFAULT_REACTIONS["received"]
    completed: str = DEFAULT_REACTIONS["completed"]
    error: str = DEFAULT_REACTIONS["error"]

    def content_for(self, state: str) -> str:
        """The emoji name for ``state`` — ``""`` for a skipped or unknown one."""
        return {
            "received": self.received,
            "completed": self.completed,
            "error": self.error,
        }.get(state, "")

    @classmethod
    def from_mapping(cls, raw: Any) -> "SlackReactionConfig":
        """Parse the block. A name outside the grammar is refused per state — a
        warning, and that state skipped — so config can never craft an API
        argument (R2.3, A4); surrounding colons are stripped first, because
        ``:eyes:`` is how Slack renders a name and how people copy it."""
        if raw is None:
            return cls()
        if not isinstance(raw, Mapping):
            logger.warning(
                "channels.slack.reactions is not a mapping — using the defaults"
            )
            return cls()
        names: Dict[str, str] = {}
        for state in REACTION_STATES:
            value = raw.get(state, DEFAULT_REACTIONS[state])
            name = str(value if value is not None else "").strip().strip(":")
            if name and not _EMOJI_NAME_RE.match(name):
                logger.warning(
                    "channels.slack.reactions.%s %r is not a Slack emoji name "
                    "(lowercase letters, digits, _ + -, no colons) — that "
                    "reaction is skipped",
                    state,
                    value,
                )
                name = ""
            names[state] = name
        return cls(enabled=bool(raw.get("enabled", True)), **names)


@dataclass(frozen=True)
class SlackChannelConfig:
    """The parsed ``channels.slack`` CLI-config section. Frozen; fail-closed."""

    enabled: bool = False
    bot_token_env: str = DEFAULT_BOT_TOKEN_ENV
    app_token_env: str = DEFAULT_APP_TOKEN_ENV
    channel: str = ""
    subscribe: Tuple[str, ...] = DEFAULT_EVENTS
    publish: Tuple[str, ...] = DEFAULT_PUBLISH
    verbosity: str = "normal"
    #: How a work item's own room reads (issue-393 B8): ``agentic`` (the default
    #: — one message per moment, first-person voice, no machine header, gates
    #: collapsed, progress edited in place) or ``classic`` (16.x's rendering,
    #: byte-for-byte, the escape hatch and the compatibility proof). Read from
    #: ``channels.slack.room.style``; anything else is ``agentic``.
    room_style: str = "agentic"
    kickoff_repo: str = ""
    kickoff_labels: Tuple[str, ...] = ()
    #: The people of `routing.authorizedUsers`, and their Slack ids (issue-309).
    principals: Tuple[Principal, ...] = ()
    authorized_users: Tuple[str, ...] = ()
    read_mode: str = "poll"
    #: Whether the config carries a usable ``gateway`` block (issue-503) — the other
    #: half of :attr:`push_reachable` in ``gateway`` mode.
    gateway: bool = False
    read_interval_seconds: float = 30.0
    #: How often socket mode re-reads the bound threads on top of the connect-time
    #: read (issue-362). ``0`` means connect-only — 16.0.1's behaviour.
    catch_up_seconds: int = DEFAULT_CATCH_UP_SECONDS
    #: How many heartbeats the listener's own split check posts per cycle
    #: (issue-413). ``0`` turns the check off entirely — nothing is posted.
    split_check_beats: int = DEFAULT_SPLIT_CHECK_BEATS
    #: The acknowledgment on an accepted inbound message (issue-325).
    reactions: SlackReactionConfig = SlackReactionConfig()
    #: Every control command and its configured keyword (issue-337) — the values
    #: the command buttons carry, read from ``routing.control.keywords``; the
    #: shipped defaults when a config is built without one.
    control_keywords: Tuple[Tuple[str, str], ...] = field(
        default_factory=lambda: _control_keywords(None)
    )

    @property
    def events(self) -> Tuple[str, ...]:
        """The pre-issue-309 name of :attr:`subscribe`."""
        return self.subscribe

    @property
    def push_reachable(self) -> bool:
        """Whether an interactive payload can reach this instance (issue-503): over its
        own Socket Mode connection, or delivered by the gateway client."""
        return self.read_mode == "socket" or (
            self.read_mode == "gateway" and self.gateway
        )

    @property
    def interactive(self) -> bool:
        """Whether an action button can be received: a press can reach this instance
        (:attr:`push_reachable`) AND the grant (decision-103 D5) — a button nobody can
        receive is worse than none."""
        return self.push_reachable and "gate.feedback" in self.publish

    @property
    def command_buttons(self) -> bool:
        """Whether an Execute / Do / Start button can be received AND acted on: a press can
        reach this instance and the ``control.command`` grant (issue-337 R1.4) — the
        same rule :attr:`interactive` applies to the Approve pair."""
        return self.push_reachable and "control.command" in self.publish

    def keyword(self, command: str) -> str:
        """The configured keyword for ``command`` — ``""`` for an unknown command
        or one the operator disabled."""
        return dict(self.control_keywords).get(command, "")

    def command_buttons_for(self, *commands: str) -> Dict[str, str]:
        """``command → keyword`` for the buttons this channel may render now:
        empty unless :attr:`command_buttons`; a disabled keyword is left out."""
        if not self.command_buttons:
            return {}
        return {
            command: self.keyword(command)
            for command in commands
            if self.keyword(command)
        }

    @property
    def kickoff_enabled(self) -> bool:
        """Whether a top-level message may be read at all: the channel, and the
        grant. **Not** a target — the message names its own (issue-341,
        decision-120 D4), and ``kickoff.repo`` is only the fallback it uses when
        it does not."""
        return bool(
            self.enabled and self.channel and "work-item.create" in self.publish
        )

    @property
    def kickoff_picker(self) -> bool:
        """Whether the kickoff may ASK which repository (issue-349, decision-122 D1).

        The same two-part rule :attr:`interactive` and :attr:`command_buttons`
        apply, with the grant that is **already** required to reach the kickoff at
        all: a press that can reach this instance (Socket Mode, or the gateway's
        delivery since issue-503 — decision-116 D5 says an interactive payload
        reaches the-loop no other way), and ``work-item.create``, because that is
        what the answer does. No new grant, no new key. In ``poll`` mode the typed
        ``<repo>: `` prefix stays the only route and the refusal is unchanged.
        """
        return self.push_reachable and self.kickoff_enabled

    @classmethod
    def from_mapping(cls, cli_config: Optional[Mapping]) -> "SlackChannelConfig":
        """Parse the whole CLI config. A malformed section is **disabled**,
        loudly — the ingress rule that a broken config never breaks a daemon."""
        config = cli_config or {}
        channels = config.get("channels") or {}
        if not isinstance(channels, Mapping):
            logger.error(
                "channels: the config section is not a mapping — the slack "
                "channel is disabled (fail closed)"
            )
            return cls()
        section = channels.get("slack") or {}
        if not isinstance(section, Mapping):
            logger.error(
                "channels.slack: the section is not a mapping — the channel "
                "is disabled (fail closed)"
            )
            return cls()
        routing = config.get("routing") or {}
        principals = tuple(
            parse_authorized_users(routing.get("authorizedUsers"))
            if isinstance(routing, Mapping)
            else ()
        )
        control_keywords = _control_keywords(
            routing.get("control") if isinstance(routing, Mapping) else None
        )
        try:
            read = section.get("read") or {}
            if not isinstance(read, Mapping):
                read = {}
            mode = str(read.get("mode", "poll"))
            if mode not in READ_MODES:
                # Never resolve an unknown value to a READING mode: a typo must
                # not silently start ingesting a Slack channel.
                logger.warning(
                    "channels.slack.read.mode %r is not one of %s — resolving to 'off'",
                    mode,
                    "/".join(READ_MODES),
                )
                mode = "off"
            gateway = gateway_block(config) is not None
            if mode == "gateway" and not gateway:
                # issue-503 R3.1: never fall back to a socket of our own — a deleted
                # block must not put a second consumer on the gateway's app.
                logger.error(
                    "channels.slack.read.mode is 'gateway' but no usable gateway: "
                    "block is configured — nothing is read from Slack (fail closed); "
                    "add gateway.url, or set read.mode"
                )
                mode = "off"
            verbosity = str(section.get("verbosity", "normal"))
            if verbosity not in VERBOSITIES:
                logger.warning(
                    "channels.slack.verbosity %r is not one of %s — resolving "
                    "to 'normal'",
                    verbosity,
                    "/".join(VERBOSITIES),
                )
                verbosity = "normal"
            for removed, replacement in (
                ("events", "channels.slack.subscribe"),
                ("authorizedUsers", "routing.authorizedUsers"),
            ):
                if removed in section:
                    # Load refuses these (migrations.assert_current); a mapping
                    # built in-process is told the same thing and the value is
                    # NOT honoured — honouring it would be the silent path.
                    logger.error(
                        "channels.slack.%s was removed in issue-309 — use %s; "
                        "the value is ignored (run `the-loop migrate-config`)",
                        removed,
                        replacement,
                    )
            subscribe = _subscribe_list(section.get("subscribe"))
            publish = _publish_list(section.get("publish"))
            # Deprecated and ignored (issue-549 R1.2, R1.3): the long form reaches
            # Slack whole, so neither key limits anything any more. A config that
            # still sets one loads, and is told once per process.
            _warn_deprecated(section)
            kickoff = section.get("kickoff") or {}
            if not isinstance(kickoff, Mapping):
                logger.warning("channels.slack.kickoff is not a mapping — ignored")
                kickoff = {}
            room = section.get("room") or {}
            if not isinstance(room, Mapping):
                logger.warning("channels.slack.room is not a mapping — ignored")
                room = {}
            room_style = str(room.get("style") or "agentic")
            if room_style not in ("agentic", "classic"):
                logger.warning(
                    "channels.slack.room.style %r is not 'agentic' or 'classic' "
                    "— using 'agentic'",
                    room_style,
                )
                room_style = "agentic"
            return cls(
                enabled=bool(section.get("enabled", False)),
                bot_token_env=str(section.get("botTokenEnv") or DEFAULT_BOT_TOKEN_ENV),
                app_token_env=str(section.get("appTokenEnv") or DEFAULT_APP_TOKEN_ENV),
                channel=str(section.get("channel") or ""),
                subscribe=subscribe,
                publish=publish,
                verbosity=verbosity,
                room_style=room_style,
                kickoff_repo=str(kickoff.get("repo") or "").strip(),
                kickoff_labels=tuple(
                    str(lbl).strip()
                    for lbl in (kickoff.get("labels") or [])
                    if str(lbl).strip()
                ),
                principals=principals,
                authorized_users=tuple(ids_for(principals, "slack")),
                read_mode=mode,
                gateway=gateway,
                read_interval_seconds=float(read.get("intervalSeconds") or 30),
                catch_up_seconds=_catch_up_seconds(read.get("catchUpSeconds")),
                split_check_beats=_split_check_beats(read.get("splitCheckBeats")),
                reactions=SlackReactionConfig.from_mapping(section.get("reactions")),
                control_keywords=control_keywords,
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "channels.slack: malformed section (%s) — the channel is "
                "disabled (fail closed)",
                exc,
            )
            return cls()


def _catch_up_seconds(raw: Any) -> int:
    """``channels.slack.read.catchUpSeconds``, fail-closed (issue-362, D5).

    Read explicitly rather than through the ``or`` idiom its neighbour
    ``intervalSeconds`` uses: ``0`` has to survive, because it is how an operator
    keeps the connect-only behaviour. A value below the floor is clamped rather
    than honoured — a reconcile that runs every second is a second poll transport
    spending the instance's rate limit on a push channel (bugfix §AC6).
    """
    if raw is None:
        return DEFAULT_CATCH_UP_SECONDS
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "channels.slack.read.catchUpSeconds %r is not a number — using %d",
            raw,
            DEFAULT_CATCH_UP_SECONDS,
        )
        return DEFAULT_CATCH_UP_SECONDS
    if seconds <= 0:
        return 0
    if seconds < MIN_CATCH_UP_SECONDS:
        logger.warning(
            "channels.slack.read.catchUpSeconds %d is below %d — using %d; the "
            "reconcile is a safety net, not a second poll transport",
            seconds,
            MIN_CATCH_UP_SECONDS,
            MIN_CATCH_UP_SECONDS,
        )
        return MIN_CATCH_UP_SECONDS
    return seconds


def _split_check_beats(raw: Any) -> int:
    """``channels.slack.read.splitCheckBeats``, clamped (issue-413).

    Read explicitly rather than through the ``or`` idiom, for the reason its
    neighbour :func:`_catch_up_seconds` is: ``0`` has to survive, because it is
    how an operator turns the check off. A value above the cap is lowered rather
    than honoured — every beat is a message posted into a room people read, and
    the confidence a bigger number buys is bought more cheaply by waiting for
    the next cycle.
    """
    if raw is None:
        return DEFAULT_SPLIT_CHECK_BEATS
    try:
        beats = int(raw)
    except (TypeError, ValueError):
        logger.warning(
            "channels.slack.read.splitCheckBeats %r is not a number — using %d",
            raw,
            DEFAULT_SPLIT_CHECK_BEATS,
        )
        return DEFAULT_SPLIT_CHECK_BEATS
    if beats < 0:
        logger.warning(
            "channels.slack.read.splitCheckBeats %d is negative — using %d; 0 is "
            "how the check is turned off",
            beats,
            DEFAULT_SPLIT_CHECK_BEATS,
        )
        return DEFAULT_SPLIT_CHECK_BEATS
    if beats > MAX_SPLIT_CHECK_BEATS:
        logger.warning(
            "channels.slack.read.splitCheckBeats %d is above %d — using %d; a "
            "split check is a measurement, not a broadcast",
            beats,
            MAX_SPLIT_CHECK_BEATS,
            MAX_SPLIT_CHECK_BEATS,
        )
        return MAX_SPLIT_CHECK_BEATS
    return beats


def _control_keywords(raw: Any) -> Tuple[Tuple[str, str], ...]:
    """Every control command with its configured keyword (issue-337) — the
    dispatcher's own parse of ``routing.control``, so a button's value is the
    word the ingress will recognise. Imported at call time, as
    ``inbound._control_config`` imports it."""
    from ..control import COMMANDS, ControlConfig

    try:
        # The buttons carry the built-in commands only, so the operator's
        # command bindings (issue-343) — which may name graphs this reader was
        # not handed — are left out of the parse.
        control = ControlConfig.from_mapping(
            {k: v for k, v in raw.items() if k != "commands"}
            if isinstance(raw, Mapping)
            else {}
        )
    except (TypeError, ValueError, AttributeError) as exc:
        # The dispatcher refuses such a config on its own; here the buttons
        # simply carry the shipped keywords rather than taking the channel down.
        logger.warning(
            "routing.control could not be parsed (%s) — the command buttons "
            "carry the default keywords",
            exc,
        )
        control = ControlConfig()
    return tuple((command, control.keyword(command)) for command in COMMANDS)


def _subscribe_list(raw: Any) -> Tuple[str, ...]:
    if raw is None:
        return DEFAULT_EVENTS
    if not isinstance(raw, (list, tuple)):
        logger.warning(
            "channels.slack.subscribe is not a list — using the default %s",
            list(DEFAULT_EVENTS),
        )
        return DEFAULT_EVENTS
    events = tuple(str(e) for e in raw)
    # Warn against the common catalog (PR #267 review): an allow-list typo
    # otherwise fails SILENTLY — the event just never arrives. Unknown names
    # are kept, not refused: a custom process graph may fire a custom notify
    # event, and its subscription must work.
    unknown = [e for e in events if e not in SUBSCRIBABLE_EVENTS]
    if unknown:
        logger.warning(
            "channels.slack.subscribe names %s, not in the subscribable-event "
            "catalog (%s) — kept, but nothing shipped broadcasts them; see "
            "`the-loop channels status` or docs/config/cli/channels-options for "
            "the vocabulary",
            ", ".join(repr(e) for e in unknown),
            ", ".join(SUBSCRIBABLE_EVENTS),
        )
    return events


def _publish_list(raw: Any) -> Tuple[str, ...]:
    """The grants. Unlike subscribe, an unknown name is IGNORED: a typo must never
    widen what a chat message may do (R2.4)."""
    if raw is None:
        return DEFAULT_PUBLISH
    if not isinstance(raw, (list, tuple)):
        logger.warning(
            "channels.slack.publish is not a list — using the default %s",
            list(DEFAULT_PUBLISH),
        )
        return DEFAULT_PUBLISH
    granted: List[str] = []
    for entry in raw:
        name = str(entry)
        if name not in PUBLISHABLE_EVENTS:
            logger.warning(
                "channels.slack.publish names %r, which is not a publishable "
                "event (%s) — ignored",
                name,
                ", ".join(PUBLISHABLE_EVENTS),
            )
            continue
        if name not in granted:
            granted.append(name)
    return tuple(granted)


# -- rendering (R4) --------------------------------------------------------------

_TITLES: Dict[str, str] = strings.section("slack.title")


def _label(value: str, limit: int = 300) -> str:
    """A verbose detail value drawn as a label: one line's worth, never a body."""
    value = value.strip()
    return value if len(value) <= limit else value[:limit].rstrip() + "…"


def _message_actions(
    event: Event,
    *,
    interactive: bool = False,
    commands: Optional[Mapping[str, str]] = None,
    open_on_github: bool = True,
) -> List[Dict[str, Any]]:
    """The buttons ``event``'s message earns, in order: *Open on GitHub* (its own
    URL, never one from its text — abuse case 5), the command buttons, the
    default-answer button and the Approve / Request changes pair (the last two
    only where a press can be received)."""
    actions: List[Dict[str, Any]] = []
    if event.url and open_on_github:
        actions.append(
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.button.open-on-github"),
                },
                "url": event.url,
                "action_id": f"{ACTION_PREFIX}open",
            }
        )
    actions.extend(_command_buttons(commands))
    # issue-393 B9/R12.1: a session's question with a stated default gets a
    # one-tap affirmative — the button's value is the default answer, delivered
    # as that member's reply exactly as a typed one would be. Only when the
    # channel can receive a press (Socket Mode + the gate.feedback grant, the
    # same interactivity the Approve pair needs).
    default_answer = str((event.detail or {}).get("default") or "").strip()
    if interactive and default_answer:
        actions.append(
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.button.defaults"),
                },
                "style": "primary",
                "action_id": f"{ACTION_PREFIX}default",
                "value": default_answer[:_BUTTON_VALUE_LIMIT],
            }
        )
    if interactive and event.event_type in APPROVAL_EVENTS:
        actions.append(
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": strings.t("slack.button.approve"),
                },
                "style": "primary",
                "action_id": f"{ACTION_PREFIX}approve",
                "value": APPROVE_VALUE,
            }
        )
        actions.append(
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": strings.t("slack.button.changes"),
                },
                "style": "danger",
                "action_id": f"{ACTION_PREFIX}changes",
                "value": CHANGES_VALUE,
            }
        )
    return actions


def render_short_blocks(
    event: Event,
    short_text: str,
    *,
    verbosity: str = "normal",
    interactive: bool = False,
    commands: Optional[Mapping[str, str]] = None,
    execute_keyword: str = "",
    open_on_github: bool = True,
) -> List[Dict[str, Any]]:
    """The short message as Block Kit (issue-549 R3, R4.4): the short form as one
    mrkdwn section, the phase-selection control (or, where it cannot be pressed,
    the line saying where the checklist is), the verbose detail lines, and the
    buttons. Gate, command and selection controls are always here, on the short
    message, so a decision is taken from it. Nothing is condensed or cut: the
    short form is already within its cap, and the long form goes elsewhere."""
    text = short_text.strip() or _TITLES.get(event.event_type, event.event_type)
    blocks: List[Dict[str, Any]] = [_mrkdwn_section(text)]
    selection = selection_rows(event.text) if is_phase_selection(event) else None
    control_keyword = str((commands or {}).get("execute") or "")
    if selection is not None and control_keyword:
        blocks.extend(selection_control_blocks(selection, control_keyword))
    elif selection is not None:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    _mrkdwn(github_checklist_line(event.url, execute_keyword))
                ],
            }
        )
    if verbosity == "verbose" and event.detail:
        lines = [
            f"*{key}:* {_label(str(value))}"
            for key, value in event.detail.items()
            if key not in ("excerpt",) and str(value).strip()
        ]
        if lines:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "\n".join(lines)[:_SECTION_LIMIT]}
                    ],
                }
            )
    gate = event.event_type in APPROVAL_EVENTS
    if gate and not interactive:
        # No press can reach this instance (R11.5): no buttons, and one line
        # saying how to answer on GitHub, linked by the event's own URL.
        blocks.append(
            {
                "type": "context",
                "elements": [
                    _mrkdwn(
                        approve_on_github_line(
                            event.url or _work_item_url(event.work_item)
                        )
                    )
                ],
            }
        )
    actions = _message_actions(
        event,
        interactive=interactive,
        commands=commands,
        open_on_github=open_on_github,
    )
    if actions:
        block: Dict[str, Any] = {"type": "actions", "elements": actions}
        node = str((event.detail or {}).get("node") or "")
        if gate and interactive and node:
            # The gate the buttons answer (issue-549 abuse case 8): a press
            # names it, and counts only while that gate is open.
            block["block_id"] = f"{GATE_BLOCK_PREFIX}{node}"[:_BLOCK_ID_LIMIT]
        blocks.append(block)
    return blocks


def approve_on_github_line(url: str) -> str:
    """What a gate message says where no press can be received (issue-549
    R11.5): how to answer the gate on GitHub, linked when there is a link."""
    on_github = strings.t("channels.slack.checklist.on-github")
    where = f"<{url}|{on_github}>" if url else on_github
    return strings.t("channels.slack.gate.approve-on-github", where=where)


#: The mark a gate's outcome line opens with, by outcome.
_GATE_ICONS = {
    "approved": "✅",
    "approved-with-comments": "✅",
    "changes-requested": "↩️",
}


def gate_answered_line(node: str, outcome: str, by: str) -> str:
    """The line an answered gate's message gains (issue-549 R11.6): the gate,
    its outcome in words, and who answered (GitHub logins, from the event)."""
    words = strings.section("channels.slack.gate.outcome").get(outcome) or outcome
    who = ", ".join(f"@{login.strip()}" for login in by.split(",") if login.strip())
    return strings.t(
        "channels.slack.gate.answered",
        icon=_GATE_ICONS.get(outcome, "☑️"),
        node=node,
        outcome=words,
        by=strings.t("channels.slack.gate.answered-by", who=who) if who else "",
    )


#: The watcher's follow-up events (issue-551), and the event whose message each
#: one is about: a channel subscribed to the opener hears the follow-up.
_FOLLOW_UPS: Dict[str, str] = {
    sessionnotes.STALL_ENDED: sessionnotes.STALLED,
    sessionnotes.ASK_DEFAULT_TAKEN: "session.awaiting_input",
    sessionnotes.ASK_REMINDED: "session.awaiting_input",
}


def _note_key(event: Event) -> str:
    """Where the message of ``event`` is remembered so it can be edited later
    (issue-551): a stall notice by its stall, a question by its ask. ``""``
    for any other event."""
    detail = event.detail or {}
    if event.event_type == sessionnotes.STALLED and detail.get("stall_id"):
        return sessionnotes.stall_key(str(detail["stall_id"]))
    if event.event_type == "session.awaiting_input" and detail.get("ask_id"):
        return sessionnotes.ask_key(str(detail["ask_id"]))
    return ""


def gate_node_of(action: Mapping[str, Any]) -> str:
    """The gate node a pressed Approve / Request changes button names through
    its block (issue-549 abuse case 8), or ``""`` for a message posted before
    the buttons named one."""
    block_id = str(action.get("block_id") or "")
    if block_id.startswith(GATE_BLOCK_PREFIX):
        return block_id[len(GATE_BLOCK_PREFIX) :]
    return ""


def _mrkdwn_section(text: str) -> Dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def _section_text(blocks: List[Dict[str, Any]]) -> str:
    """The first section's text — the message body as drawn — or ``""``."""
    for block in blocks:
        if block.get("type") == "section":
            return str((block.get("text") or {}).get("text") or "")
    return ""


def _command_buttons(commands: Optional[Mapping[str, str]]) -> List[Dict[str, Any]]:
    """One primary button per command: the label from :data:`COMMAND_BUTTONS`,
    the value the configured keyword, the ``action_id`` under the prefix the
    action handler reads (issue-337 R1.5)."""
    return [
        {
            "type": "button",
            "text": {
                "type": "plain_text",
                "text": COMMAND_BUTTONS.get(command, command.title()),
            },
            "style": "primary",
            "action_id": f"{ACTION_PREFIX}command:{command}",
            "value": keyword,
        }
        for command, keyword in (commands or {}).items()
        if keyword
    ]


def expected_commands(event: Event) -> Tuple[str, ...]:
    """The control commands ``event``'s message asks the reader to type back —
    the ones a button may stand in for (issue-337 R1.1, decision-117 D4).

    One shape today: the phase-selection checklist, which reaches a channel as
    the ``comment.agent`` mirror of the-loop's own comment and carries the hook's
    marker, asks for ``execute``. Read from the marker rather than the prose, and
    only on the agent's own comments: a human's comment never earns a button.
    """
    if event.event_type == "comment.agent" and PHASE_SELECTION_MARKER in event.text:
        return ("execute",)
    return ()


def render_reply_blocks(
    text: str, commands: Optional[Mapping[str, str]] = None
) -> List[Dict[str, Any]]:
    """A plain reply as Block Kit — one section — plus one actions block of
    command buttons when ``commands`` names any (the kickoff's "opened, this
    thread is the conversation" reply and its Do / Start buttons, issue-337
    R1.2, issue-529). A rendered command with a description gets one line
    between the two, in button order, so the choice is read before it is made."""
    blocks: List[Dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}}
    ]
    buttons = _command_buttons(commands)
    if buttons:
        lines = [
            f"*{COMMAND_BUTTONS[command]}* — {COMMAND_DESCRIPTIONS[command]}"
            for command, keyword in (commands or {}).items()
            if keyword and command in COMMAND_DESCRIPTIONS
        ]
        if lines:
            blocks.append(
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "\n".join(lines)},
                }
            )
        blocks.append({"type": "actions", "elements": buttons})
    return blocks


#: The decision modal's callback id — the shortcut's, so one id names the act
#: from the ⋯ menu to the submission (issue-389 R6.3).
DECISION_VIEW_CALLBACK = "the-loop:record-decision"
#: Slack's ceiling on a plain-text input's initial value.
_INPUT_LIMIT = 3000


def decision_view(text: str, private_metadata: str) -> Dict[str, Any]:
    """The *Record a decision* modal (issue-389 R6.3): the decision pre-filled
    from the message, a kind select over :data:`~.verbs.KINDS`, an optional
    rationale. ``private_metadata`` is the JSON the submission hands back —
    the channel, the message ts and its thread — composed by the-loop, never
    from the member's text, and validated again on the way back (A3)."""
    from .verbs import KINDS

    return {
        "type": "modal",
        "callback_id": DECISION_VIEW_CALLBACK,
        "private_metadata": private_metadata,
        "title": {
            "type": "plain_text",
            "text": strings.t("channels.slack.decision-view.title"),
        },
        "submit": {
            "type": "plain_text",
            "text": strings.t("channels.slack.decision-view.submit"),
        },
        "close": {
            "type": "plain_text",
            "text": strings.t("channels.slack.decision-view.close"),
        },
        "blocks": [
            {
                "type": "input",
                "block_id": "decision",
                "label": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.decision-view.decision-label"),
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "text",
                    "multiline": True,
                    "initial_value": " ".join((text or "").split())[:_INPUT_LIMIT],
                },
            },
            {
                "type": "input",
                "block_id": "kind",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.decision-view.kind-label"),
                },
                "element": {
                    "type": "static_select",
                    "action_id": "select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": strings.t(
                            "channels.slack.decision-view.kind-placeholder"
                        ),
                    },
                    "options": [
                        {"text": {"type": "plain_text", "text": kind}, "value": kind}
                        for kind in KINDS
                    ],
                },
            },
            {
                "type": "input",
                "block_id": "rationale",
                "optional": True,
                "label": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.decision-view.rationale-label"),
                },
                "element": {
                    "type": "plain_text_input",
                    "action_id": "text",
                    "multiline": True,
                },
            },
        ],
    }


def render_kickoff_question(text: str, options: Sequence[str]) -> List[Dict[str, Any]]:
    """The "which repository?" question as Block Kit (issue-349, R2.1–R2.4).

    ``text`` is :func:`~.kickoff.question_text`'s fixed words; ``options`` are the
    operator's **declared** slugs. Both the visible label and the value of every
    option are that same declared string, so what a press hands back is a selector
    into the operator's own config — nothing of the member's message is rendered
    here at all, which is what stops a hostile message styling the question or
    pinging through it (A8).

    Shape follows size: at most :data:`BUTTON_CHOICE_LIMIT` repositories are
    buttons (one tap); more become a ``static_select`` (Slack's own widget for a
    list). Past :data:`OPTION_LIMIT` — Slack's ceiling for a static select — the
    first hundred are offered in declaration order and the caller's prose names
    the ``<repo>: `` prefix for the rest.
    """
    shown = [str(option) for option in options][:OPTION_LIMIT]
    body = text
    extra = len(options) - len(shown)
    if extra > 0:
        body = f"{text}\n" + strings.t(
            "channels.slack.kickoff.showing", shown=len(shown), total=len(options)
        )
    blocks: List[Dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": body}}
    ]
    if not shown:
        return blocks
    if len(shown) <= BUTTON_CHOICE_LIMIT:
        elements: List[Dict[str, Any]] = [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": option[:_OPTION_TEXT_LIMIT],
                },
                "action_id": f"{KICKOFF_REPO_ACTION}:{index}",
                "value": option,
            }
            for index, option in enumerate(shown)
        ]
    else:
        elements = [
            {
                "type": "static_select",
                "placeholder": {
                    "type": "plain_text",
                    "text": strings.t("channels.slack.kickoff.choose-repository"),
                },
                "action_id": KICKOFF_REPO_ACTION,
                "options": [
                    {
                        "text": {
                            "type": "plain_text",
                            "text": option[:_OPTION_TEXT_LIMIT],
                        },
                        "value": option,
                    }
                    for option in shown
                ],
            }
        ]
    blocks.append({"type": "actions", "elements": elements})
    return blocks


def is_kickoff_repo_action(action_id: str) -> bool:
    """Whether ``action_id`` is the repository picker's.

    Slack requires a unique ``action_id`` per element in one message, so the
    button shape numbers itself (``…:0``, ``…:1``) while the select menu — one
    element — carries the bare id. Both are the same question, and one predicate
    is what keeps them one branch in the handler.
    """
    return action_id == KICKOFF_REPO_ACTION or action_id.startswith(
        f"{KICKOFF_REPO_ACTION}:"
    )


def _button_name(action_id: str) -> str:
    """The name the press outcome line uses for ``action_id`` (R2.6) — the
    picker's numbered buttons all answer to its one entry."""
    if is_kickoff_repo_action(action_id):
        return BUTTON_NAMES[KICKOFF_REPO_ACTION]
    return BUTTON_NAMES.get(action_id, strings.t("channels.slack.press.the-button"))


def action_value(action: Mapping[str, Any]) -> str:
    """What a member chose in ``action`` — ``""`` when they chose nothing.

    A button carries its answer as a top-level ``value``; a ``static_select``
    carries it as ``selected_option.value`` and has no top-level ``value`` at all
    (issue-349 R4.2). One helper, so the handler's filter and its read agree and a
    third widget shape is one line here rather than two branches there.
    """
    selected = action.get("selected_option")
    if isinstance(selected, Mapping):
        return str(selected.get("value") or "").strip()
    return str(action.get("value") or "").strip()


def _work_item_url(ref: str) -> str:
    """The browser link for ``ref`` — derived through :class:`WorkItemRef`, so the
    host it carries is honoured (issue-311); ``""`` for a ref that is not a work
    item (a standing session's) or will not parse."""
    from ..sessions import WorkItemRef

    try:
        return WorkItemRef.parse(ref).url
    except ValueError:
        return ""


def render_root(
    work_item: str, url: str = "", *, reading: bool = True
) -> Tuple[str, List[Dict[str, Any]]]:
    """The thread root for ``work_item`` — ``(text, blocks)`` built from the bound
    ref and nothing else (issue-312 A2): a header naming it, a section saying what
    the thread is for, and the link button when a URL can be derived.

    ``reading`` says whether the channel reads replies (``read.mode != "off"``),
    so the root promises only what the configuration delivers.
    """
    name = f"<{url}|{work_item}>" if url else f"`{work_item}`"
    lines = [strings.t("channels.slack.root.body", name=name)]
    if reading:
        lines.append(strings.t("channels.slack.root.reading"))
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": strings.t("channels.slack.root.header", work_item=work_item)[
                    :_HEADER_LIMIT
                ],
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": " ".join(lines)}},
    ]
    if url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": strings.t("channels.slack.button.open-on-github"),
                        },
                        "url": url,
                        "action_id": f"{ACTION_PREFIX}open",
                    }
                ],
            }
        )
    link = f" — {url}" if url else ""
    return (
        strings.t("channels.slack.root.fallback", work_item=work_item, link=link),
        blocks,
    )


def render_room(
    work_item: str, url: str = "", *, reading: bool = True
) -> Tuple[str, List[Dict[str, Any]]]:
    """The message that opens a **room** conversation (issue-378 R5.1) —
    ``(text, blocks)`` from the ref alone, like :func:`render_root`: the room is
    the work item's own, so it says every update lands here as a message."""
    name = f"<{url}|{work_item}>" if url else f"`{work_item}`"
    lines = [strings.t("channels.slack.room.body", name=name)]
    if reading:
        lines.append(strings.t("channels.slack.room.reading"))
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": strings.t("channels.slack.root.header", work_item=work_item)[
                    :_HEADER_LIMIT
                ],
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": " ".join(lines)}},
    ]
    if url:
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": strings.t("channels.slack.button.open-on-github"),
                        },
                        "url": url,
                        "action_id": f"{ACTION_PREFIX}open",
                    }
                ],
            }
        )
    link = f" — {url}" if url else ""
    return (
        strings.t("channels.slack.room.fallback", work_item=work_item, link=link),
        blocks,
    )


class SlackBotChannel:
    """The bot: one Slack channel, one thread per work item, replies read back."""

    name = "slack"

    def __init__(
        self,
        config: SlackChannelConfig,
        state_path: Path,
        client_factory: Optional[Callable[[str], Any]] = None,
        cli_config: Optional[Mapping[str, Any]] = None,
    ):
        self.config = config
        self.state_path = Path(state_path)
        # Where this channel's bindings and cursors actually live (issue-368):
        # the binding in each work item's portable record, the cursor in its
        # session record on this machine. Derived from the state path, so every
        # construction site of a channel keeps its one argument.
        self.stores = ChannelStores.beside(self.state_path, self.name)
        self._client_factory = client_factory
        self._own_user: Optional[str] = None
        #: The resolved central channel (PR #376 review), memoised per instance.
        self._central: Optional[str] = None
        #: The CLI config this channel was built from, when a caller handed it
        #: over (issue-416): the state layout the attachment directory derives
        #: from, and (issue-519) the `gateway` block the posting path reads.
        #: Absent, the layout's default root applies and no gateway is known.
        self._cli_config: Optional[Mapping[str, Any]] = cli_config

    def subscribes(self, event_type: str) -> bool:
        if event_type == GATE_ANSWERED:
            # A channel that posts a gate's message hears its answer, so the
            # message can be closed (issue-549 R11.6) without a second key.
            return event_type in self.config.subscribe or any(
                name in self.config.subscribe for name in APPROVAL_EVENTS
            )
        # The same rule for the watcher's follow-ups (issue-551): a channel that
        # posts the stall notice hears its end, and one that posts the question
        # hears its reminder and its default being taken.
        opener = _FOLLOW_UPS.get(event_type)
        if opener and opener in self.config.subscribe:
            return True
        return event_type in self.config.subscribe

    def wants(self, event_type: str) -> bool:
        """The pre-issue-309 spelling of :meth:`subscribes`."""
        return self.subscribes(event_type)

    def may_publish(self, event_type: str) -> bool:
        return event_type in self.config.publish

    def _client(self):
        # Resolved at call time so a test's monkeypatch of ``build_client`` (and an
        # env var set after construction) is always seen. The posting path (issue-519):
        # the local token first, else the gateway's client, else today's error.
        return outbound_client(self.config, self._cli_config, self._client_factory)

    def fetch_attachments(
        self, files: Sequence[Mapping[str, Any]], work_item: str
    ) -> List[attachments.Attachment]:
        """The message's files, fetched with the bot token into this work item's
        attachment directory (issue-416) — an audio clip with Slack's own
        transcript, re-read through ``files.info`` while Slack is still producing
        it. Never raises: with no token every file comes back named and linked
        with the reason, and a client without ``files.info`` (a test double, an
        older SDK) simply gets no transcript wait.
        """
        if not files:
            return []
        from ..sessions import WorkItemRef
        from ..state import layout_from_config

        from .slack_gateway import GatewaySlackClient

        token = os.environ.get(self.config.bot_token_env) or ""
        try:
            slug = WorkItemRef.parse(work_item).slug
        except ValueError:
            slug = attachments.safe_name(work_item)
        layout = layout_from_config(dict(self._cli_config or {}))
        dest = Path(layout.attachments_dir) / slug
        files_info: Optional[Callable[[str], Mapping[str, Any]]] = None
        fetch: Optional[Callable[..., Tuple[str, bytes]]] = None
        try:
            client = self._client()
        except ChannelError:
            client = None
        method = getattr(client, "files_info", None)
        if callable(method):
            read = method

            def _info(file_id: str) -> Mapping[str, Any]:
                result = read(file=file_id)
                return result if isinstance(result, Mapping) else {}

            files_info = _info
        if isinstance(client, GatewaySlackClient):
            # behind a gateway with no token of its own (issue-519, R3.3): the gateway
            # downloads the file, under the same hosts and cap
            fetch = client.fetch

        return attachments.slack_attachments(
            files, token=token, dest_dir=dest, files_info=files_info, fetch=fetch
        )

    # -- outbound (R3) ---------------------------------------------------------

    def central_channel(self) -> str:
        """``channels.slack.channel`` as a conversation id (PR #376 review).

        The operator may declare the room by **name** — ``#the-loop`` — which is
        what they call it; Slack's API wants ``C0123ABCD``. Resolved once per
        instance over the shared directory cache, so the eighteen places that
        used to read ``config.channel`` read one id and cannot disagree about
        which room they mean. ``""`` when nothing is configured, or when a
        configured name resolves to nothing — both of which the callers already
        refuse on.

        Memoised per instance, including the empty answer: a name that does not
        resolve must not cost a directory refresh on every message.
        """
        if self._central is not None:
            return self._central
        declared = self.config.channel
        if not declared:
            self._central = ""
            return ""
        if is_conversation_id(declared):
            self._central = declared
            return declared
        resolved = self.directory().conversation_id(declared)
        if not resolved:
            logger.warning(
                "slack: channels.slack.channel is %r, which resolves to no channel "
                "this bot can see — check the spelling, invite the bot, and make "
                "sure the app carries channels:read / groups:read",
                declared,
            )
        self._central = resolved
        return resolved

    def directory(self):
        """The name→id directory beside this channel's own state file."""
        from .directory import SlackDirectory

        return SlackDirectory.beside(
            self.state_path,
            token_env=self.config.bot_token_env,
            client_factory=self._client_factory,
        )

    def home_for(self, work_item: str) -> str:
        """The channel this work item's conversation belongs in (issue-375).

        Its **declared** collaboration channel when it has one, the operator's
        ``channels.slack.channel`` otherwise. One resolver, used by every outbound
        path, so a thread root, a reply and an acknowledgment can never end up in
        different rooms.
        """
        if self.stores is not None and work_item:
            declared = self.stores.declared(work_item)
            if declared:
                return declared
        return self.central_channel()

    def _no_channel(self, work_item: str) -> ChannelError:
        """No room to post in — nothing configured, nothing declared, or a name
        that resolves to nothing this bot can see."""
        declared = self.config.channel
        why = (
            f" (channels.slack.channel is {declared!r}, which resolves to no "
            "channel this bot can see — check the spelling, invite the bot, and "
            "make sure the app carries channels:read / groups:read)"
            if declared
            else ""
        )
        return ChannelError(
            "slack: no channel to post "
            + (f"{work_item} in" if work_item else "in")
            + " — set channels.slack.channel to the channel the bot posts into "
            "(its name or its C… id), or declare one on the work item with "
            "`the-loop add-channel slack@#room`" + why
        )

    def _conversation(
        self, client, state: ChannelState, work_item: str, *, origin: str = "event"
    ) -> Tuple[str, str]:
        """``(channel_id, thread_ts)`` for ``work_item`` — opening or MOVING it.

        Three cases, and the third is the whole of R2.2: no binding opens the
        conversation in the work item's home; a binding already in that home is
        returned untouched, whatever its shape; a binding in another channel
        means the work item was declared into a new room after its conversation
        had started, so the conversation is opened **there** and the binding
        follows it.

        What "open in the home" means depends on the home (issue-378 R5): a
        **declared room** is the work item's own, so the conversation is the
        room itself (``thread_ts == ""``, every update a top-level message); the
        operator's central channel is shared by every work item, so a thread is
        opened there, as always.

        A work item has exactly one conversation (issue-312), so the move is a
        move: replies in the old thread are `unmapped` from then on. That is why
        :meth:`_say_moved` is not a courtesy — it is the only thing standing
        between somebody still typing there and silence.

        Called inside the caller's state lock.
        """
        home = self.home_for(work_item)
        if not home:
            raise self._no_channel(work_item)
        bound = state.conversation_for(work_item)
        if bound and bound[0] and bound[0] != home:
            moved = self._open_home(client, state, work_item, home, origin="declared")
            self._say_moved(bound, moved, work_item)
            return moved
        if bound:
            return bound
        return self._open_home(client, state, work_item, home, origin=origin)

    def _open_home(
        self, client, state: ChannelState, work_item: str, home: str, *, origin: str
    ) -> Tuple[str, str]:
        """Open ``work_item``'s conversation in ``home``: as the room itself when
        the home is a room the work item declared, as a thread otherwise."""
        declared = self.stores.declared(work_item) if self.stores is not None else ""
        if declared and declared == home:
            return self._open_room(client, state, work_item, home, origin=origin)
        return self._open_thread(
            client, state, work_item, channel_id=home, origin=origin
        )

    def _say_moved(
        self, old: Tuple[str, str], new: Tuple[str, str], work_item: str
    ) -> None:
        """Leave a pointer in the thread the conversation just left (R2.2).

        Best-effort, and the one thing that makes the move readable: a work item
        has one conversation, so replies in this thread reach nobody from now on.
        Saying where it went is cheaper than the silence it replaces.
        """
        self.say(
            old[1],
            strings.t("channels.slack.moved", work_item=work_item, channel=new[0]),
            old[0],
        )

    def _room_decision(self, event: Event, is_room: bool) -> "room_policy.Decision":
        """RoomPolicy's decision for ``event`` (issue-393 B5) — for every
        conversation since issue-549, the central channel included. ``is_room``
        (an agentic room) scopes the two rules that make a room conversational.
        Reads the delivery memory under the lock, so it is a snapshot the post
        then acts on. An event with no work item has no memory and simply posts.
        """
        if not event.work_item:
            return room_policy.Decision(room_policy.POST, rule="no-work-item")
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                memory = state.delivery_for(event.work_item)
        except Exception as exc:  # noqa: BLE001 — a memory read never fails a post
            logger.debug("slack: delivery memory read failed (%s); posting", exc)
            return room_policy.Decision(room_policy.POST, rule="no-memory")
        return room_policy.decide(
            event,
            memory,
            is_room=is_room,
            session_authored=(event.source in ("cli", "session")),
            is_operator_doc=bool((event.detail or {}).get("operatorDoc")),
        )

    def _remember_delivery(
        self, event: Event, decision: "room_policy.Decision", ts: str
    ) -> None:
        """Merge what the conversation now holds into the delivery memory. ``@ts``
        in a decision's ``remember`` is the placeholder for the message just
        posted — resolved to ``ts`` here — and the last event/node are always
        recorded so the dedupe rule can fire next time (issue-393 B5)."""
        node = str(
            (event.detail or {}).get("node") or (event.detail or {}).get("phase") or ""
        )
        changes: Dict[str, Any] = {
            "lastEvent": event.event_type,
            "lastNode": node,
        }
        # issue-393 B9/R12.3: when the SESSION speaks for a node (its question or
        # summary), remember that, so a later runtime template for the same node
        # is suppressed by RoomPolicy's session-wins rule — the agent's own words
        # win over the boilerplate.
        if node and event.source in ("cli", "session"):
            changes["sessionSpokeFor"] = node
        for key, value in (decision.remember or {}).items():
            if isinstance(value, dict):
                changes[key] = {k: (ts if v == "@ts" else v) for k, v in value.items()}
            else:
                changes[key] = ts if value == "@ts" else value
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(event.work_item, **changes)
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug(
                "slack: could not record delivery for %s (%s)", event.work_item, exc
            )

    # -- the posting path (issue-549): policy → placement → builders → plan → delivery

    #: The clock the recap and the mentions read (issue-549 R9) — a test
    #: substitutes it.
    _now: Callable[[], float] = staticmethod(time.time)  # type: ignore[assignment]

    def _preamble(self, event: Event) -> Preamble:
        """What opens ``event``'s short form, inside its cap (issue-549 R7, R9):
        the recap line when a person has been away and the loop moved, then the
        mentions when ``event`` announces a wait not announced before. Built
        from configuration and the delivery memory, never from the event's
        text. A memory that cannot be read opens nothing."""
        if not event.work_item:
            return Preamble()
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                memory = state.delivery_for(event.work_item)
        except Exception as exc:  # noqa: BLE001 — a preamble never fails a post
            logger.debug("slack: delivery memory read failed (%s)", exc)
            return Preamble()
        wait = wait_key(event)
        mentions = ""
        if wait and wait not in memory["announced"]:
            mentions = mention_line(self._mention_ids())
            if not mentions and self.config.authorized_users:
                # nobody resolved (a directory lookup that failed): the wait is
                # not recorded as announced, so the next message of it mentions
                # them again, rather than nobody for good
                wait = ""
        recap = recap_line(
            memory["changes"],
            last_human=memory["lastHuman"],
            recapped_at=memory["recapAt"],
            now=self._now(),
        )
        text = "\n".join(line for line in (recap, mentions) if line)
        return Preamble(text=text, wait=wait, recapped=bool(recap))

    def _mention_ids(self) -> List[str]:
        """The member ids of the authorized users (``routing.authorizedUsers[]
        .slack``), in configured order: an id as written, a handle through the
        Slack directory. One that does not resolve is left out, never guessed
        (abuse case 6)."""
        from .directory import is_member_id

        ids: List[str] = []
        directory = None
        for entry in self.config.authorized_users:
            if is_member_id(entry):
                ids.append(entry)
                continue
            try:
                directory = directory or self.directory()
                resolved = directory.user_id(entry)
            except Exception as exc:  # noqa: BLE001 — unresolved: no mention
                logger.debug(
                    "slack: could not resolve %s for a mention (%s)", entry, exc
                )
                continue
            if resolved:
                ids.append(resolved)
        return ids

    def _remember_event(self, event: Event, preamble: Preamble) -> None:
        """Record what ``event`` means for the next preamble (issue-549): its
        change for the recap (dropped events too, R10.2), the wait it
        announced, the recap it carried — and, once the work item is no longer
        waiting, forget the announced waits, so a gate that reopens is a new
        wait (R7.3). Best effort."""
        if not event.work_item:
            return
        now = str(self._now())
        changes: Dict[str, Any] = {}
        change = change_of(event)
        if change is not None:
            changes["changes"] = [{"at": now, "kind": change[0], "value": change[1]}]
        state_name = status_reactor.state_for(event)
        if preamble.wait:
            changes["announced"] = {preamble.wait: now}
        elif state_name and state_name != status_reactor.WAITING:
            changes["announced"] = None
        if preamble.recapped:
            changes["recapAt"] = now
        if not changes:
            return
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(event.work_item, **changes)
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug("slack: could not record %s (%s)", event.work_item, exc)

    def note_human(self, work_item: str) -> None:
        """An authorized human spoke in ``work_item``'s conversation now — the
        recap's reference point (issue-549 R9.1). Best effort."""
        if not work_item:
            return
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(work_item, lastHuman=str(self._now()))
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug("slack: could not note a human in %s (%s)", work_item, exc)

    def _plan(
        self,
        event: Event,
        kind: str,
        decision: "room_policy.Decision",
        *,
        channel_id: str,
        thread: str,
        preamble: str = "",
    ) -> MessagePlan:
        """``event`` as a :class:`MessagePlan` for a conversation of ``kind``.

        ``thread`` is where the short message goes when it is a reply: the
        central channel's item thread, the room mention's thread, or the gate
        message an acknowledgement threads under (``""`` = top-level).
        """
        short = build_short_form(event, preamble=preamble)
        where = placement.place(kind, event, long_adds=long_form_adds(event, short))
        blocks = render_short_blocks(
            event,
            short.text,
            verbosity=self.config.verbosity,
            interactive=self.config.interactive,
            commands=self.config.command_buttons_for(*expected_commands(event)),
            execute_keyword=self.config.keyword("execute"),
            open_on_github=where.open_on_github,
        )
        editing = decision.action == room_policy.EDIT and bool(decision.ts)
        long_form = render_long_form(event.text) if where.long else LongForm()
        if where.long == placement.SHORT_THREAD:
            # a room: the long form goes in the short message's own thread — or,
            # when the short message is itself a reply, in that same thread
            parts_thread = thread or THREAD_OF_TOP
        else:
            parts_thread = thread if where.long else ""
        return plan_message(
            event_id=event.event_id,
            channel=channel_id,
            short_text=short.fallback,
            short_blocks=blocks,
            top_thread=thread,
            parts=long_form.parts,
            parts_thread=parts_thread,
            edit_ts=decision.ts if editing else "",
            edit_parts=(
                self._parts_under(event, channel_id, decision.ts) if editing else ()
            ),
            short_source=short.source,
            tables_as_code=long_form.tables_as_code,
            parts_text=_without_preamble(short.fallback, preamble),
        )

    def _parts_under(self, event: Event, channel_id: str, ts: str) -> Tuple[str, ...]:
        """The long-form replies the message at ``ts`` holds today, from the
        delivery memory: the newest event delivered to that message — its first
        post or its last edit — other than ``event`` itself (issue-549 R6.2). A
        lost memory yields none, so the edit posts its long form afresh."""
        if not event.work_item:
            return ()
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                posted = state.delivery_for(event.work_item)["posted"]
        except Exception as exc:  # noqa: BLE001 — a memory read never fails a post
            logger.debug("slack: posted memory read failed (%s)", exc)
            return ()
        for event_id, record in reversed(list(posted.items())):
            if event_id == event.event_id:
                continue
            if record.get("channel") == channel_id and record.get("top") == ts:
                return tuple(record.get("parts") or ())
        return ()

    def _deliver(self, client, event: Event, plan: MessagePlan) -> Delivered:
        """Run the delivery step with this work item's delivery memory: what an
        earlier attempt at this event id posted is skipped, and every new ts is
        recorded before the next call (non-functional: idempotent retries)."""
        if not (event.work_item and event.event_id):
            return deliver(client, plan, sleep=self._sleep)
        already: Dict[str, Any] = {}
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                already = state.posted_for(event.work_item, event.event_id)
        except Exception as exc:  # noqa: BLE001 — a lost memory re-posts, never fails
            logger.debug("slack: posted memory read failed (%s)", exc)

        def record(delivered: Delivered) -> None:
            try:
                with ChannelState.locked(self.state_path, self.stores) as state:
                    state.remember_posted(
                        event.work_item, event.event_id, summary_of(delivered)
                    )
                    state.save(self.state_path)
            except Exception as exc:  # noqa: BLE001 — memory is best-effort
                logger.debug("slack: could not record posted parts (%s)", exc)

        return deliver(client, plan, already=already, record=record, sleep=self._sleep)

    #: How the delivery step waits out a 429 — a test substitutes it.
    _sleep: Callable[[float], None] = staticmethod(time.sleep)  # type: ignore[assignment]

    def _after_delivery(
        self,
        event: Event,
        kind: str,
        plan: MessagePlan,
        delivered: Delivered,
        client: Any = None,
    ) -> None:
        """The hook after a successful delivery, best effort: the status reactor
        (issue-549 R8). In a room the status message moves to the short message
        just posted top-level; in the central channel it is the thread root."""
        target = ("", "")
        if kind == placement.ROOM and not plan.top.thread_ts and not delivered.edited:
            target = (plan.channel, delivered.top)
        self._react_status(event, kind, target, client)

    def _react_status(
        self, event: Event, kind: str, target: Tuple[str, str], client: Any = None
    ) -> None:
        """Keep the work item's one status reaction current (issue-549 R8).

        ``target`` is the new status message, or ``("", "")`` to keep the one
        the memory names; in the central channel it is always the thread root.
        Runs on dropped events too, so bookkeeping still moves the state
        (R10.3). Never raises and never delays a delivery: a reaction that
        fails is logged and the status left as it was (R8.4).
        """
        if not event.work_item:
            return
        state_name = status_reactor.state_for(event)
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                current = dict(state.delivery_for(event.work_item)["status"])
                bound = state.conversation_for(event.work_item)
            if kind == placement.CENTRAL and bound and bound[1]:
                target = (bound[0], bound[1])
            plan = status_reactor.plan_status(current, state_name, target)
            if plan is None:
                return
            client = client or self._client()
            if plan.add is not None and not self._status_call(
                client, "add", *plan.add, event=event
            ):
                return  # the old reaction stays: still exactly one (R8.1)
            if plan.remove is not None:
                self._status_call(client, "remove", *plan.remove, event=event)
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(event.work_item, status=dict(plan.status))
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — a reaction never fails delivery
            logger.warning(
                "slack: status reaction for %s failed (%s)", event.work_item, exc
            )

    def _status_call(
        self, client, verb: str, channel_id: str, ts: str, name: str, *, event: Event
    ) -> bool:
        """``reactions.add`` / ``reactions.remove`` of one status emoji; ``False``
        (logged, recorded as ``channel.reaction_failed``) when Slack refuses. A
        reaction already there, or already gone, is the outcome wanted."""
        try:
            call = client.reactions_add if verb == "add" else client.reactions_remove
            response = call(channel=channel_id, name=name, timestamp=ts)
            data = (
                response
                if isinstance(response, Mapping)
                else getattr(response, "data", None) or {}
            )
            if data.get("ok") is False and data.get("error") not in (
                "already_reacted",
                "no_reaction",
            ):
                raise ChannelError(str(data.get("error") or "error"))
            return True
        except Exception as exc:  # SlackApiError and transport errors alike
            error = getattr(getattr(exc, "response", None), "data", None) or {}
            if isinstance(error, Mapping) and error.get("error") in (
                "already_reacted",
                "no_reaction",
            ):
                return True
            logger.warning(
                "slack: could not %s the status reaction %s on %s: %s",
                verb,
                name,
                event.work_item,
                exc,
            )
            eventlog.emit(
                "channel.reaction_failed",
                level="warning",
                channel=self.name,
                work_item=event.work_item or None,
                state="status",
                content=name,
                error=str(exc),
            )
            return False

    def post(self, event: Event) -> PostResult:
        """Deliver ``event`` into its work item's conversation — opening it first,
        once, when none is bound (issue-312 R1).

        The lock covers the decision (is there a conversation? open and bind one)
        and not the delivery: the messages are posted after it is released, so a
        slow Slack call never holds the watcher's cursor advance. A post that
        fails is a :class:`ChannelError` and never a second root (R2.3) — only "no
        binding" opens one. An event with no work item posts top-level, unbound.

        Since issue-549 the path is one pipeline: the room policy (every
        conversation) → placement (room, central thread, mention thread) → the
        short and long builders → a :class:`MessagePlan` → one delivery step.
        """
        if event.event_type == GATE_ANSWERED:
            return self._close_gate(event)
        detail = event.detail or {}
        if event.event_type == sessionnotes.STALL_ENDED:
            return self._close_note(
                event, sessionnotes.stall_key(str(detail.get("stall_id") or ""))
            )
        if event.event_type == sessionnotes.ASK_DEFAULT_TAKEN:
            return self._close_note(
                event, sessionnotes.ask_key(str(detail.get("ask_id") or ""))
            )
        if not self.home_for(event.work_item):
            raise self._no_channel(event.work_item)
        client = self._client()
        bound: Optional[Tuple[str, str]] = None
        reply_to = ""
        question_ts = ""
        if event.work_item:
            with ChannelState.locked(self.state_path, self.stores) as state:
                before = state.conversation_for(event.work_item)
                bound = self._conversation(client, state, event.work_item)
                if before == bound and state.backfilled:
                    state.save(self.state_path)  # a 13.0.1 file, now keyed (R3.4)
                reply_to = self._reply_thread(state, event, bound)
                if event.event_type == sessionnotes.ASK_REMINDED:
                    asked = sessionnotes.ask_key(str(detail.get("ask_id") or ""))
                    question_ts = state.delivery_for(event.work_item)["gateTs"].get(
                        asked, ""
                    )
        # A declared room is a channel-mode binding: `thread_ts == ""` with a
        # channel (issue-378). The conversational rules (issue-393 B4) apply only
        # where the operator kept the agentic room style.
        in_room = bool(bound and bound[0] and not bound[1])
        agentic = in_room and self.config.room_style == "agentic"

        decision = self._room_decision(event, agentic)
        if decision.action == room_policy.DROP:
            logger.debug(
                "slack: room policy dropped %s for %s (%s)",
                event.event_type,
                event.work_item,
                decision.rule,
            )
            # Not posted, but still the work item's state (R10.3) and the recap's
            # record (R10.2).
            self._remember_event(event, Preamble())
            self._react_status(
                event,
                placement.ROOM if in_room else placement.CENTRAL,
                ("", ""),
                client,
            )
            return PostResult(
                channel=self.name, ok=True, thread=(bound and bound[1]) or ""
            )

        channel_id = bound[0] if bound and bound[0] else self.central_channel()
        threaded = decision.action == room_policy.THREAD and bool(decision.ts)
        if in_room:
            # an ack threads under its gate's message; an answer to a mention
            # goes in the mention's thread (issue-507); either way the long form
            # follows the short message in that thread (R4.3)
            # and the reminder goes under the question it is about, when this
            # channel posted that question (issue-551, R6.7)
            thread = decision.ts if threaded else (question_ts or reply_to)
            kind = placement.ROOM_MENTION_THREAD if thread else placement.ROOM
        else:
            # the central channel: everything is a reply in the item's one thread
            # (a gate message there is itself a reply, so an ack joins the thread)
            thread = reply_to or ((bound[1] or "") if bound else "")
            kind = placement.CENTRAL
        preamble = self._preamble(event)
        plan = self._plan(
            event,
            kind,
            decision,
            channel_id=channel_id,
            thread=thread,
            preamble=preamble.text,
        )
        try:
            delivered = self._deliver(client, event, plan)
        except ChannelError:
            raise
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: post failed: {exc}") from None
        logger.info(
            "slack: delivered event %s to %s (%s): %d long-form part(s), short form "
            "from %s%s, %d call(s)",
            event.event_id or "-",
            channel_id,
            kind,
            len(plan.parts),
            plan.short_source or "-",
            f", {plan.tables_as_code} table(s) as code" if plan.tables_as_code else "",
            delivered.calls,
        )
        # Record what the conversation now holds, so the next decision reads it.
        if event.work_item:
            self._remember_delivery(event, decision, delivered.top)
            self._remember_event(event, preamble)
            if decision.rule == "gate-pending" and delivered.top:
                self._remember_gate(event, channel_id, plan.top.text)
            note = _note_key(event)
            if note and delivered.top:
                self._remember_note(event, note, channel_id, plan.top.text)
        try:
            self._after_delivery(event, kind, plan, delivered, client)
        except Exception as exc:  # noqa: BLE001 — never fails a delivery
            logger.debug("slack: after-delivery hook failed (%s)", exc)
        posted_plain = decision.action not in (room_policy.EDIT, room_policy.THREAD)
        if reply_to and posted_plain:
            return PostResult(channel=self.name, ok=True, thread=reply_to)
        if bound and bound[1]:
            return PostResult(channel=self.name, ok=True, thread=bound[1])
        return PostResult(channel=self.name, ok=True, thread=delivered.top)

    def _remember_gate(self, event: Event, channel_id: str, text: str) -> None:
        """Keep what an open gate's message says and where (issue-549 R11.6),
        so it can be edited to its outcome when the gate is answered."""
        node = str((event.detail or {}).get("node") or "")
        if not node:
            return
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(
                    event.work_item,
                    gateMessage={
                        node: {"channel": channel_id, "text": text, "url": event.url}
                    },
                )
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug("slack: could not remember the gate %s (%s)", node, exc)

    def _close_gate(self, event: Event) -> PostResult:
        """Edit an answered gate's message to its outcome (issue-549 R11.6).

        The gate's message — remembered when it was posted — keeps its short
        form and its link, loses its Approve / Request changes buttons, and
        gains one line: the outcome and who answered. Nothing is posted: a gate
        with no remembered message is left as it is. The gate is then forgotten
        as open, so a later press on that message is stale (abuse case 8).
        ``chat.update`` takes no unfurl flags, so the edit adds no preview.
        """
        detail = event.detail or {}
        node = str(detail.get("node") or "")
        ok = PostResult(channel=self.name, ok=True)
        if not (event.work_item and node):
            return ok
        with ChannelState.locked(self.state_path, self.stores) as state:
            memory = state.delivery_for(event.work_item)
            ts = memory["gateTs"].get(node, "")
            gate = dict(memory["gateMessage"].get(node) or {})
            bound = state.conversation_for(event.work_item)
            if ts:
                state.remember_delivery(
                    event.work_item, gateTs={node: None}, gateMessage={node: None}
                )
                state.save(self.state_path)
        if not ts:
            return ok
        channel_id = gate.get("channel") or (bound[0] if bound else "")
        if not channel_id:
            return ok
        line = gate_answered_line(
            node, str(detail.get("outcome") or ""), str(detail.get("by") or "")
        )
        short = gate.get("text") or ""
        blocks: List[Dict[str, Any]] = []
        if short:
            blocks.append(_mrkdwn_section(short))
        blocks.append({"type": "context", "elements": [_mrkdwn(line)]})
        url = gate.get("url") or ""
        if url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": _message_actions(
                        Event(
                            event_type=GATE_ANSWERED,
                            work_item=event.work_item,
                            text="",
                            url=url,
                        )
                    ),
                }
            )
        error = ""
        try:
            client = self._client()
            with_retry(
                lambda: client.chat_update(
                    channel=channel_id,
                    ts=ts,
                    text=f"{short}\n{line}" if short else line,
                    blocks=blocks,
                ),
                "close the gate",
                self._sleep,
            )
        except Exception as exc:  # SlackApiError and transport errors alike
            error = str(exc)
            logger.warning(
                "slack: could not close the gate %s on %s: %s",
                node,
                event.work_item,
                exc,
            )
        eventlog.emit(
            "channel.gate_closed",
            level="warning" if error else "info",
            channel=self.name,
            work_item=event.work_item,
            node=node,
            outcome=str(detail.get("outcome") or "") or None,
            edited=not error,
            error=error or None,
        )
        return ok

    def _remember_note(
        self, event: Event, key: str, channel_id: str, text: str
    ) -> None:
        """Keep what a stall notice or a question says and where (issue-551), as
        an open gate's message is kept, so it can be edited when the stall ends
        or the default is taken. A work item has one open question: remembering
        a new one forgets the one before it."""
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                changes: Dict[str, Any] = {
                    key: {"channel": channel_id, "text": text, "url": event.url}
                }
                stale: Dict[str, Any] = {}
                if key.startswith("ask:"):
                    held = state.delivery_for(event.work_item)["gateTs"]
                    stale = {k: None for k in held if k.startswith("ask:") and k != key}
                state.remember_delivery(
                    event.work_item, gateMessage={**stale, **changes}
                )
                if stale:
                    state.remember_delivery(event.work_item, gateTs=stale)
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug("slack: could not remember %s (%s)", key, exc)

    def _close_note(self, event: Event, key: str) -> PostResult:
        """Edit a remembered message to how it ended (issue-551): the stall
        notice to its resolved form (R4.5), the question to "default taken"
        (R6.2). The status reaction returns to working.

        Nothing is posted, ever: a stall with no remembered notice was fixed by
        a nudge before anyone was told, and is left unsaid. The stall notice is
        replaced by its resolved line. The question keeps its words, loses its
        default button and gains the outcome line, as an answered gate does.
        """
        ok = PostResult(channel=self.name, ok=True)
        if not event.work_item:
            return ok
        with ChannelState.locked(self.state_path, self.stores) as state:
            memory = state.delivery_for(event.work_item)
            ts = memory["gateTs"].get(key, "")
            note = dict(memory["gateMessage"].get(key) or {})
            bound = state.conversation_for(event.work_item)
        in_room = bool(bound and bound[0] and not bound[1])
        kind = placement.ROOM if in_room else placement.CENTRAL
        stall = event.event_type == sessionnotes.STALL_ENDED
        channel_id = note.get("channel") or (bound[0] if bound else "")
        if not ts or not channel_id:
            # The session moved on whether or not its question was here. A
            # stall changed the reaction only if its notice was posted.
            if ts or not stall:
                self._react_status(event, kind, ("", ""))
            return ok
        line = build_short_form(event).text
        short = "" if stall else str(note.get("text") or "")
        blocks: List[Dict[str, Any]] = []
        if short:
            blocks.append(_mrkdwn_section(short))
            blocks.append({"type": "context", "elements": [_mrkdwn(line)]})
        else:
            blocks.append(_mrkdwn_section(line))
        url = note.get("url") or ""
        if url:
            blocks.append(
                {
                    "type": "actions",
                    "elements": _message_actions(
                        Event(
                            event_type=event.event_type,
                            work_item=event.work_item,
                            text="",
                            url=url,
                        )
                    ),
                }
            )
        try:
            client = self._client()
            with_retry(
                lambda: client.chat_update(
                    channel=channel_id,
                    ts=ts,
                    text=f"{short}\n{line}" if short else line,
                    blocks=blocks,
                ),
                "close the note",
                self._sleep,
            )
        except Exception as exc:  # SlackApiError and transport errors alike
            logger.warning(
                "slack: could not edit the message of %s on %s: %s",
                key,
                event.work_item,
                exc,
            )
            # The message keeps its old words, and stays remembered so that a
            # replay can edit it. The status is not left saying "stalled".
            self._react_status(event, kind, ("", ""))
            return ok
        # Forgotten only now: a message that was not edited is still open.
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                state.remember_delivery(
                    event.work_item, gateTs={key: None}, gateMessage={key: None}
                )
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — memory is best-effort
            logger.debug("slack: could not forget %s (%s)", key, exc)
        self._react_status(event, kind, ("", ""), client)
        return ok

    def delete_message(self, channel_id: str, ts: str) -> bool:
        """``chat.delete`` of one of the bot's own messages (issue-549 R6.2, for a
        long form that shrank). Best effort: ``False`` when Slack refused."""
        try:
            self._client().chat_delete(channel=channel_id, ts=ts)
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.debug("slack: chat.delete of %s failed (%s)", ts, exc)
            return False
        return True

    def remove_reaction(self, channel_id: str, ts: str, name: str) -> bool:
        """``reactions.remove`` of a reaction the bot added (issue-549 R8.5). Best
        effort: ``False`` when Slack refused."""
        try:
            self._client().reactions_remove(channel=channel_id, timestamp=ts, name=name)
        except Exception as exc:  # noqa: BLE001 — best effort
            logger.debug("slack: reactions.remove on %s failed (%s)", ts, exc)
            return False
        return True

    def _reply_thread(
        self, state: ChannelState, event: Event, bound: Optional[Tuple[str, str]]
    ) -> str:
        """The thread ``event`` answers in, or ``""`` (issue-507).

        A ``comment.agent`` goes to the work item's reply thread — the thread of
        the last mention delivered from one — when that thread is in the channel
        the conversation is bound to (R1.2, R3.2). Any other event, progress
        aside, starts a new conversation and clears it first (R2.3). Called inside
        :meth:`post`'s lock; a failure degrades to ``""``, today's top level.
        """
        try:
            memory = state.delivery_for(event.work_item)
            thread, channel = memory["replyThread"], memory["replyChannel"]
            if not thread:
                return ""
            if event.event_type == "comment.agent":
                return thread if bound and channel == bound[0] else ""
            if not room_policy.is_progress(event.event_type):
                state.remember_delivery(
                    event.work_item, replyChannel="", replyThread=""
                )
                state.save(self.state_path)
        except Exception as exc:  # noqa: BLE001 — never fails a post (R3.1)
            logger.debug(
                "slack: reply thread for %s unavailable (%s)", event.work_item, exc
            )
        return ""

    def open(self, work_item: str, *, origin: str = "start") -> PostResult:
        """Open ``work_item``'s thread now — the root alone, no reply — or
        return the one it already has (issue-317 R1.2, R1.3). ``origin`` is
        how the record says the conversation came to be: ``start`` from the
        spawn path, ``kickoff`` when a member's `/the-loop new` began it
        (issue-378).

        What the dispatcher's spawn path calls, through the bus, the moment a
        start is accepted: the same lock, root, bind and save as the lazy path
        in :meth:`post`, with ``origin="start"`` on the record, and nothing
        posted for a work item that is already bound. The refusals are
        :meth:`post`'s — no channel at all, no token — raised before any call; a
        root that fails to post raises and binds nothing, so the next event
        opens the thread lazily as before (R1.5).
        """
        if not self.home_for(work_item):
            raise self._no_channel(work_item)
        client = self._client()
        with ChannelState.locked(self.state_path, self.stores) as state:
            before = state.conversation_for(work_item)
            bound = self._conversation(client, state, work_item, origin=origin)
            if before == bound and state.backfilled:
                state.save(self.state_path)  # a 13.0.1 file, now keyed (R3.4)
        return PostResult(channel=self.name, ok=True, thread=bound[1])

    def _open_thread(
        self,
        client,
        state: ChannelState,
        work_item: str,
        *,
        channel_id: str = "",
        origin: str = "event",
    ) -> Tuple[str, str]:
        """Post the root for ``work_item``, bind it, save — inside the caller's
        lock. Returns ``(channel_id, thread_ts)``. A root that fails to post
        binds nothing, so the next event tries again. ``origin`` is how the
        record and ``channel.thread_opened`` say the thread came to be:
        ``event`` (the lazy path), ``start`` (issue-317) or ``declared``
        (issue-375: the work item was declared into a room after its
        conversation had already started elsewhere). ``channel_id`` is the room
        to open it in, defaulting to the operator's central channel."""
        room = channel_id or self.central_channel()
        url = _work_item_url(work_item)
        text, blocks = render_root(
            work_item, url, reading=self.config.read_mode != "off"
        )
        try:
            response = post_message(client, channel=room, text=text, blocks=blocks)
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: could not open a thread: {exc}") from None
        ts = str(response.get("ts") or "")
        if not ts:
            raise ChannelError("slack: could not open a thread: no ts returned")
        permalink = ""
        try:
            permalink = str(
                client.chat_getPermalink(channel=room, message_ts=ts).get("permalink")
                or ""
            )
        except Exception as exc:  # noqa: BLE001 — a nicety; the binding stands (A3)
            logger.debug("slack: no permalink for thread %s: %s", ts, exc)
        state.bind(ts, work_item, room, origin=origin, permalink=permalink)
        state.save(self.state_path)
        eventlog.emit(
            "channel.thread_opened",
            channel=self.name,
            work_item=work_item,
            thread=ts,
            channel_id=room,
            origin=origin,
        )
        return (room, ts)

    def _open_room(
        self,
        client,
        state: ChannelState,
        work_item: str,
        room: str,
        *,
        origin: str = "event",
    ) -> Tuple[str, str]:
        """Open ``work_item``'s conversation as the room ``room`` itself (issue-378
        R5.1): one top-level message naming the work item, a record with no
        thread and ``mode: channel``, saved — inside the caller's lock. Returns
        ``(room, "")``. A message that fails to post binds nothing, so the next
        event tries again, exactly as :meth:`_open_thread` behaves."""
        url = _work_item_url(work_item)
        text, blocks = render_room(
            work_item, url, reading=self.config.read_mode != "off"
        )
        try:
            response = post_message(client, channel=room, text=text, blocks=blocks)
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: could not open the room: {exc}") from None
        ts = str(response.get("ts") or "")
        if not ts:
            raise ChannelError("slack: could not open the room: no ts returned")
        permalink = ""
        try:
            permalink = str(
                client.chat_getPermalink(channel=room, message_ts=ts).get("permalink")
                or ""
            )
        except Exception as exc:  # noqa: BLE001 — a nicety; the binding stands
            logger.debug("slack: no permalink for room message %s: %s", ts, exc)
        state.bind(
            "", work_item, room, origin=origin, permalink=permalink, mode=ROOM_MODE
        )
        state.save(self.state_path)
        eventlog.emit(
            "channel.thread_opened",
            channel=self.name,
            work_item=work_item,
            thread="",
            channel_id=room,
            origin=origin,
            mode=ROOM_MODE,
        )
        return (room, "")

    def say(
        self,
        thread: str,
        text: str,
        channel_id: str = "",
        blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """A plain reply into ``thread`` — the kickoff's "here is your issue" —
        with ``blocks`` when the caller rendered any (its Do / Start buttons, issue-337, issue-529)."""
        try:
            post_message(
                self._client(),
                channel=channel_id or self.central_channel(),
                text=text,
                thread_ts=thread,
                blocks=blocks,
            )
        except Exception as exc:  # best-effort; the issue exists either way
            logger.warning("slack: could not reply in thread %s: %s", thread, exc)
            return False
        return True

    def bind(
        self,
        thread: str,
        work_item: str,
        channel_id: str = "",
        *,
        origin: str = "kickoff",
    ) -> None:
        """Bind ``thread`` to ``work_item`` — a kickoff's thread to its new issue.
        The thread a member started **is** the conversation (issue-312 R1.5)."""
        with ChannelState.locked(self.state_path, self.stores) as state:
            state.bind(
                thread, work_item, channel_id or self.central_channel(), origin=origin
            )
            state.save(self.state_path)
        eventlog.emit(
            "channel.thread_opened",
            channel=self.name,
            work_item=work_item,
            thread=thread,
            channel_id=channel_id or self.central_channel(),
            origin=origin,
        )

    # -- acknowledgment (issue-325) ---------------------------------------------

    def react(self, reply: InboundReply, state: str) -> bool:
        """Add the configured reaction for ``state`` to ``reply``'s message.

        **Never raises**: the acknowledgment is a decoration on a message the
        pipeline already accepted, and a decoration must never fail, delay or
        drop the record or the delivery — the ``GitHubReactor`` contract
        (issue-84), restated for this channel. Every failure is a
        ``channel.reaction_failed`` event and ``False``. A missing token is a
        quiet no-op: the read that produced the message already reported it.
        The call carries Slack's own ``channel``/``ts`` and a name the config
        parser validated — never the message text.
        """
        config = self.config.reactions
        if not config.enabled:
            return False
        content = config.content_for(state)
        if not content:
            return False  # the state is skipped ("") or unknown
        channel_id = reply.channel_id or self.central_channel()
        if not reply.ts or not channel_id:
            logger.debug(
                "slack: nothing to react on for %s (%s)", reply.work_item, state
            )
            return False
        try:
            client = self._client()
        except ChannelError as exc:
            logger.debug("slack: %s reaction skipped: %s", state, exc)
            return False
        try:
            client.reactions_add(channel=channel_id, name=content, timestamp=reply.ts)
        except Exception as exc:  # SlackApiError and transport errors alike
            logger.warning(
                "slack: could not add the %s reaction (%s) for %s: %s",
                state,
                content,
                reply.work_item or "a kickoff",
                exc,
            )
            eventlog.emit(
                "channel.reaction_failed",
                level="warning",
                channel=self.name,
                work_item=reply.work_item or None,
                state=state,
                content=content,
                thread=reply.thread or None,
                error=str(exc),
            )
            return False
        eventlog.emit(
            "channel.reaction_added",
            level="debug",
            channel=self.name,
            work_item=reply.work_item or None,
            state=state,
            content=content,
            thread=reply.thread or None,
        )
        return True

    # -- the press outcome (issue-337) ------------------------------------------

    def report_press(
        self,
        reply: InboundReply,
        message: Mapping[str, Any],
        action_id: str,
        outcome: Mapping[str, Any],
    ) -> bool:
        """Write what a button press did onto the pressed message (R2.1–R2.3).

        The message's blocks are handed back with the pressed button set replaced
        by a context line — ✅ / ⚠️, the button's name, the member, what landed
        and where — and the link buttons kept. A landed press removes the
        buttons (it acts once); a failed one keeps them (the retry). The line is
        fixed words plus the ``action_id``'s name, the member id, the ref and the
        record's URL — never ``reply.text``, never the payload's button text.

        **Never raises**, the ``react`` contract: the outcome the pipeline
        returned stands whatever Slack says. A refused edit (a message the bot
        did not post, a transport fault) is ``channel.press_report_failed`` and
        ``False``; a missing token is a quiet ``False``. Called only for a
        *processed* press — a dropped one is not reported, because a refusal
        leaves no mark (decision-111 D1).
        """
        channel_id = reply.channel_id or self.central_channel()
        if not reply.ts or not channel_id:
            return False
        try:
            client = self._client()
        except ChannelError as exc:
            logger.debug("slack: press report skipped: %s", exc)
            return False
        landed, line = _press_line(reply, action_id, outcome)
        blocks = _press_blocks(message, landed, line)
        text = str(message.get("text") or "").rstrip()
        text = f"{text}\n{line}" if text else line
        try:
            client.chat_update(
                channel=channel_id, ts=reply.ts, text=text, blocks=blocks
            )
        except Exception as exc:  # SlackApiError and transport errors alike
            logger.warning(
                "slack: could not report the press of %s on %s: %s",
                action_id,
                reply.work_item or "a message",
                exc,
            )
            eventlog.emit(
                "channel.press_report_failed",
                level="warning",
                channel=self.name,
                work_item=reply.work_item or None,
                thread=reply.thread or None,
                action=action_id,
                error=str(exc),
            )
            return False
        eventlog.emit(
            "channel.press_reported",
            channel=self.name,
            work_item=reply.work_item or None,
            thread=reply.thread or None,
            action=action_id,
            outcome="landed" if landed else "failed",
        )
        return True

    # -- inbound (R4) ----------------------------------------------------------

    def _own_user_id(self, client) -> str:
        """The bot's own user id, for the Slack-side loop-prevention drop."""
        if self._own_user is None:
            try:
                self._own_user = str(client.auth_test().get("user_id") or "")
            except Exception as exc:  # best-effort; bot_id still catches bots
                logger.warning("slack: auth.test failed: %s", exc)
                self._own_user = ""
        return self._own_user

    def own_user_id(self) -> str:
        """The bot's own member id, or ``""`` when it cannot be learned — what
        the inbound pipeline strips a mention's ``<@…>`` token by (issue-389)."""
        try:
            return self._own_user_id(self._client())
        except ChannelError:
            return ""

    def hears_messages(self, channel_id: str) -> bool:
        """Whether a plain ``message.*`` event in ``channel_id`` is input
        (issue-389 R1.2, R1.6, R2.2): in a direct message with the bot, and in
        a room an authorized user declared ``--listen all``. Everywhere else the
        mention is the address and a plain message is ``not-addressed``."""
        if (channel_id or "")[:1].upper() == "D":
            return True
        if self.stores is None:
            return False
        return self.stores.listen_mode(channel_id) == "all"

    def open_view(self, trigger_id: str, view: Mapping[str, Any]) -> bool:
        """Open ``view`` on ``trigger_id`` — the decision modal (issue-389 R6.3).
        Never raises: an expired trigger, a missing token or a refused open is
        ``channel.shortcut_failed`` and ``False``."""
        if not trigger_id:
            return False
        try:
            self._client().views_open(trigger_id=trigger_id, view=dict(view))
        except Exception as exc:  # noqa: BLE001 — the member is told, the listener lives
            logger.warning("slack: could not open the decision modal: %s", exc)
            eventlog.emit(
                "channel.shortcut_failed",
                level="warning",
                channel=self.name,
                error=str(exc),
            )
            return False
        return True

    def post_ephemeral(
        self, channel_id: str, user: str, text: str, thread: str = ""
    ) -> bool:
        """A message only ``user`` sees, in ``channel_id`` — the `help` answer,
        a refusal's reason, a shortcut's outcome (issue-389 R3.2, R5.2, R6.5) —
        inside ``thread`` when the member is in one, so the answer appears where
        they are looking. Never raises; a refused post is a debug line and
        ``False``."""
        if not channel_id or not user or not text:
            return False
        extra: Dict[str, Any] = {"thread_ts": thread} if thread else {}
        try:
            self._client().chat_postEphemeral(
                channel=channel_id, user=user, text=text[: _SECTION_LIMIT * 10], **extra
            )
        except Exception as exc:  # noqa: BLE001 — an answer is a nicety
            logger.debug("slack: could not post ephemerally in %s: %s", channel_id, exc)
            return False
        return True

    def snapshot_thread(
        self, channel_id: str, thread: str, since: str = "", skip: str = ""
    ) -> Snapshot:
        """The thread ``thread`` in ``channel_id`` as `record-context` records it
        (issue-389 R4.1, R4.4, R4.5): every message after ``since`` (the root
        included when ``since`` is empty), ascending, each drawn as
        ``**@name** (HH:MM UTC, link): text`` with the name from the cached
        directory and the link composed from the workspace URL ``auth.test``
        returns — no call per message — capped by :data:`SNAPSHOT_MESSAGE_CAP`
        and :data:`SNAPSHOT_CHAR_CAP`, the thread's permalink for the rest.
        The-loop's own messages are included, attributed to the bot: they are
        part of the discussion; the message whose ts is ``skip`` — the
        ``record-context`` mention itself — is not. A member mentioned inside
        a message is drawn by name where the directory knows them. Raises
        :class:`ChannelError` when the thread cannot be read.
        """
        client = self._client()
        try:
            response = client.conversations_replies(
                channel=channel_id, ts=thread, oldest=since or None, limit=200
            )
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: could not read the thread: {exc}") from None
        messages = sorted(
            (m for m in (response.get("messages") or []) if m.get("ts")),
            key=lambda m: _ts_key(str(m["ts"])),
        )
        if since:
            messages = [m for m in messages if _ts_key(str(m["ts"])) > _ts_key(since)]
        if skip:
            messages = [m for m in messages if str(m["ts"]) != skip]
        own = self._own_user_id(client)
        if own:
            # An earlier `@the-loop record-context` in the thread is the act
            # that recorded it, never context — whichever cursor arithmetic
            # brought it back (a capped or failed record before this one).
            from .verbs import parse_verb, strip_mention

            def is_trigger(message: Mapping[str, Any]) -> bool:
                text, found = strip_mention(str(message.get("text") or ""), own)
                verb = parse_verb(text) if found else None
                return verb is not None and verb.name == "record-context"

            messages = [m for m in messages if not is_trigger(m)]
        # Slack pages a long thread; what this page did not carry is "more",
        # uncounted, rather than a wrong count.
        more = bool(response.get("has_more"))
        workspace = ""
        try:
            workspace = str(client.auth_test().get("url") or "").rstrip("/")
        except Exception:  # noqa: BLE001 — the link is a nicety
            workspace = ""
        directory = self.directory()
        lines: List[str] = []
        count = 0
        size = 0
        newest = since
        truncated = False
        for message in messages:
            ts = str(message["ts"])
            author = str(message.get("user") or "")
            if author and author == own:
                name = "the-loop"
            elif author:
                name = directory.user_name(author) or author
            else:
                name = str(message.get("username") or message.get("bot_id") or "bot")
            when = _clock(ts)
            link = ""
            if workspace:
                link = f"{workspace}/archives/{channel_id}/p{ts.replace('.', '')}"
                if ts != thread:
                    link += f"?thread_ts={thread}&cid={channel_id}"
            body = " ".join(str(message.get("text") or "").split())
            body = _MENTION_IN_TEXT_RE.sub(
                lambda m: (
                    "@"
                    + (
                        "the-loop"
                        if m.group(1) == own
                        else directory.user_name(m.group(1)) or m.group(1)
                    )
                ),
                body,
            )
            for file in _files_of(message):
                # A screenshot in a recorded thread is a link, not a blank line
                # (issue-416 R3.3): the name and the permalink, nothing fetched.
                pin = attachments.safe_name(
                    str(file.get("name") or file.get("title") or "")
                )
                permalink = str(file.get("permalink") or "")
                body = (
                    body + f" 📎 {pin}" + (f" ({permalink})" if permalink else "")
                ).strip()
            line = f"**@{name}** ({when}" + (f", {link}" if link else "") + f"): {body}"
            if count >= SNAPSHOT_MESSAGE_CAP or size + len(line) > SNAPSHOT_CHAR_CAP:
                truncated = True
                break
            lines.append(line)
            count += 1
            size += len(line) + 1
            newest = ts
        permalink = ""
        if workspace:
            permalink = f"{workspace}/archives/{channel_id}/p{thread.replace('.', '')}"
        if truncated or more:
            left = len(messages) - count
            rest = (
                strings.t("channels.slack.snapshot.more-left", left=left)
                if not more
                else strings.t("channels.slack.snapshot.more")
            )
            lines.append(rest + (f": {permalink}" if permalink else ""))
        return Snapshot(
            text="\n".join(lines),
            count=count,
            newest=newest,
            permalink=permalink,
            truncated=truncated or more,
        )

    def fetch_replies(self) -> List[InboundReply]:
        """Every not-yet-processed reply in every bound thread (R4.4, R4.6).

        Only bound threads are queried — the bot structurally cannot read the
        channel at large through this path. The cursor filter is applied
        client-side (strictly newer than the last processed ts), so the exact
        inclusivity semantics of the API's ``oldest`` never matter.
        """
        state = ChannelState.load(self.state_path, self.stores)
        if not state.threads:
            return []
        client = self._client()
        own_user = self._own_user_id(client)
        replies: List[InboundReply] = []
        for thread, info in state.threads.items():
            cursor = state.cursor(thread)
            channel_id = info.get("channel") or self.central_channel()
            if not self.hears_messages(channel_id):
                # The mention is the address (issue-389 R1.7): a plain message
                # here is not input, and this read has no mention event — so
                # nothing is read and the cursor stays where the listener left
                # it, never ahead of a mention it has yet to process.
                continue
            try:
                response = client.conversations_replies(
                    channel=channel_id,
                    ts=thread,
                    oldest=cursor,
                )
            except Exception as exc:
                logger.warning(
                    "slack: conversations.replies failed for thread %s: %s",
                    thread,
                    exc,
                )
                continue
            for message in response.get("messages") or []:
                ts = str(message.get("ts") or "")
                if not ts or ts == thread or _ts_key(ts) <= _ts_key(cursor):
                    continue
                author = str(message.get("user") or "")
                replies.append(
                    InboundReply(
                        channel=self.name,
                        work_item=str(info.get("workItem") or ""),
                        author=author,
                        text=str(message.get("text") or ""),
                        thread=thread,
                        ts=ts,
                        is_bot=bool(message.get("bot_id"))
                        or bool(own_user and author == own_user),
                        channel_id=channel_id,
                        files=_files_of(message),
                    )
                )
        return replies

    def fetch_kickoffs(self) -> List[InboundReply]:
        """Every not-yet-seen TOP-LEVEL message in the configured channel — only
        with the ``work-item.create`` grant and a ``kickoff.repo`` (R6.5).

        **First sight baselines.** With no cursor yet, the newest message's ts is
        recorded and nothing is returned: a channel's backlog must never become a
        burst of issues the moment an operator turns the grant on — the poller's
        own first-sight rule (issue-80), applied here.
        """
        if not self.config.kickoff_enabled:
            return []
        if not self.hears_messages(self.central_channel()):
            # A kickoff by mention arrives as `app_mention` on the listener
            # (issue-389 R1.5); the poll read has no mention to go on.
            return []
        if self.stores is not None and self.stores.declared_work_item(
            self.central_channel()
        ):
            # The central channel is somebody's declared room (issue-375). A
            # dedicated room has one subject, so a message there is a message on
            # that work item — `fetch_channel_messages` reads it — and opening a
            # second issue from it would be the opposite of what was declared.
            return []
        state = ChannelState.load(self.state_path, self.stores)
        key = kickoff_cursor_key(self.central_channel())
        cursor = state.cursors.get(key, "")
        client = self._client()
        try:
            response = client.conversations_history(
                channel=self.central_channel(), oldest=cursor or None
            )
        except Exception as exc:
            logger.warning("slack: conversations.history failed: %s", exc)
            return []
        messages = [m for m in (response.get("messages") or []) if m.get("ts")]
        if not cursor:
            newest = max((str(m["ts"]) for m in messages), key=_ts_key, default="0")
            self.advance(key, newest)
            logger.info(
                "slack: kickoff read baselined at %s — earlier top-level messages "
                "are never turned into work items",
                newest,
            )
            return []
        own_user = self._own_user_id(client)
        found: List[InboundReply] = []
        for message in sorted(messages, key=lambda m: _ts_key(str(m["ts"]))):
            ts = str(message["ts"])
            thread_ts = str(message.get("thread_ts") or "")
            if _ts_key(ts) <= _ts_key(cursor):
                continue
            if thread_ts and thread_ts != ts:
                continue  # a reply; the thread reader owns it
            if state.work_item_for(ts):
                continue  # a thread root the-loop itself started
            author = str(message.get("user") or "")
            found.append(
                InboundReply(
                    channel=self.name,
                    work_item="",
                    author=author,
                    text=str(message.get("text") or ""),
                    thread=ts,
                    ts=ts,
                    is_bot=bool(message.get("bot_id"))
                    or message.get("subtype") == "bot_message"
                    or bool(own_user and author == own_user),
                    top_level=True,
                    channel_id=self.central_channel(),
                    files=_files_of(message),
                )
            )
        return found

    def fetch_channel_messages(self) -> List[InboundReply]:
        """Every not-yet-seen message in a channel a work item DECLARED (issue-375).

        The reader half of "a dedicated room has one subject": a top-level message
        in that room is a message *on that work item*, not a new issue and not an
        unmapped drop. Each declared channel carries its own cursor — the same
        ``channel:<id>`` key the kickoff read uses — so a room is read once
        whatever else is being polled.

        **First sight baselines**, exactly as the kickoff read does: declaring a
        channel with a month of history in it must not deliver that month to the
        session. With no cursor for the room, the newest ts is recorded and
        nothing is returned.

        What this path does *not* see is a reply inside a thread it did not open:
        ``conversations.history`` returns top-level messages, so an unbound
        thread's replies are read only under Socket Mode, where Slack delivers
        every message. A thread the-loop DID bind is read by
        :meth:`fetch_replies`, and its root is skipped here so the two reads
        cannot both claim one message.
        """
        if self.stores is None:
            return []
        targets = self.stores.declared_targets()
        if not targets:
            return []
        state = ChannelState.load(self.state_path, self.stores)
        client = self._client()
        own_user = self._own_user_id(client)
        found: List[InboundReply] = []
        for target, work_item in sorted(targets.items()):
            if not self.hears_messages(target):
                continue  # a `mentions` room: the listener hears it (issue-389)
            key = kickoff_cursor_key(target)
            cursor = state.cursors.get(key, "")
            try:
                response = client.conversations_history(
                    channel=target, oldest=cursor or None
                )
            except Exception as exc:
                logger.warning(
                    "slack: conversations.history failed for %s: %s", target, exc
                )
                continue
            messages = [m for m in (response.get("messages") or []) if m.get("ts")]
            if not cursor:
                newest = max((str(m["ts"]) for m in messages), key=_ts_key, default="0")
                self.advance(key, newest)
                logger.info(
                    "slack: %s's collaboration channel %s baselined at %s — earlier "
                    "messages are never delivered",
                    work_item,
                    target,
                    newest,
                )
                continue
            for message in sorted(messages, key=lambda m: _ts_key(str(m["ts"]))):
                ts = str(message["ts"])
                thread_ts = str(message.get("thread_ts") or "")
                if _ts_key(ts) <= _ts_key(cursor):
                    continue
                if thread_ts and thread_ts != ts:
                    continue  # a broadcast reply; the thread reader owns it
                if state.work_item_for(ts):
                    continue  # a bound thread's root — `fetch_replies` owns it
                author = str(message.get("user") or "")
                found.append(
                    InboundReply(
                        channel=self.name,
                        work_item=work_item,
                        author=author,
                        text=str(message.get("text") or ""),
                        thread=ts,
                        ts=ts,
                        is_bot=bool(message.get("bot_id"))
                        or message.get("subtype") == "bot_message"
                        or bool(own_user and author == own_user),
                        channel_id=target,
                        files=_files_of(message),
                    )
                )
        return found

    def advance(self, thread: str, ts: str) -> None:
        """Persist that everything in ``thread`` up to ``ts`` was processed —
        under the lock, so a cursor never overwrites a binding written beside it."""
        with ChannelState.locked(self.state_path, self.stores) as state:
            state.advance(thread, ts)
            state.save(self.state_path)

    def advance_kickoff(self, ts: str) -> None:
        self.advance(kickoff_cursor_key(self.central_channel()), ts)


def _press_line(
    reply: InboundReply, action_id: str, outcome: Mapping[str, Any]
) -> Tuple[bool, str]:
    """``(landed, line)`` for a processed press, from fixed words (R2.6)."""
    if is_kickoff_repo_action(action_id):
        # The repository picker (issue-349): the press did not answer a gate or
        # relay a keyword — it opened the work item the question was holding, or
        # it did not, and the member is told which on the question itself.
        return _kickoff_press_line(reply, action_id, outcome)
    event_type = str(outcome.get("event") or "")
    mirrored = bool(outcome.get("mirrored"))
    delivered = bool(outcome.get("delivered"))
    error = str(outcome.get("error") or "").strip()
    url = str(outcome.get("url") or "")
    ref = reply.work_item or strings.t("channels.slack.press.the-work-item")
    where = f"<{url}|{ref}>" if url else f"`{ref}`"
    refused_comment = error or strings.t("channels.slack.press.ledger-refused-comment")
    if event_type == "control.command":
        landed = mirrored
        what = (
            strings.t("channels.slack.press.command-recorded", where=where)
            if landed
            else strings.t("channels.slack.press.not-recorded", error=refused_comment)
        )
    elif event_type == "gate.feedback":
        landed = mirrored
        what = (
            strings.t("channels.slack.press.feedback-recorded", where=where)
            if landed
            else strings.t("channels.slack.press.not-recorded", error=refused_comment)
        )
    else:  # work-item.reply — a standing session has no record to make
        from ..standing import parse_standing_ref

        standing = bool(parse_standing_ref(reply.work_item))
        landed = delivered and (mirrored or standing)
        if landed:
            what = strings.t("channels.slack.press.delivered") + (
                strings.t("channels.slack.press.delivered-recorded", where=where)
                if mirrored
                else ""
            )
        elif not delivered:
            what = strings.t(
                "channels.slack.press.not-delivered",
                error=error or strings.t("channels.slack.press.no-session"),
            )
        else:
            what = strings.t(
                "channels.slack.press.delivered-not-recorded",
                error=error or strings.t("channels.slack.press.ledger-refused"),
            )
    name = _button_name(action_id)
    icon = "✅" if landed else "⚠️"
    return landed, strings.t(
        "channels.slack.press.line",
        icon=icon,
        name=name,
        author=reply.author,
        what=what,
    )


#: Why a repository pick did nothing — fixed words per drop reason (R2.6), and
#: never a repository name: a refused pick names nothing the member did not
#: already see on the question above it.
KICKOFF_REFUSALS: Dict[str, str] = strings.section("slack.kickoff-refusal")


def _kickoff_press_line(
    reply: InboundReply, action_id: str, outcome: Mapping[str, Any]
) -> Tuple[bool, str]:
    """``(landed, line)`` for a press of the repository picker (issue-349).

    Three shapes: the work item opened; the create was attempted and failed; or
    one of the three gates below the allow-list refused it. Only the first
    ``landed``, so only the first takes the picker away — the other two leave it
    where it is, which is the same rule a failed command press already follows.
    """
    what = str(outcome.get("outcome") or "")
    opened = str(outcome.get("workItem") or "")
    if what == "created" and opened:
        url = str(outcome.get("url") or "")
        where = f"<{url}|{opened}>" if url else f"`{opened}`"
        said = strings.t("channels.slack.press.opened", where=where)
        landed = True
    elif what in KICKOFF_REFUSALS:
        said = KICKOFF_REFUSALS[what]
        landed = False
    else:
        problem = str(outcome.get("error") or "").strip()
        said = strings.t(
            "channels.slack.press.nothing-opened",
            problem=problem or strings.t("channels.slack.press.ledger-refused"),
        )
        landed = False
    return (
        landed,
        strings.t(
            "channels.slack.press.line",
            icon="✅" if landed else "⚠️",
            name=_button_name(action_id),
            author=reply.author,
            what=said,
        ),
    )


def _press_blocks(
    message: Mapping[str, Any], landed: bool, line: str
) -> List[Dict[str, Any]]:
    """The pressed message's blocks, rebuilt: an ``actions`` block keeps its link
    (``url``) elements only once the press landed — every element while it did
    not — and is dropped when nothing remains; the phase-selection control's
    blocks (issue-393 R9) go with the landed press too, having acted once; the
    outcome line closes the message. A message with no blocks is its text."""
    blocks: List[Dict[str, Any]] = []
    source = message.get("blocks")
    if not isinstance(source, list) or not source:
        source = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": str(message.get("text") or " ")},
            }
        ]
    for block in source:
        if not isinstance(block, Mapping):
            continue
        if landed and str(block.get("block_id") or "").startswith(SELECTION_BLOCK):
            continue
        if block.get("type") != "actions":
            blocks.append(dict(block))
            continue
        elements = [
            e
            for e in (block.get("elements") or [])
            if isinstance(e, Mapping) and (not landed or e.get("url"))
        ]
        if elements:
            blocks.append({**block, "elements": elements})
    blocks.append(
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": line[:_SECTION_LIMIT]}],
        }
    )
    return blocks


def _clock(ts: str) -> str:
    """``HH:MM UTC`` from a Slack ts, or the ts itself when it is not one."""
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%H:%M UTC")
    except (TypeError, ValueError, OverflowError, OSError):
        return ts


def _ts_key(ts: str) -> Tuple[int, Any]:
    """Slack ts ordering that survives a non-numeric value."""
    try:
        return (0, float(ts))
    except ValueError:
        return (1, ts)


# -- Socket Mode (R4.2) ----------------------------------------------------------


def catch_up(cli_config: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """One read cycle over the bound threads and the kickoff cursor — what the
    listener runs right after it connects (issue-334, the downtime gap).

    Slack retries an unacknowledged event only a few times over a few minutes;
    a reply posted during a longer outage would otherwise stay on Slack and
    never reach the ledger. The two transports share the per-thread cursors,
    so the cycle processes exactly what accumulated since the last handled
    ``ts`` and nothing twice. Best-effort: a failing cycle is logged and the
    listener still listens.
    """
    from . import inbound

    try:
        summary = inbound.poll_once(cli_config)
    except Exception as exc:  # noqa: BLE001 — never keep the listener from listening
        logger.exception("slack: catch-up read raised; listening anyway")
        return {"skipped": str(exc), "replies": 0}
    if summary.get("skipped"):
        logger.info("slack: catch-up read skipped: %s", summary["skipped"])
        return summary
    eventlog.emit(
        "channel.caught_up",
        channel="slack",
        replies=summary.get("replies", 0),
        processed=summary.get("processed", 0),
        delivered=summary.get("delivered", 0),
        created=summary.get("created", 0),
        dropped=summary.get("dropped", 0),
    )
    return summary


def report_subscription(
    config: "SlackChannelConfig", cli_config: Optional[Mapping[str, Any]] = None
) -> None:
    """Probe the installed app once and log what it cannot receive (R2.4).

    Best-effort in both directions: a probe that cannot run is an ``info`` line,
    a probe that raises is swallowed, and neither keeps the listener from
    listening. The words are :func:`subscription_findings`' own, so an operator
    reads the same sentence here and in ``the-loop channels status --probe``.
    """
    try:
        result = probe_subscription(config, cli_config=cli_config)
    except Exception:  # noqa: BLE001 — a diagnostic never costs a channel its listener
        logger.exception("slack: the subscription probe raised; listening anyway")
        return
    if result.get("skipped"):
        logger.info(
            "slack: subscription not checked (%s) — `the-loop channels status "
            "--probe` checks it",
            result["skipped"],
        )
        return
    for finding in result.get("findings") or ():
        logger.warning("slack: %s", finding)
    # What the app is EXPECTED to hear, and why nobody can confirm it (issue-393
    # R2.1) — one info line at connect, so the e2e failure "scopes fine, no
    # event ever arrives" has its explanation in the log before it happens.
    events = result.get("events") or ()
    if events:
        logger.info(
            "slack: the manifest subscribes the bot to %s — %s",
            ", ".join(events),
            EVENTS_UNVERIFIABLE_CAVEAT,
        )


def _split_check(watch: Any, waiter: threading.Event) -> None:
    """One split check, guarded (issue-413, R1.7).

    ``run_cycle`` already swallows everything it can name; this guards what it
    cannot — the call itself, a future refactor — because a listener that dies
    on a diagnostic is strictly worse than one that never diagnosed.
    """
    if watch is None:
        return
    try:
        watch.run_cycle(stop_event=waiter)
    except Exception:  # noqa: BLE001 — a diagnostic never ends the listener
        logger.exception("slack: the split check raised; still listening")


#: The Socket Mode envelope types the listener handles; everything else is ignored.
ENVELOPE_TYPES = ("events_api", "interactive", "slash_commands")


def heartbeat_of(kind: str, payload: Mapping[str, Any]) -> str:
    """The split check's nonce when ``payload`` is the doctor's own heartbeat
    (an ``events_api`` bot message carrying the marker), else ``""``."""
    if kind != "events_api":
        return ""
    event = payload.get("event") or {}
    if not isinstance(event, Mapping) or event.get("type") != "message":
        return ""
    return heartbeat_nonce(event)


def dispatch_envelope(
    kind: str, payload: Mapping[str, Any], cli_config: Mapping[str, Any]
) -> str:
    """Classify and act on one Slack envelope — the half of the listener that is not
    the transport (issue-496).

    ``kind`` is the Socket Mode envelope type (:data:`ENVELOPE_TYPES`) and ``payload``
    its body: a slash command goes to :mod:`.commands`, an interactive payload to the
    matching :mod:`.inbound` handler by its ``type``, an ``events_api`` ``app_mention``
    or ``message`` to :func:`.inbound.handle_socket_event`. Called by the gateway-less
    listener's ``handle`` after it acknowledged the envelope, and by the gateway client
    for a delivery fetched from its queue, so there is exactly one classifier whichever
    way the envelope arrived. Returns a short outcome for the log:
    ``handled:<what>`` or ``ignored:<why>``.
    """
    from . import commands, inbound

    config = dict(cli_config or {})
    if kind == "slash_commands":
        commands.handle_slash_command(dict(payload), config)
        return "handled:slash-command"
    if kind == "interactive":
        itype = payload.get("type")
        if itype == "block_actions":
            inbound.handle_socket_action(dict(payload), config)
            return "handled:block-actions"
        if itype == "message_action":
            inbound.handle_message_action(dict(payload), config)
            return "handled:message-action"
        if itype == "view_submission":
            inbound.handle_view_submission(dict(payload), config)
            return "handled:view-submission"
        logger.debug(
            "slack: ignoring an interactive payload of kind %r "
            "(handled: block_actions, message_action, view_submission)",
            itype,
        )
        return "ignored:interactive-kind"
    if kind != "events_api":
        return "ignored:envelope-type"
    event = payload.get("event") or {}
    if not isinstance(event, Mapping):
        return "ignored:event-shape"
    event_type = event.get("type")
    if event_type == "app_mention":
        inbound.handle_socket_event(dict(event), config, addressed=True)
        return "handled:app-mention"
    if event_type != "message":
        logger.debug(
            "slack: ignoring an events_api event of type %r in channel %r "
            "(handled: app_mention, message)",
            event_type,
            event.get("channel") or event.get("channel_id") or "",
        )
        return "ignored:event-type"
    if heartbeat_nonce(event):
        return "ignored:heartbeat"
    inbound.handle_socket_event(dict(event), config, addressed=False)
    return "handled:message"


def run_socket_listener(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: Optional[threading.Event] = None,
    *,
    catch_up_override: Optional[float] = None,
) -> int:
    """Receive replies, button presses, kickoffs and slash commands push-fashion
    until stopped — ``the-loop channels listen``.

    Uses the SDK's built-in Socket Mode client (stdlib WebSocket — no extra
    dependency) over an *outbound* connection, so nothing is exposed. Every
    accepted envelope is acknowledged **before** it is handled, so Slack's
    deadline is met whatever the handling takes; messages and presses converge
    on the same pipeline the poll transport uses (:mod:`.inbound`), and a
    ``/the-loop`` slash command (issue-334) on :mod:`.commands`, which answers
    through the command's ``response_url``.
    """
    config = SlackChannelConfig.from_mapping(cli_config)
    if not config.enabled:
        logger.error("channels.slack is not enabled — nothing to listen for")
        return 1
    if config.gateway:
        # issue-503 R4.3: one app has one Socket Mode connection, and the gateway
        # holds it — whatever read.mode says, a second consumer here would split
        # every envelope between the two.
        logger.error(
            "a gateway block is configured — this instance consumes Slack from the "
            "gateway, which holds the app's Socket Mode connection; not opening a "
            "second one (read.mode: gateway is the setting for this instance)"
        )
        return 1
    if config.read_mode != "socket":
        logger.error(
            "channels.slack.read.mode is %r — set it to 'socket' to listen",
            config.read_mode,
        )
        return 1
    app_token = os.environ.get(config.app_token_env) or ""
    bot_token = os.environ.get(config.bot_token_env) or ""
    if not app_token or not bot_token:
        logger.error(
            "slack: Socket Mode needs both tokens — export %s (xapp-, "
            "connections:write) and %s (xoxb-)",
            config.app_token_env,
            config.bot_token_env,
        )
        return 1

    from slack_sdk.socket_mode import (  # type: ignore[import-not-found]
        SocketModeClient,
    )
    from slack_sdk.socket_mode.response import (  # type: ignore[import-not-found]
        SocketModeResponse,
    )

    from . import splitwatch

    frozen_config = dict(cli_config or {})
    web_client = build_client(bot_token)
    # The listener's own split check (issue-413). `None` when the deployment
    # asks for none (`read.splitCheckBeats: 0`); every other obstacle is a
    # recorded `unverifiable`, so "all is well" and "never ran" stay distinct.
    watch = splitwatch.SplitWatch.for_config(
        frozen_config, client=web_client, config=config
    )

    def handle(client, request) -> None:
        if request.type not in ENVELOPE_TYPES:
            logger.debug(
                "slack: ignoring a Socket Mode envelope of type %r (handled: "
                "events_api, interactive, slash_commands)",
                request.type,
            )
            return
        client.send_socket_mode_response(
            SocketModeResponse(envelope_id=request.envelope_id)
        )
        payload = request.payload or {}
        try:
            # The transport half (issue-496): the doctor's heartbeat is consumed by
            # the connection that heard it and never classified.
            nonce = heartbeat_of(request.type, payload)
            if nonce:
                event = payload.get("event") or {}
                eventlog.emit(
                    "channel.heartbeat",
                    channel="slack",
                    channel_id=str(event.get("channel") or ""),
                    ts=str(event.get("ts") or ""),
                    nonce=nonce,
                )
                if watch is not None:
                    watch.observe(nonce)
                return
            dispatch_envelope(request.type, payload, frozen_config)
        except Exception:  # one bad message never ends the listener
            logger.exception("slack: socket event handling raised; continuing")

    client = SocketModeClient(app_token=app_token, web_client=web_client)
    client.socket_mode_request_listeners.append(handle)
    client.connect()
    logger.info(
        "slack: Socket Mode connected — listening for mentions, button presses, "
        "shortcuts and /the-loop commands"
    )
    report_subscription(config, frozen_config)
    catch_up(frozen_config)
    # The periodic reconcile (issue-362, R3): one deadline carried through the
    # existing one-second tick rather than a second thread, so the stop event is
    # still honoured within a tick whatever the interval is. `monotonic`, not the
    # wall clock — an NTP step or a DST change must not move a cadence.
    interval = (
        float(catch_up_override)
        if catch_up_override is not None
        else float(config.catch_up_seconds)
    )
    tick = min(1.0, interval) if interval > 0 else 1.0
    due = time.monotonic() + interval if interval > 0 else None
    if due is not None:
        logger.info("slack: reconciling the bound threads every %gs", interval)
    waiter = stop_event or threading.Event()
    # The split check rides the reconcile's deadline (issue-413) rather than a
    # cadence of its own: a second key is a second thing to get wrong, and
    # "how late may an inbound envelope be" is exactly the question a split
    # makes urgent. `catchUpSeconds: 0` therefore keeps its connect-only
    # contract for both.
    _split_check(watch, waiter)
    try:
        while not waiter.wait(tick):
            if due is not None and time.monotonic() >= due:
                try:
                    catch_up(frozen_config)
                except Exception:  # noqa: BLE001 — R3.3: a cycle never ends the listener
                    # `catch_up` already swallows what `poll_once` raises; this
                    # guards everything around it (the event emit, a future
                    # refactor), because a listener that dies on a reconcile is
                    # strictly worse than one that never reconciled.
                    logger.exception("slack: reconcile cycle raised; still listening")
                _split_check(watch, waiter)
                due = time.monotonic() + interval
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        logger.info("slack: Socket Mode listener stopped")
    return 0


def _without_preamble(text: str, preamble: str) -> str:
    """``text`` with the ``preamble`` it opens with removed: what a long-form
    part's ``text`` fallback carries, so a mention reaches only the top message
    (issue-549 R7.4). ``""`` when there is no preamble (the part uses the short
    form itself)."""
    preamble = preamble.strip()
    if not preamble:
        return ""
    if text.startswith(preamble):
        return text[len(preamble) :].lstrip("\n") or text
    return text
