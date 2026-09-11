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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .. import eventlog
from ..identity import Principal, ids_for, parse_authorized_users
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
from .events import APPROVAL_EVENTS, PUBLISHABLE_EVENTS, SUBSCRIBABLE_EVENTS
from .state import ChannelState

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "ACTION_PREFIX",
    "APPROVE_VALUE",
    "BUTTON_NAMES",
    "CHANGES_VALUE",
    "COMMAND_BUTTONS",
    "DEFAULT_APP_TOKEN_ENV",
    "DEFAULT_BOT_TOKEN_ENV",
    "DEFAULT_MAX_CHARS",
    "DEFAULT_REACTIONS",
    "PHASE_SELECTION_MARKER",
    "REACTION_STATES",
    "READ_MODES",
    "SlackBotChannel",
    "SlackChannelConfig",
    "SlackReactionConfig",
    "build_client",
    "catch_up",
    "expected_commands",
    "kickoff_cursor_key",
    "render_blocks",
    "render_reply_blocks",
    "render_root",
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
#: action_id → the name the press outcome line uses — never the payload's own
#: button text (R2.6).
BUTTON_NAMES: Dict[str, str] = {
    f"{ACTION_PREFIX}approve": "Approve",
    f"{ACTION_PREFIX}changes": "Request changes",
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
    kickoff_repo: str = ""
    kickoff_labels: Tuple[str, ...] = ()
    #: The people of `routing.authorizedUsers`, and their Slack ids (issue-309).
    principals: Tuple[Principal, ...] = ()
    authorized_users: Tuple[str, ...] = ()
    read_mode: str = "poll"
    read_interval_seconds: float = 30.0
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
        return bool(
            self.enabled
            and self.channel
            and self.kickoff_repo
            and "work-item.create" in self.publish
        )

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
            return cls(
                enabled=bool(section.get("enabled", False)),
                bot_token_env=str(section.get("botTokenEnv") or DEFAULT_BOT_TOKEN_ENV),
                app_token_env=str(section.get("appTokenEnv") or DEFAULT_APP_TOKEN_ENV),
                channel=str(section.get("channel") or ""),
                subscribe=subscribe,
                publish=publish,
                verbosity=verbosity,
                max_chars=min(max_chars, _SECTION_LIMIT),
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


def _cap(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    rest = len(text) - max_chars
    return text[:max_chars].rstrip() + f"\n… ({rest} more characters — see the link)"


def render_blocks(
    event: Event,
    verbosity: str,
    *,
    interactive: bool = False,
    max_chars: int = DEFAULT_MAX_CHARS,
    commands: Optional[Mapping[str, str]] = None,
) -> List[Dict[str, Any]]:
    """``event`` as Block Kit: header, text, context, and the buttons it earns.

    Strict supersets by verbosity, as :func:`render`: ``quiet`` is the header and
    the link; ``normal`` adds the text; ``verbose`` adds the detail. Buttons: a
    link button whenever the event carries a URL; one **command button** per
    entry of ``commands`` (``command → keyword``, issue-337 — the caller decides
    which message earns which, see :func:`expected_commands` and
    :meth:`SlackChannelConfig.command_buttons_for`); Approve / Request changes
    only for an approval-shaped event **and** only when ``interactive`` (Socket
    Mode with the ``gate.feedback`` grant) — decision-103 D5.
    """
    title = _TITLES.get(event.event_type, event.event_type)
    who = f" · {event.actor.label}" if event.actor and event.actor.label else ""
    author = event.detail.get("author") if event.detail else ""
    if author and not who:
        who = f" · @{author}"
    header = f"{title}{who} · {event.work_item}"[:_HEADER_LIMIT]
    blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header}}
    ]
    if verbosity != "quiet" and event.text.strip():
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _cap(event.text, min(max_chars, _SECTION_LIMIT)),
                },
            }
        )
    if verbosity == "verbose" and event.detail:
        lines = [
            f"*{key}:* {_cap(str(value), 300)}"
            for key, value in event.detail.items()
            if key not in ("excerpt",) and str(value).strip()
        ]
        excerpt = str(event.detail.get("excerpt") or "").strip()
        if excerpt:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": _cap(excerpt, min(max_chars, _SECTION_LIMIT)),
                    },
                }
            )
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
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _cap(
                        str(event.detail["excerpt"]), min(max_chars, _SECTION_LIMIT)
                    ),
                },
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
        self._client_factory = client_factory
        self._own_user: Optional[str] = None

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

    def post(self, event: Event) -> PostResult:
        """Deliver ``event`` as a reply in its work item's thread — opening the
        thread first, once, when none is bound (issue-312 R1).

        The lock covers the decision (is there a thread? open and bind one) and
        not the delivery: the reply is posted after it is released, so a slow
        Slack call never holds the watcher's cursor advance. A reply that fails
        is a :class:`ChannelError` and never a second root (R2.3) — only "no
        binding" opens one. An event with no work item posts top-level, unbound.
        """
        if not self.config.channel:
            raise ChannelError(
                "slack: no channel id configured — set channels.slack.channel "
                "to the channel the bot posts into (C…)"
            )
        client = self._client()
        bound: Optional[Tuple[str, str]] = None
        if event.work_item:
            with ChannelState.locked(self.state_path) as state:
                bound = state.thread_for(event.work_item)
                if not bound:
                    bound = self._open_thread(client, state, event.work_item)
                elif state.backfilled:
                    state.save(self.state_path)  # a 13.0.1 file, now keyed (R3.4)
        text = render(event, self.config.verbosity)
        blocks = render_blocks(
            event,
            self.config.verbosity,
            interactive=self.config.interactive,
            max_chars=self.config.max_chars,
            commands=self.config.command_buttons_for(*expected_commands(event)),
        )
        try:
            response = client.chat_postMessage(
                channel=bound[0] if bound and bound[0] else self.config.channel,
                text=text,
                blocks=blocks,
                thread_ts=bound[1] if bound else None,
            )
        except ChannelError:
            raise
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: post failed: {exc}") from None
        if bound:
            return PostResult(channel=self.name, ok=True, thread=bound[1])
        return PostResult(
            channel=self.name, ok=True, thread=str(response.get("ts") or "")
        )

    def open(self, work_item: str) -> PostResult:
        """Open ``work_item``'s thread now — the root alone, no reply — or
        return the one it already has (issue-317 R1.2, R1.3).

        What the dispatcher's spawn path calls, through the bus, the moment a
        start is accepted: the same lock, root, bind and save as the lazy path
        in :meth:`post`, with ``origin="start"`` on the record, and nothing
        posted for a work item that is already bound. The refusals are
        :meth:`post`'s — no channel id, no token — raised before any call; a
        root that fails to post raises and binds nothing, so the next event
        opens the thread lazily as before (R1.5).
        """
        if not self.config.channel:
            raise ChannelError(
                "slack: no channel id configured — set channels.slack.channel "
                "to the channel the bot posts into (C…)"
            )
        client = self._client()
        with ChannelState.locked(self.state_path) as state:
            bound = state.thread_for(work_item)
            if not bound:
                bound = self._open_thread(client, state, work_item, origin="start")
            elif state.backfilled:
                state.save(self.state_path)  # a 13.0.1 file, now keyed (R3.4)
        return PostResult(channel=self.name, ok=True, thread=bound[1])

    def _open_thread(
        self, client, state: ChannelState, work_item: str, *, origin: str = "event"
    ) -> Tuple[str, str]:
        """Post the root for ``work_item``, bind it, save — inside the caller's
        lock. Returns ``(channel_id, thread_ts)``. A root that fails to post
        binds nothing, so the next event tries again. ``origin`` is how the
        record and ``channel.thread_opened`` say the thread came to be:
        ``event`` (the lazy path) or ``start`` (issue-317)."""
        url = _work_item_url(work_item)
        text, blocks = render_root(
            work_item, url, reading=self.config.read_mode != "off"
        )
        try:
            response = client.chat_postMessage(
                channel=self.config.channel, text=text, blocks=blocks, thread_ts=None
            )
        except Exception as exc:  # SlackApiError and transport errors alike
            raise ChannelError(f"slack: could not open a thread: {exc}") from None
        ts = str(response.get("ts") or "")
        if not ts:
            raise ChannelError("slack: could not open a thread: no ts returned")
        permalink = ""
        try:
            permalink = str(
                client.chat_getPermalink(
                    channel=self.config.channel, message_ts=ts
                ).get("permalink")
                or ""
            )
        except Exception as exc:  # noqa: BLE001 — a nicety; the binding stands (A3)
            logger.debug("slack: no permalink for thread %s: %s", ts, exc)
        state.bind(
            ts, work_item, self.config.channel, origin=origin, permalink=permalink
        )
        state.save(self.state_path)
        eventlog.emit(
            "channel.thread_opened",
            channel=self.name,
            work_item=work_item,
            thread=ts,
            channel_id=self.config.channel,
            origin=origin,
        )
        return (self.config.channel, ts)

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
                channel=channel_id or self.config.channel,
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
        with ChannelState.locked(self.state_path) as state:
            state.bind(
                thread, work_item, channel_id or self.config.channel, origin=origin
            )
            state.save(self.state_path)
        eventlog.emit(
            "channel.thread_opened",
            channel=self.name,
            work_item=work_item,
            thread=thread,
            channel_id=channel_id or self.config.channel,
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
        channel_id = reply.channel_id or self.config.channel
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
        channel_id = reply.channel_id or self.config.channel
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

    def fetch_replies(self) -> List[InboundReply]:
        """Every not-yet-processed reply in every bound thread (R4.4, R4.6).

        Only bound threads are queried — the bot structurally cannot read the
        channel at large through this path. The cursor filter is applied
        client-side (strictly newer than the last processed ts), so the exact
        inclusivity semantics of the API's ``oldest`` never matter.
        """
        state = ChannelState.load(self.state_path)
        if not state.threads:
            return []
        client = self._client()
        own_user = self._own_user_id(client)
        replies: List[InboundReply] = []
        for thread, info in state.threads.items():
            cursor = state.cursor(thread)
            channel_id = info.get("channel") or self.config.channel
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
        state = ChannelState.load(self.state_path)
        key = kickoff_cursor_key(self.config.channel)
        cursor = state.cursors.get(key, "")
        client = self._client()
        try:
            response = client.conversations_history(
                channel=self.config.channel, oldest=cursor or None
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
                    channel_id=self.config.channel,
                )
            )
        return found

    def advance(self, thread: str, ts: str) -> None:
        """Persist that everything in ``thread`` up to ``ts`` was processed —
        under the lock, so a cursor never overwrites a binding written beside it."""
        with ChannelState.locked(self.state_path) as state:
            state.advance(thread, ts)
            state.save(self.state_path)

    def advance_kickoff(self, ts: str) -> None:
        self.advance(kickoff_cursor_key(self.config.channel), ts)


def _press_line(
    reply: InboundReply, action_id: str, outcome: Mapping[str, Any]
) -> Tuple[bool, str]:
    """``(landed, line)`` for a processed press, from fixed words (R2.6)."""
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
    name = BUTTON_NAMES.get(action_id, "the button")
    icon = "✅" if landed else "⚠️"
    return landed, f"{icon} *{name}* — pressed by <@{reply.author}> · {what}"


def _press_blocks(
    message: Mapping[str, Any], landed: bool, line: str
) -> List[Dict[str, Any]]:
    """The pressed message's blocks, rebuilt: an ``actions`` block keeps its link
    (``url``) elements only once the press landed — every element while it did
    not — and is dropped when nothing remains; the outcome line closes the
    message. A message with no blocks is its text."""
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


def run_socket_listener(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: Optional[threading.Event] = None,
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
                if payload.get("type") == "block_actions":
                    inbound.handle_socket_action(payload, frozen_config)
                return
            event = payload.get("event") or {}
            if event.get("type") != "message":
                return
            inbound.handle_socket_event(event, frozen_config)
        except Exception:  # one bad message never ends the listener
            logger.exception("slack: socket event handling raised; continuing")

    client = SocketModeClient(app_token=app_token, web_client=build_client(bot_token))
    client.socket_mode_request_listeners.append(handle)
    client.connect()
    logger.info(
        "slack: Socket Mode connected — listening for thread replies, button "
        "presses and /the-loop commands"
    )
    catch_up(frozen_config)
    waiter = stop_event or threading.Event()
    try:
        while not waiter.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        client.close()
        logger.info("slack: Socket Mode listener stopped")
    return 0
