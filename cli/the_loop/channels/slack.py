"""The Slack bot channel — writes and reads through the official SDK (D5, D7).

Distinct from :mod:`the_loop.graph.integrations.slack`, deliberately: that is
the *incoming webhook* — a bearer URL for one channel, write-only, used by the
graph's ``notify`` hook. This is a **bot**: a token with an identity, able to
post into a channel, thread a conversation per work item, and read the replies
back. The two coexist (R3.4); an operator may run either or both.

Tokens are read from the environment **at call time** (the
``_SlackBase._url()`` rule: a provider outlives many transitions and must see
the environment as it is), named by config, never held as values (R3.1).
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Mapping, Optional, Tuple

from .base import (
    DEFAULT_EVENTS,
    VERBOSITIES,
    ChannelError,
    InboundReply,
    OutboundEvent,
    PostResult,
    render,
)
from .state import ChannelState

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DEFAULT_APP_TOKEN_ENV",
    "DEFAULT_BOT_TOKEN_ENV",
    "READ_MODES",
    "SlackBotChannel",
    "SlackChannelConfig",
    "build_client",
    "run_socket_listener",
    "slack_state_path",
]

DEFAULT_BOT_TOKEN_ENV = "THE_LOOP_SLACK_BOT_TOKEN"
DEFAULT_APP_TOKEN_ENV = "THE_LOOP_SLACK_APP_TOKEN"

READ_MODES: Tuple[str, ...] = ("poll", "socket", "off")


def build_client(token: str):
    """The real SDK client. Module-level so tests substitute it in one place."""
    from slack_sdk import WebClient  # type: ignore[import-not-found]

    return WebClient(token=token)


def slack_state_path(cli_config: Optional[Mapping[str, Any]]) -> Path:
    """Where this channel's bindings live — ``<state.root>/channels/slack.json``."""
    from ..state import layout_from_config

    return Path(layout_from_config(dict(cli_config or {})).channels_dir) / "slack.json"


@dataclass(frozen=True)
class SlackChannelConfig:
    """The parsed ``channels.slack`` CLI-config section. Frozen; fail-closed."""

    enabled: bool = False
    bot_token_env: str = DEFAULT_BOT_TOKEN_ENV
    app_token_env: str = DEFAULT_APP_TOKEN_ENV
    channel: str = ""
    events: Tuple[str, ...] = DEFAULT_EVENTS
    verbosity: str = "normal"
    authorized_users: Tuple[str, ...] = ()
    read_mode: str = "poll"
    read_interval_seconds: float = 30.0

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
            events = tuple(str(e) for e in (section.get("events") or DEFAULT_EVENTS))
            # Warn against the common catalog (PR #267 review): an allow-list
            # typo otherwise fails SILENTLY — the event just never arrives.
            # Unknown names are kept, not refused: a custom process graph may
            # fire a custom notify event, and its subscription must work.
            from .events import SUBSCRIBABLE_EVENTS

            unknown = [e for e in events if e not in SUBSCRIBABLE_EVENTS]
            if unknown:
                logger.warning(
                    "channels.slack.events names %s, not in the subscribable-"
                    "event catalog (%s) — kept, but nothing shipped broadcasts "
                    "them; see `the-loop channels status` or "
                    "docs/config/cli/channels-options for the vocabulary",
                    ", ".join(repr(e) for e in unknown),
                    ", ".join(SUBSCRIBABLE_EVENTS),
                )
            return cls(
                enabled=bool(section.get("enabled", False)),
                bot_token_env=str(section.get("botTokenEnv") or DEFAULT_BOT_TOKEN_ENV),
                app_token_env=str(section.get("appTokenEnv") or DEFAULT_APP_TOKEN_ENV),
                channel=str(section.get("channel") or ""),
                events=events,
                verbosity=verbosity,
                authorized_users=tuple(
                    str(user) for user in (section.get("authorizedUsers") or []) if user
                ),
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

    def wants(self, event_type: str) -> bool:
        return event_type in self.config.events

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

    def post(self, event: OutboundEvent) -> PostResult:
        if not self.config.channel:
            raise ChannelError(
                "slack: no channel id configured — set channels.slack.channel "
                "to the channel the bot posts into (C…)"
            )
        client = self._client()
        state = ChannelState.load(self.state_path)
        bound = state.thread_for(event.work_item) if event.work_item else None
        text = render(event, self.config.verbosity)
        try:
            response = client.chat_postMessage(
                channel=self.config.channel,
                text=text,
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
            try:
                response = client.conversations_replies(
                    channel=info.get("channel") or self.config.channel,
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
                    )
                )
        return replies

    def advance(self, thread: str, ts: str) -> None:
        """Persist that everything in ``thread`` up to ``ts`` was processed."""
        state = ChannelState.load(self.state_path)
        state.advance(thread, ts)
        state.save(self.state_path)


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
    """Receive replies push-fashion until stopped — ``the-loop channels listen``.

    Uses the SDK's built-in Socket Mode client (stdlib WebSocket — no extra
    dependency) over an *outbound* connection, so nothing is exposed. Every
    accepted envelope is acknowledged, and message events converge on the same
    pipeline the poll transport uses (:func:`~.inbound.handle_socket_event`).
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
        if request.type != "events_api":
            return
        client.send_socket_mode_response(
            SocketModeResponse(envelope_id=request.envelope_id)
        )
        event = (request.payload or {}).get("event") or {}
        if event.get("type") != "message":
            return
        try:
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
