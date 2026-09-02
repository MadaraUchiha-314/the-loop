"""The Slack bot channel — writes and reads through the official SDK (D5, D7).

Distinct from :mod:`the_loop.graph.integrations`: that layer carries the-loop's own
one-shot calls. This is a **bot**: a token with an identity, able to post into a
channel, thread a conversation per work item, read the replies back — and, since
issue-309, render every event with Block Kit, carry Approve / Request changes
buttons where a press can be received, and open a work item from a top-level
message when granted.

Tokens are read from the environment **at call time** (the ``_SlackBase._url()``
rule: a provider outlives many transitions and must see the environment as it
is), named by config, never held as values (R3.1).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

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
    "CHANGES_VALUE",
    "DEFAULT_APP_TOKEN_ENV",
    "DEFAULT_BOT_TOKEN_ENV",
    "DEFAULT_MAX_CHARS",
    "READ_MODES",
    "SlackBotChannel",
    "SlackChannelConfig",
    "build_client",
    "kickoff_cursor_key",
    "render_blocks",
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
            )
        except (TypeError, ValueError) as exc:
            logger.error(
                "channels.slack: malformed section (%s) — the channel is "
                "disabled (fail closed)",
                exc,
            )
            return cls()


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
) -> List[Dict[str, Any]]:
    """``event`` as Block Kit: header, text, context, and the buttons it earns.

    Strict supersets by verbosity, as :func:`render`: ``quiet`` is the header and
    the link; ``normal`` adds the text; ``verbose`` adds the detail. Buttons: a
    link button whenever the event carries a URL; Approve / Request changes only
    for an approval-shaped event **and** only when ``interactive`` (Socket Mode
    with the ``gate.feedback`` grant) — decision-103 D5.
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
        if not self.config.channel:
            raise ChannelError(
                "slack: no channel id configured — set channels.slack.channel "
                "to the channel the bot posts into (C…)"
            )
        client = self._client()
        state = ChannelState.load(self.state_path)
        bound = state.thread_for(event.work_item) if event.work_item else None
        text = render(event, self.config.verbosity)
        blocks = render_blocks(
            event,
            self.config.verbosity,
            interactive=self.config.interactive,
            max_chars=self.config.max_chars,
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
        ts = str(response.get("ts") or "")
        if bound:
            return PostResult(channel=self.name, ok=True, thread=bound[1])
        if ts and event.work_item:
            state.bind(ts, event.work_item, self.config.channel)
            state.save(self.state_path)
        return PostResult(channel=self.name, ok=True, thread=ts)

    def say(self, thread: str, text: str, channel_id: str = "") -> bool:
        """A plain reply into ``thread`` — the kickoff's "here is your issue"."""
        try:
            self._client().chat_postMessage(
                channel=channel_id or self.config.channel,
                text=text,
                thread_ts=thread or None,
            )
        except Exception as exc:  # best-effort; the issue exists either way
            logger.warning("slack: could not reply in thread %s: %s", thread, exc)
            return False
        return True

    def bind(self, thread: str, work_item: str, channel_id: str = "") -> None:
        """Bind ``thread`` to ``work_item`` — a kickoff's thread to its new issue."""
        state = ChannelState.load(self.state_path)
        state.bind(thread, work_item, channel_id or self.config.channel)
        state.save(self.state_path)

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
            state.advance(key, newest)
            state.save(self.state_path)
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
        """Persist that everything in ``thread`` up to ``ts`` was processed."""
        state = ChannelState.load(self.state_path)
        state.advance(thread, ts)
        state.save(self.state_path)

    def advance_kickoff(self, ts: str) -> None:
        self.advance(kickoff_cursor_key(self.config.channel), ts)


def _ts_key(ts: str) -> Tuple[int, Any]:
    """Slack ts ordering that survives a non-numeric value."""
    try:
        return (0, float(ts))
    except ValueError:
        return (1, ts)


# -- Socket Mode (R4.2) ----------------------------------------------------------


def run_socket_listener(
    cli_config: Optional[Mapping[str, Any]],
    stop_event: Optional[threading.Event] = None,
) -> int:
    """Receive replies, button presses and kickoffs push-fashion until stopped —
    ``the-loop channels listen``.

    Uses the SDK's built-in Socket Mode client (stdlib WebSocket — no extra
    dependency) over an *outbound* connection, so nothing is exposed. Every
    accepted envelope is acknowledged, and everything converges on the same
    pipeline the poll transport uses (:mod:`.inbound`).
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

    from . import inbound

    frozen_config = dict(cli_config or {})

    def handle(client, request) -> None:
        if request.type not in ("events_api", "interactive"):
            return
        client.send_socket_mode_response(
            SocketModeResponse(envelope_id=request.envelope_id)
        )
        payload = request.payload or {}
        try:
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
    logger.info("slack: Socket Mode connected — listening for thread replies")
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
