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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from .. import eventlog
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
    render,
)
from .digest import (
    DEFAULT_DIGEST_MODE,
    DIGEST_MODES,
    fit,
    sanitize_summary,
    truncate,
)
from .events import APPROVAL_EVENTS, PUBLISHABLE_EVENTS, SUBSCRIBABLE_EVENTS
from . import room_policy
from .state import ROOM_MODE, ChannelState, ChannelStores
from .voice import room_lead

logger = logging.getLogger("the-loop.channels")

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
    "BUTTON_CHOICE_LIMIT",
    "KICKOFF_REFUSALS",
    "BUTTON_NAMES",
    "CHANGES_VALUE",
    "COMMAND_BUTTONS",
    "KICKOFF_REPO_ACTION",
    "OPTION_LIMIT",
    "DEFAULT_APP_TOKEN_ENV",
    "DEFAULT_BOT_TOKEN_ENV",
    "DEFAULT_MAX_CHARS",
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
    "REACTION_STATES",
    "READ_MODES",
    "CONVERSATION_KINDS",
    "ConversationKind",
    "DEFAULT_CATCH_UP_SECONDS",
    "MIN_CATCH_UP_SECONDS",
    "kind_from_info",
    "kind_summary",
    "kinds_from_id",
    "probe_subscription",
    "subscription_findings",
    "unchecked_advice",
    "EVENTS_UNVERIFIABLE_CAVEAT",
    "HEARTBEAT_MARKER",
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
    "render_blocks",
    "render_kickoff_question",
    "render_reply_blocks",
    "render_root",
    "report_subscription",
    "run_socket_listener",
    "slack_state_path",
]

DEFAULT_BOT_TOKEN_ENV = "THE_LOOP_SLACK_BOT_TOKEN"
DEFAULT_APP_TOKEN_ENV = "THE_LOOP_SLACK_APP_TOKEN"
DEFAULT_MAX_CHARS = 1500
#: Slack refuses a section over 3000 characters; the cap never exceeds this.
_SECTION_LIMIT = 2900
_HEADER_LIMIT = 150

READ_MODES: Tuple[str, ...] = ("poll", "socket", "off")

#: How often socket mode re-reads the bound threads on top of the one read it
#: runs at connect (issue-362, R3). The reconcile bounds EVERY cause of a missed
#: envelope — a subscription the app does not carry, a Socket Mode reconnect gap,
#: an acknowledgement that raced a restart — not only this ticket's.
DEFAULT_CATCH_UP_SECONDS = 900
#: A reconcile is a safety net, not a second poll transport: each cycle is one
#: ``conversations.history`` plus one ``conversations.replies`` per bound thread.
MIN_CATCH_UP_SECONDS = 60


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
        "public channel", "channels:history", "message.channels"
    ),
    "private": ConversationKind("private channel", "groups:history", "message.groups"),
    "im": ConversationKind("direct message", "im:history", "message.im"),
    "mpim": ConversationKind("group direct message", "mpim:history", "message.mpim"),
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
    "a mention in any channel", "app_mentions:read", "app_mention"
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
        return "unrecognised — not a Slack conversation id (C…, G… or D…)"
    labels = " or ".join(CONVERSATION_KINDS[kind].label for kind in kinds)
    scopes = " / ".join(CONVERSATION_KINDS[kind].scope for kind in kinds)
    events = " / ".join(CONVERSATION_KINDS[kind].event for kind in kinds)
    return f"{labels} — needs bot scope {scopes} and bot event {events}"


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
        f"channel {channel_id} is a {entry.label}: it needs the bot scope "
        f"{entry.scope} and the bot event {entry.event}, which the-loop's app "
        "manifest did not always carry — a message there is then only read when "
        "the listener starts or reconciles. Run `the-loop channels status "
        "--probe` to check the installed app.",
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
        f"channel {channel_id} is a {labels} and the app lacks the bot scope "
        f"{missing_scopes} — Slack never delivers {missing_events}, so replies and "
        "kickoffs are only read when the listener starts or reconciles. Add the "
        "scope and the event to the Slack app (`the-loop channels manifest` prints "
        "the manifest that carries them, then Reinstall).",
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
        f"the app lacks the bot scope {MENTION.scope} — Slack never delivers "
        f"{MENTION.event}, and since the mention is the address (issue-389) "
        "nothing typed reaches the-loop until it is added: re-import the manifest "
        "(`the-loop channels manifest`), then Reinstall. A direct message with "
        "the bot and a room declared `--listen all` still work.",
    )


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
EVENTS_UNVERIFIABLE_CAVEAT = (
    "not verifiable through the API — Slack exposes no method that lists an "
    "app's event subscriptions, so an app imported from an older manifest reads "
    "as healthy here while hearing nothing. Test them: send the bot a mention "
    "(@the-loop) in the channel and watch the listener answer; if it does not, "
    "re-import the manifest (`the-loop channels manifest`) and Reinstall."
)


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
        events = (
            ((data.get("settings") or {}).get("event_subscriptions") or {}).get(
                "bot_events"
            )
            or []
        )
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
) -> Dict[str, Any]:
    """Ask the installed app what the configured channel is and what it may read.

    Two fixed calls (bugfix §AC4): ``conversations.info`` on the operator's own
    configured channel, and ``auth.test`` for the granted scopes. ``channel_id``
    lets a caller that already resolved the configured value pass the id in; left
    out, a configured **name** is resolved here (PR #376 review). Returns either
    ``{"skipped": why}`` or ``{"kind", "scopes", "findings", "events"}``; it
    never raises, because a diagnostic that fails is not an error (R2.3).
    ``events`` is what the manifest is *expected* to carry (issue-393 R2.1) —
    named, not verified: see :data:`EVENTS_UNVERIFIABLE_CAVEAT`.
    """
    if not config.channel:
        return {"skipped": "no channel is configured"}
    token = os.environ.get(config.bot_token_env) or ""
    if not token:
        return {"skipped": f"no bot token — {config.bot_token_env} is unset"}
    factory = client_factory or build_client
    # `conversations.info` takes an id; the operator may have declared a NAME
    # (PR #376 review). Resolved here so the diagnostic reports on the channel
    # they meant rather than skipping with an opaque API error.
    channel_id = channel_id or config.channel
    if not is_conversation_id(channel_id):
        from .directory import SlackDirectory

        channel_id = SlackDirectory(
            token_env=config.bot_token_env, client_factory=client_factory
        ).conversation_id(channel_id)
        if not channel_id:
            return {
                "skipped": (
                    f"channels.slack.channel is {config.channel!r}, which resolves "
                    "to no channel this bot can see (channels:read / groups:read?)"
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
        + mention_findings(scopes),
        # Expected, not measured (issue-393 R2.1) — the caller prints the caveat.
        "events": expected_bot_events(),
    }


#: Block Kit action ids the-loop renders — and the only ones it acts on.
ACTION_PREFIX = "the-loop:"
#: The button values, which are the words `classify-feedback` already reads.
APPROVE_VALUE = "approved"
CHANGES_VALUE = "changes requested"
_BUTTON_VALUES = (APPROVE_VALUE, CHANGES_VALUE)

#: The command buttons (issue-337): control command → the label a member sees.
#: Fixed; the button's VALUE is the configured keyword, read from
#: ``routing.control.keywords`` so a press is exactly a typed keyword.
COMMAND_BUTTONS: Dict[str, str] = {"execute": "Execute", "start": "Start"}

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
    f"{ACTION_PREFIX}approve": "Approve",
    f"{ACTION_PREFIX}changes": "Request changes",
    KICKOFF_REPO_ACTION: "Repository",
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

#: The checklist's rows that are NOT phases: the hook's ``SURFACE_TOKEN`` and the
#: prefixes of its ``PR_SESSIONS_TOKENS`` / ``MODEL_PREFIX`` / ``EFFORT_PREFIX``
#: rows. Pinned to the hook's by a test, like the marker.
SURFACE_TOKEN = "outer-loop-on-pull-request"
_NON_PHASE_PREFIXES = ("pr-sessions-", "model-", "effort-")

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
        elif token.startswith(_NON_PHASE_PREFIXES):
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
    about = row.about or ("" if row.ticked else "optional — runs only if ticked")
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
        f"{_SELECTION_EMOJI} *Which phases does this work item need?* Untick what "
        "it does not need"
        + (", tick anything optional it does want" if opt_in else "")
        + ", then press *Execute*. The boxes as they stand at that moment are the "
        "graph this item walks."
    )
    blocks: List[Dict[str, Any]] = [{"type": "section", "text": _mrkdwn(lead)}]
    for index in range(0, len(rows.phases), CHECKBOX_LIMIT):
        chunk = rows.phases[index : index + CHECKBOX_LIMIT]
        group = index // CHECKBOX_LIMIT
        label = "*Phases* — ticked ones run" if group == 0 else "*Phases* (continued)"
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
            "text": _mrkdwn("On a pull request in this repository instead"),
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
                "text": _mrkdwn(
                    "*Where does the outer loop happen?* Left unticked, the "
                    "requirements, design, testing plan and task list are iterated "
                    "on the work item itself (the default)."
                ),
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
            "Always run: " + ", ".join(f"`{node}`" for node in rows.always) + "."
        )
    notes.append(
        "Sessions per pull request, model and effort keep this deployment's "
        "defaults from here — to choose them, tick them on GitHub and reply "
        f"`{keyword}` there instead."
    )
    blocks.append({"type": "context", "elements": [_mrkdwn(" ".join(notes))]})
    return blocks


def github_checklist_line(url: str, keyword: str) -> str:
    """What a room that cannot carry the control is told instead (R9.4): the
    checklist is edited on GitHub — linked — and the reply is said there."""
    where = f"<{url}|on GitHub>" if url else "on GitHub"
    say = (
        f"reply `{keyword}` there"
        if keyword
        else "reply with the execute keyword there"
    )
    return f"✍️ This checklist is edited {where}: tick the boxes there, then {say}."


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


def without_clause(text: str, keyword: str) -> Optional[List[str]]:
    """The names and numbers after ``<keyword> without`` in ``text`` — ``[]`` for
    a clause naming nothing, ``None`` when the text carries no such clause."""
    if not keyword or not text:
        return None
    pattern = (
        r"(?<![\w:-])"
        + re.escape(keyword)
        + r"[ \t]+"
        + WITHOUT
        + r"(?![\w-])(?P<rest>[^\n]*)"
    )
    match = re.search(pattern, text, re.IGNORECASE)
    if match is None:
        return None
    items = []
    for raw in re.split(r"[\s,;]+", match.group("rest")):
        item = raw.strip().strip("`'\"“”.:!?()[]{}")
        if item and item.lower() not in ("and", "&", "the", "phase", "phases"):
            items.append(item)
    return items


def _safe_name(item: str) -> str:
    """``item`` as a refusal may echo it: a token, in backticks — anything else
    (prose, markup, a broadcast) is named as *that*, never repeated."""
    return f"`{item}`" if _TOKEN_RE.match(item) and len(item) <= 40 else "that name"


def _offered(rows: SelectionRows) -> str:
    listed = ", ".join(f"{n}. `{row.token}`" for n, row in enumerate(rows.phases, 1))
    return (
        f"The phases you may leave out: {listed} — say `execute without 2, 5` or "
        "`skip <phase>`."
    )


def apply_without(
    rows: SelectionRows, items: Sequence[str], keyword: str
) -> Tuple[str, str]:
    """``(composed reply, refusal)`` for ``execute without <items>`` (R9.3).

    The checklist as it stands, every row kept as ticked, with the named phases
    — by number in checklist order, or by name — unticked; the keyword first,
    the list after, the reply the gate reads over the checklist. **Any item that
    is not one of the offered phases refuses the whole reply** with the reason
    (abuse case 4): a typo, a protected phase, a row that is not a phase — none
    of them may quietly freeze a selection other than the one that was asked.
    """
    if not items:
        return "", f"`{WITHOUT}` needs the phases to leave out. " + _offered(rows)
    drop: set = set()
    for item in items:
        if item.isdigit():
            number = int(item)
            if not 1 <= number <= len(rows.phases):
                return "", (
                    f"There is no phase {number} on this checklist, so nothing was "
                    "recorded. " + _offered(rows)
                )
            drop.add(rows.phases[number - 1].token)
            continue
        row = rows.phase(item)
        if row is None:
            if item.lower() in {node.lower() for node in rows.always}:
                return "", (
                    f"{_safe_name(item)} always runs on this work item and cannot be "
                    "skipped, so nothing was recorded. " + _offered(rows)
                )
            return "", (
                f"{_safe_name(item)} is not a phase this checklist offers, so nothing "
                "was recorded. " + _offered(rows)
            )
        drop.add(row.token)
    lines = [
        _row_line(row.token, row.ticked and row.token not in drop)
        for row in rows.phases
    ]
    if rows.surface is not None:
        lines.append(_row_line(SURFACE_TOKEN, rows.surface.ticked, code=True))
    lines += [_row_line(row.token, row.ticked, code=True) for row in rows.others]
    return f"{keyword}\n\n" + "\n".join(lines), ""


def build_client(token: str):
    """The real SDK client. Module-level so tests substitute it in one place."""
    from slack_sdk import WebClient  # type: ignore[import-not-found]

    return WebClient(token=token)


def slack_state_path(cli_config: Optional[Mapping[str, Any]]) -> Path:
    """Where this channel's bindings live — ``<state.root>/channels/slack.json``."""
    from ..state import layout_from_config

    return Path(layout_from_config(dict(cli_config or {})).channels_dir) / "slack.json"


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
    max_chars: int = DEFAULT_MAX_CHARS
    #: What happens to a text section longer than ``max_chars`` (issue-338):
    #: ``digest`` (the default — the ask first, choices numbered, code and
    #: traces as pointers, cut at a sentence) or ``truncate`` (13.10.0's cut).
    long_messages: str = DEFAULT_DIGEST_MODE
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
    read_interval_seconds: float = 30.0
    #: How often socket mode re-reads the bound threads on top of the connect-time
    #: read (issue-362). ``0`` means connect-only — 16.0.1's behaviour.
    catch_up_seconds: int = DEFAULT_CATCH_UP_SECONDS
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
    def interactive(self) -> bool:
        """Whether an action button can be received: Socket Mode AND the grant
        (decision-103 D5) — a button nobody can receive is worse than none."""
        return self.read_mode == "socket" and "gate.feedback" in self.publish

    @property
    def command_buttons(self) -> bool:
        """Whether an Execute / Start button can be received AND acted on: Socket
        Mode and the ``control.command`` grant (issue-337 R1.4) — the same rule
        :attr:`interactive` applies to the Approve pair."""
        return self.read_mode == "socket" and "control.command" in self.publish

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
        all: Socket Mode, because decision-116 D5 says an interactive payload
        reaches the-loop no other way, and ``work-item.create``, because that is
        what the answer does. No new grant, no new key. In ``poll`` mode the typed
        ``<repo>: `` prefix stays the only route and the refusal is unchanged.
        """
        return self.read_mode == "socket" and self.kickoff_enabled

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
            long_messages = str(section.get("longMessages") or DEFAULT_DIGEST_MODE)
            if long_messages not in DIGEST_MODES:
                logger.warning(
                    "channels.slack.longMessages %r is not one of %s — resolving to %r",
                    long_messages,
                    "/".join(DIGEST_MODES),
                    DEFAULT_DIGEST_MODE,
                )
                long_messages = DEFAULT_DIGEST_MODE
            max_chars = int(section.get("maxChars") or DEFAULT_MAX_CHARS)
            if max_chars < 200:
                logger.warning(
                    "channels.slack.maxChars %d is below 200 — using %d",
                    max_chars,
                    DEFAULT_MAX_CHARS,
                )
                max_chars = DEFAULT_MAX_CHARS
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
                max_chars=min(max_chars, _SECTION_LIMIT),
                long_messages=long_messages,
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
                read_interval_seconds=float(read.get("intervalSeconds") or 30),
                catch_up_seconds=_catch_up_seconds(read.get("catchUpSeconds")),
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


def _control_keywords(raw: Any) -> Tuple[Tuple[str, str], ...]:
    """Every control command with its configured keyword (issue-337) — the
    dispatcher's own parse of ``routing.control``, so a button's value is the
    word the ingress will recognise. Imported at call time, as
    ``inbound._control_config`` imports it."""
    from ..control import COMMANDS, ControlConfig

    try:
        control = ControlConfig.from_mapping(
            dict(raw) if isinstance(raw, Mapping) else {}
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

_TITLES: Dict[str, str] = {
    "session.awaiting_input": "Question from the agent",
    "decision-pending": "Decision needed",
    "phase-approval-pending": "Approval needed",
    "pr-review-pending": "Pull request ready for review",
    "security-sign-off-pending": "Security sign-off needed",
    "conflict-escalated": "Escalated",
    "work-item-complete": "Done",
    "comment.agent": "The agent commented",
    "comment.human": "New comment",
    "standing.started": "Standing session up",
}


#: 13.10.0's cut, kept for the verbose context lines (a detail value is a label,
#: not prose) and for `longMessages: truncate`; the text sections go through
#: :func:`fit` (issue-338).
_cap = truncate


def render_blocks(
    event: Event,
    verbosity: str,
    *,
    interactive: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
    commands: Optional[Mapping[str, str]] = None,
    long_messages: str = DEFAULT_DIGEST_MODE,
    agentic: bool = False,
    execute_keyword: str = "",
) -> List[Dict[str, Any]]:
    """``event`` as Block Kit: header, text, context, and the buttons it earns.

    Strict supersets by verbosity, as :func:`render`: ``quiet`` is the header and
    the link; ``normal`` adds the text; ``verbose`` adds the detail. Buttons: a
    link button whenever the event carries a URL; one **command button** per
    entry of ``commands`` (``command → keyword``, issue-337 — the caller decides
    which message earns which, see :func:`expected_commands` and
    :meth:`SlackChannelConfig.command_buttons_for`); Approve / Request changes
    only for an approval-shaped event **and** only when ``interactive`` (Socket
    Mode with the ``gate.feedback`` grant) — decision-103 D5. Every text section
    — the text, the artifact excerpt — is drawn as mrkdwn and, above
    ``max_chars``, digested or truncated per ``long_messages`` (issue-338,
    :func:`fit`).

    The phase-selection checklist (issue-393 R9) is the one message drawn as a
    **control** rather than a digest: where its Execute button can be pressed
    (``commands`` names ``execute``), its phases and its outer-loop question are
    checkboxes (:func:`selection_control_blocks`) in place of the text; where it
    cannot, the digest stands and a line says the checklist is edited on GitHub
    (R9.4) — ``execute_keyword`` is the configured keyword that line names.
    """
    cap = min(max_chars, _SECTION_LIMIT)

    def section(text: str) -> Dict[str, Any]:
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": fit(text, cap, long_messages, event.url),
            },
        }

    def header() -> Dict[str, Any]:
        title = _TITLES.get(event.event_type, event.event_type)
        who = f" · {event.actor.label}" if event.actor and event.actor.label else ""
        author = event.detail.get("author") if event.detail else ""
        if author and not who:
            who = f" · @{author}"
        text = f"{title}{who} · {event.work_item}"[:_HEADER_LIMIT]
        return {"type": "header", "text": {"type": "plain_text", "text": text}}

    selection = selection_rows(event.text) if is_phase_selection(event) else None
    control_keyword = str((commands or {}).get("execute") or "")
    blocks: List[Dict[str, Any]] = []
    if selection is not None and control_keyword:
        # The control (R9.1, R9.2): the header keeps its place outside a room;
        # the checklist's prose gives way to the boxes, at every verbosity — the
        # boxes are the point of the message, as the summary is of a gate's.
        if not agentic:
            blocks.append(header())
        blocks.extend(selection_control_blocks(selection, control_keyword))
    elif agentic:
        # issue-393 B4/R7, R11: no machine header — the room's binding already
        # says which item this is. One state emoji and the event's own
        # first-person sentence lead instead (voice.room_lead). The text section
        # below is skipped: the lead IS the text, drawn as mrkdwn.
        lead = room_lead(event)
        blocks.append(section(lead))
    else:
        blocks.append(header())
        if verbosity != "quiet" and event.text.strip():
            blocks.append(section(event.text))
    # issue-393 B1/R8: the agent's own summary leads the message when it wrote
    # one — what a reviewer on a phone wants from a gate, in place of the
    # document's first N characters. Rendered at any verbosity (it is the point
    # of a gate message), sanitized (a summary pings no one), and it stands in
    # for the excerpt below; absent, the excerpt is the fallback exactly as before.
    summary = sanitize_summary(getattr(event, "summary", "") or "")
    if summary:
        blocks.append(section(summary))
    if verbosity == "verbose" and event.detail:
        lines = [
            f"*{key}:* {_cap(str(value), 300)}"
            for key, value in event.detail.items()
            if key not in ("excerpt",) and str(value).strip()
        ]
        excerpt = str(event.detail.get("excerpt") or "").strip()
        if excerpt and not summary:
            blocks.append(section(excerpt))
        if lines:
            blocks.append(
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": "\n".join(lines)[:_SECTION_LIMIT]}
                    ],
                }
            )
    elif verbosity == "normal" and event.detail.get("excerpt"):
        blocks.append(section(str(event.detail["excerpt"])))
    if selection is not None and not control_keyword:
        # No control can be posted here (R9.4): never "untick right here" where
        # nothing can be unticked — say where the boxes are, and link them.
        blocks.append(
            {
                "type": "context",
                "elements": [
                    _mrkdwn(github_checklist_line(event.url, execute_keyword))
                ],
            }
        )
    actions: List[Dict[str, Any]] = []
    if event.url:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Open on GitHub"},
                "url": event.url,
                "action_id": f"{ACTION_PREFIX}open",
            }
        )
    actions.extend(_command_buttons(commands))
    if interactive and event.event_type in APPROVAL_EVENTS:
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Approve"},
                "style": "primary",
                "action_id": f"{ACTION_PREFIX}approve",
                "value": APPROVE_VALUE,
            }
        )
        actions.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Request changes"},
                "style": "danger",
                "action_id": f"{ACTION_PREFIX}changes",
                "value": CHANGES_VALUE,
            }
        )
    if actions:
        blocks.append({"type": "actions", "elements": actions})
    return blocks


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
    thread is the conversation" reply and its Start button, issue-337 R1.2)."""
    blocks: List[Dict[str, Any]] = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}}
    ]
    buttons = _command_buttons(commands)
    if buttons:
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
        "title": {"type": "plain_text", "text": "Record a decision"},
        "submit": {"type": "plain_text", "text": "Record"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "decision",
                "label": {"type": "plain_text", "text": "What was decided"},
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
                "label": {"type": "plain_text", "text": "Kind"},
                "element": {
                    "type": "static_select",
                    "action_id": "select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "product, design or tech",
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
                "label": {"type": "plain_text", "text": "Why"},
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
        body = (
            f"{text}\n_Showing {len(shown)} of {len(options)} — for the rest, start "
            "your message with `<repo>: `._"
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
                "placeholder": {"type": "plain_text", "text": "Choose a repository"},
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
    return BUTTON_NAMES.get(action_id, "the button")


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
    lines = [
        f"This thread carries every message about {name} — questions, "
        "approvals, comments — each as a reply."
    ]
    if reading:
        lines.append("Replies here from an authorized member reach it.")
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"the-loop · {work_item}"[:_HEADER_LIMIT],
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
                        "text": {"type": "plain_text", "text": "Open on GitHub"},
                        "url": url,
                        "action_id": f"{ACTION_PREFIX}open",
                    }
                ],
            }
        )
    link = f" — {url}" if url else ""
    return f"the-loop: conversation for {work_item}{link}", blocks


def render_room(
    work_item: str, url: str = "", *, reading: bool = True
) -> Tuple[str, List[Dict[str, Any]]]:
    """The message that opens a **room** conversation (issue-378 R5.1) —
    ``(text, blocks)`` from the ref alone, like :func:`render_root`: the room is
    the work item's own, so it says every update lands here as a message."""
    name = f"<{url}|{work_item}>" if url else f"`{work_item}`"
    lines = [
        f"Every update about {name} — questions, approvals, phases, comments — "
        "is posted in this channel as a message."
    ]
    if reading:
        lines.append("Messages here from an authorized member reach it.")
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"the-loop · {work_item}"[:_HEADER_LIMIT],
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
                        "text": {"type": "plain_text", "text": "Open on GitHub"},
                        "url": url,
                        "action_id": f"{ACTION_PREFIX}open",
                    }
                ],
            }
        )
    link = f" — {url}" if url else ""
    return (
        f"the-loop: every update about {work_item} is posted in this channel{link}",
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

    def subscribes(self, event_type: str) -> bool:
        return event_type in self.config.subscribe

    def wants(self, event_type: str) -> bool:
        """The pre-issue-309 spelling of :meth:`subscribes`."""
        return self.subscribes(event_type)

    def may_publish(self, event_type: str) -> bool:
        return event_type in self.config.publish

    def _client(self):
        token = os.environ.get(self.config.bot_token_env) or ""
        if not token:
            raise ChannelError(
                f"slack: no bot token — export {self.config.bot_token_env} "
                "(an xoxb- bot token with chat:write, and channels.history "
                "for reads)"
            )
        # Resolved at call time so a test's monkeypatch of ``build_client``
        # (and an env var set after construction) is always seen.
        factory = self._client_factory or build_client
        return factory(token)

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
            f"the-loop: {work_item}'s conversation has moved to its declared "
            f"collaboration channel (<#{new[0]}>). Replies here no longer reach "
            "it — continue there.",
            old[0],
        )

    def _room_decision(self, event: Event, agentic: bool) -> "room_policy.Decision":
        """RoomPolicy's decision for ``event`` (issue-393 B5). Always ``post``
        outside an agentic room, so the classic path never changes. Reads the
        delivery memory under the lock, so it is a snapshot the post then acts on.
        """
        if not agentic or not event.work_item:
            return room_policy.Decision(room_policy.POST, rule="not-a-room")
        try:
            with ChannelState.locked(self.state_path, self.stores) as state:
                memory = state.delivery_for(event.work_item)
        except Exception as exc:  # noqa: BLE001 — a memory read never fails a post
            logger.debug("slack: delivery memory read failed (%s); posting", exc)
            return room_policy.Decision(room_policy.POST, rule="no-memory")
        return room_policy.decide(
            event,
            memory,
            is_room=True,
            session_authored=(event.source in ("cli", "session")),
            is_operator_doc=bool((event.detail or {}).get("operatorDoc")),
        )

    def _edit_or_post(self, client, channel_id, ts, text, blocks):
        """chat.update the message at ``ts``; if it is gone/stale, post fresh and
        adopt the new ts (issue-393 B5 error handling — a lost progress message
        never wedges the phase)."""
        try:
            return client.chat_update(
                channel=channel_id, ts=ts, text=text, blocks=blocks
            )
        except Exception as exc:  # noqa: BLE001 — a stale ts is recoverable
            logger.debug("slack: chat.update at %s failed (%s); posting fresh", ts, exc)
            return client.chat_postMessage(channel=channel_id, text=text, blocks=blocks)

    def _remember_delivery(
        self, event: Event, decision: "room_policy.Decision", ts: str
    ) -> None:
        """Merge what the room now holds into the delivery memory. ``@ts`` in a
        decision's ``remember`` is the placeholder for the message just posted —
        resolved to ``ts`` here — and the last event/node are always recorded so
        the dedupe rule can fire next time (issue-393 B5)."""
        node = str(
            (event.detail or {}).get("node") or (event.detail or {}).get("phase") or ""
        )
        changes: Dict[str, Any] = {
            "lastEvent": event.event_type,
            "lastNode": node,
        }
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

    def post(self, event: Event) -> PostResult:
        """Deliver ``event`` as a reply in its work item's thread — opening the
        thread first, once, when none is bound (issue-312 R1).

        The lock covers the decision (is there a thread? open and bind one) and
        not the delivery: the reply is posted after it is released, so a slow
        Slack call never holds the watcher's cursor advance. A reply that fails
        is a :class:`ChannelError` and never a second root (R2.3) — only "no
        binding" opens one. An event with no work item posts top-level, unbound.
        """
        if not self.home_for(event.work_item):
            raise self._no_channel(event.work_item)
        client = self._client()
        bound: Optional[Tuple[str, str]] = None
        if event.work_item:
            with ChannelState.locked(self.state_path, self.stores) as state:
                before = state.conversation_for(event.work_item)
                bound = self._conversation(client, state, event.work_item)
                if before == bound and state.backfilled:
                    state.save(self.state_path)  # a 13.0.1 file, now keyed (R3.4)
        # The agentic voice (issue-393 B4) applies to a work item's own ROOM — a
        # channel-mode binding, `thread_ts == ""` with a channel — and only when
        # the operator has not asked for the classic rendering. A shared channel,
        # a thread, or an unbound post keeps the header rendering.
        in_room = bool(bound and bound[0] and not bound[1])
        agentic = in_room and self.config.room_style == "agentic"

        # issue-393 B5: in an agentic room, RoomPolicy decides whether this event
        # is a new message, an edit of one already there, a threaded reply, or
        # nothing — over the room's delivery memory. Outside a room the decision
        # is always "post", so the classic path is unchanged.
        decision = self._room_decision(event, agentic)
        if decision.action == room_policy.DROP:
            logger.debug(
                "slack: room policy dropped %s for %s (%s)",
                event.event_type,
                event.work_item,
                decision.rule,
            )
            return PostResult(
                channel=self.name, ok=True, thread=(bound and bound[1]) or ""
            )

        blocks = render_blocks(
            event,
            self.config.verbosity,
            interactive=self.config.interactive,
            max_chars=self.config.max_chars,
            commands=self.config.command_buttons_for(*expected_commands(event)),
            long_messages=self.config.long_messages,
            agentic=agentic,
            execute_keyword=self.config.keyword("execute"),
        )
        # The plain-text fallback — what the phone's notification shows — carries
        # the text section as drawn, so a digested message leads with the ask
        # there too (issue-338 R1.5); a short text is the fallback it always was.
        fallback = event
        if len(event.text.strip()) > self.config.max_chars:
            fallback = replace(event, text=_section_text(blocks))
        text = render(fallback, self.config.verbosity)
        channel_id = bound[0] if bound and bound[0] else self.central_channel()
        try:
            if decision.action == room_policy.EDIT and decision.ts:
                response = self._edit_or_post(
                    client, channel_id, decision.ts, text, blocks
                )
            elif decision.action == room_policy.THREAD and decision.ts:
                response = client.chat_postMessage(
                    channel=channel_id,
                    text=text,
                    blocks=blocks,
                    thread_ts=decision.ts,
                )
            else:
                response = client.chat_postMessage(
                    channel=channel_id,
                    text=text,
                    blocks=blocks,
                    # A room conversation has no thread (issue-378): top-level,
                    # never `thread_ts=""`, which Slack refuses.
                    thread_ts=(bound[1] or None) if bound else None,
                )
        except ChannelError:
            raise
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: post failed: {exc}") from None
        # Record what the room now holds, so the next decision reads it (B5).
        if agentic and event.work_item:
            self._remember_delivery(event, decision, str(response.get("ts") or ""))
        if bound and bound[1]:
            return PostResult(channel=self.name, ok=True, thread=bound[1])
        return PostResult(
            channel=self.name, ok=True, thread=str(response.get("ts") or "")
        )

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
            response = client.chat_postMessage(
                channel=room, text=text, blocks=blocks, thread_ts=None
            )
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
            response = client.chat_postMessage(
                channel=room, text=text, blocks=blocks, thread_ts=None
            )
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
        with ``blocks`` when the caller rendered any (its Start button, issue-337)."""
        try:
            self._client().chat_postMessage(
                channel=channel_id or self.central_channel(),
                text=text,
                thread_ts=thread or None,
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
                f"_+{left} more in the thread_" if not more else "_more in the thread_"
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
    ref = reply.work_item or "the work item"
    where = f"<{url}|{ref}>" if url else f"`{ref}`"
    if event_type == "control.command":
        landed = mirrored
        what = (
            f"recorded on {where} — the loop runs it on its next ingress"
            if landed
            else f"not recorded: {error or 'the ledger refused the comment'}"
        )
    elif event_type == "gate.feedback":
        landed = mirrored
        what = (
            f"recorded on {where} as the answer of record — the gate reads it there"
            if landed
            else f"not recorded: {error or 'the ledger refused the comment'}"
        )
    else:  # work-item.reply — a standing session has no record to make
        from ..standing import parse_standing_ref

        standing = bool(parse_standing_ref(reply.work_item))
        landed = delivered and (mirrored or standing)
        if landed:
            what = "delivered to the session" + (
                f" (recorded on {where})" if mirrored else ""
            )
        elif not delivered:
            what = f"not delivered: {error or 'no session could take it'}"
        else:
            what = f"delivered, not recorded: {error or 'the ledger refused it'}"
    name = _button_name(action_id)
    icon = "✅" if landed else "⚠️"
    return landed, f"{icon} *{name}* — pressed by <@{reply.author}> · {what}"


#: Why a repository pick did nothing — fixed words per drop reason (R2.6), and
#: never a repository name: a refused pick names nothing the member did not
#: already see on the question above it.
KICKOFF_REFUSALS: Dict[str, str] = {
    "no-pending-kickoff": (
        "this question is no longer open — it was already answered, or it "
        "expired. Post the message again to file it"
    ),
    "not-your-kickoff": (
        "this question belongs to the member who posted the message, so only "
        "they can answer it"
    ),
    "undeclared-repository": (
        "that is not one of the repositories this question offered, so nothing "
        "was created"
    ),
    "unpublishable-event": (
        "this channel is no longer set up to open work items, so nothing was "
        "created — ask whoever configured the-loop"
    ),
}


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
        said = f"opened {where} — this thread is now its conversation"
        landed = True
    elif what in KICKOFF_REFUSALS:
        said = KICKOFF_REFUSALS[what]
        landed = False
    else:
        problem = str(outcome.get("error") or "").strip()
        said = f"nothing was opened: {problem or 'the ledger refused it'}"
        landed = False
    return (
        landed,
        f"{'✅' if landed else '⚠️'} *{_button_name(action_id)}* — "
        f"pressed by <@{reply.author}> · {said}",
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


def report_subscription(config: "SlackChannelConfig") -> None:
    """Probe the installed app once and log what it cannot receive (R2.4).

    Best-effort in both directions: a probe that cannot run is an ``info`` line,
    a probe that raises is swallowed, and neither keeps the listener from
    listening. The words are :func:`subscription_findings`' own, so an operator
    reads the same sentence here and in ``the-loop channels status --probe``.
    """
    try:
        result = probe_subscription(config)
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

    from . import commands, inbound

    frozen_config = dict(cli_config or {})

    def handle(client, request) -> None:
        if request.type not in ("events_api", "interactive", "slash_commands"):
            # issue-393 B3/R2.4: an ignored envelope is logged, never dropped in
            # silence. When two listeners share one app Slack splits events
            # across the connections, and half of everything lands on the
            # instance that does not own the room — a debug line per ignored
            # envelope is the one thread an operator can pull to see it.
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
            if request.type == "slash_commands":
                commands.handle_slash_command(payload, frozen_config)
                return
            if request.type == "interactive":
                kind = payload.get("type")
                if kind == "block_actions":
                    inbound.handle_socket_action(payload, frozen_config)
                elif kind == "message_action":
                    # A shortcut is exactly the typed mention (issue-389 R6.2).
                    inbound.handle_message_action(payload, frozen_config)
                elif kind == "view_submission":
                    # The ack above already closed the modal (R6.1).
                    inbound.handle_view_submission(payload, frozen_config)
                else:
                    logger.debug(
                        "slack: ignoring an interactive payload of kind %r "
                        "(handled: block_actions, message_action, view_submission)",
                        kind,
                    )
                return
            event = payload.get("event") or {}
            event_type = event.get("type")
            if event_type == "app_mention":
                # The mention is the address (issue-389 R1.1).
                inbound.handle_socket_event(event, frozen_config, addressed=True)
                return
            if event_type != "message":
                logger.debug(
                    "slack: ignoring an events_api event of type %r in channel %r "
                    "(handled: app_mention, message)",
                    event_type,
                    event.get("channel") or event.get("channel_id") or "",
                )
                return
            nonce = heartbeat_nonce(event)
            if nonce:
                # The doctor's own heartbeat (issue-393 F2 / R2.2): the receipt
                # is the whole point — recorded where `the-loop doctor slack`
                # reads it back, and never handed to the pipeline as input.
                eventlog.emit(
                    "channel.heartbeat",
                    channel="slack",
                    channel_id=str(event.get("channel") or ""),
                    ts=str(event.get("ts") or ""),
                    nonce=nonce,
                )
                return
            inbound.handle_socket_event(event, frozen_config, addressed=False)
        except Exception:  # one bad message never ends the listener
            logger.exception("slack: socket event handling raised; continuing")

    client = SocketModeClient(app_token=app_token, web_client=build_client(bot_token))
    client.socket_mode_request_listeners.append(handle)
    client.connect()
    logger.info(
        "slack: Socket Mode connected — listening for mentions, button presses, "
        "shortcuts and /the-loop commands"
    )
    report_subscription(config)
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
                due = time.monotonic() + interval
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        logger.info("slack: Socket Mode listener stopped")
    return 0
