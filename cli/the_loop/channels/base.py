"""The channel contract: events, rendering, and loading from config."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Protocol, Tuple

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DEFAULT_EVENTS",
    "VERBOSITIES",
    "Channel",
    "ChannelError",
    "InboundReply",
    "OutboundEvent",
    "PostResult",
    "load_channels",
    "render",
]

#: The event types a channel subscribes to when its config names none. The ask
#: is the one conversation-shaped event the loop emits today (issue-208); a
#: channel that wants more opts in per event type.
DEFAULT_EVENTS: Tuple[str, ...] = ("session.awaiting_input",)

VERBOSITIES: Tuple[str, ...] = ("quiet", "normal", "verbose")


class ChannelError(RuntimeError):
    """A channel operation could not be performed. Callers record, never crash."""


@dataclass(frozen=True)
class OutboundEvent:
    """One thing the-loop wants to say, channel-neutral.

    ``text`` is the message itself (the question); ``url`` is the human's link
    to where it lives on the source of truth; ``detail`` is context a verbose
    channel may render. Channels receive this, never the raw event-log record.
    """

    event_type: str
    work_item: str
    text: str
    url: str = ""
    detail: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class PostResult:
    """What one channel did with one outbound event."""

    channel: str
    ok: bool
    error: str = ""
    thread: str = ""  # provider-specific conversation handle (Slack: thread ts)


@dataclass(frozen=True)
class InboundReply:
    """One message that arrived through a channel, normalized.

    ``work_item`` is resolved from the channel's own bindings — empty means the
    message could not be attributed to a conversation the-loop started, and the
    pipeline drops it as ``unmapped``. ``is_bot`` flags messages authored by any
    bot (the-loop's own included), dropped before authorization.
    """

    channel: str
    work_item: str
    author: str
    text: str
    thread: str
    ts: str
    is_bot: bool = False


class Channel(Protocol):
    """Every conversation surface looks the same to the loop."""

    name: str

    def wants(self, event_type: str) -> bool: ...

    def post(self, event: OutboundEvent) -> PostResult: ...


def render(event: OutboundEvent, verbosity: str) -> str:
    """``event`` as one message at ``verbosity`` (R2.2).

    The levels are strict supersets — quiet ⊂ normal ⊂ verbose — so turning
    verbosity down never changes the words, only how many of them there are.
    An unknown verbosity renders ``normal``: the safe middle, never silence.
    """
    link = f" — {event.url}" if event.url else ""
    quiet = f"the-loop: {event.event_type} on {event.work_item}{link}"
    if verbosity == "quiet":
        return quiet
    normal = f"{quiet}\n\n{event.text}"
    if verbosity != "verbose":
        return normal
    detail = "\n".join(f"{key}: {value}" for key, value in event.detail.items())
    return f"{normal}\n\n{detail}" if detail else normal


def load_channels(
    cli_config: Optional[Mapping[str, Any]], client_factory=None
) -> List[Channel]:
    """The enabled channels from the CLI config's ``channels`` section.

    Fail closed at every step (R6.1): no section, a disabled channel or a
    malformed one yields nothing — a malformed one loudly, because silence
    here would read as "configured and quiet" to the operator who wrote it.
    """
    config = dict(cli_config or {})
    section = config.get("channels")
    if not section:
        return []
    if not isinstance(section, Mapping):
        logger.error(
            "channels: the config section is not a mapping — every channel "
            "is disabled (fail closed)"
        )
        return []

    from .slack import SlackBotChannel, SlackChannelConfig, slack_state_path

    slack_config = SlackChannelConfig.from_mapping(config)
    if not slack_config.enabled:
        return []
    return [
        SlackBotChannel(
            slack_config, slack_state_path(config), client_factory=client_factory
        )
    ]
