"""The channel contract: the event, the results, and loading from config.

Since issue-309 (decision-103) a channel is a **peer on one event bus**: it
``subscribes`` to the event types it receives, ``may_publish`` the ones a message on
it is granted to become, ``post``s an event it rendered itself — and one channel, the
**ledger**, additionally ``record``s every event that originated elsewhere. The bus
(:mod:`.bus`) is the only caller of a channel; nothing else in the-loop posts to one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Protocol, Tuple

from ..identity import Principal

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "DEFAULT_EVENTS",
    "DEFAULT_PUBLISH",
    "LEDGERS",
    "VERBOSITIES",
    "Channel",
    "ChannelError",
    "Event",
    "InboundReply",
    "Ledger",
    "OutboundEvent",
    "PostResult",
    "PublishResult",
    "ledger_name",
    "load_channels",
    "load_ledger",
    "render",
]

#: The event types a channel subscribes to when its config names none. The ask
#: is the one conversation-shaped event the loop emitted first (issue-208); a
#: channel that wants more opts in per event type.
DEFAULT_EVENTS: Tuple[str, ...] = ("session.awaiting_input",)

#: The grant a channel holds when its config names none: a message is input to
#: the waiting session and nothing more — 12.1.0's behaviour, exactly.
DEFAULT_PUBLISH: Tuple[str, ...] = ("work-item.reply",)

VERBOSITIES: Tuple[str, ...] = ("quiet", "normal", "verbose")

#: The ledgers this release ships. The key is the extension point the owner named;
#: a second value is a second provider (decision-103 D8).
LEDGERS: Tuple[str, ...] = ("github",)


class ChannelError(RuntimeError):
    """A channel operation could not be performed. Callers record, never crash."""


@dataclass(frozen=True)
class Event:
    """One thing that happened, channel-neutral — the only currency of the bus.

    ``text`` is the message itself; ``url`` the human's link to where it lives on
    the ledger; ``detail`` context a verbose channel may render; ``source`` the
    channel (or ``loop``/``cli``) it came from — the bus never posts an event back
    to its source; ``actor`` the person who caused it, resolved from config.
    """

    event_type: str
    work_item: str
    text: str
    url: str = ""
    detail: Mapping[str, str] = field(default_factory=dict)
    source: str = "loop"
    actor: Optional[Principal] = None


#: The pre-issue-309 name, kept so embedders and the standing-session module read on.
OutboundEvent = Event


@dataclass(frozen=True)
class PostResult:
    """What one channel did with one event."""

    channel: str
    ok: bool
    error: str = ""
    thread: str = ""  # provider-specific conversation handle (Slack: thread ts)
    url: str = ""  # where the record lives, when the channel can say (the ledger)
    ref: str = ""  # a work item the record created (`work-item.create`)


@dataclass(frozen=True)
class PublishResult:
    """What the bus did with one event: the ledger's record, then the fan-out."""

    record: Optional[PostResult] = None
    posts: List[PostResult] = field(default_factory=list)

    @property
    def recorded(self) -> bool:
        return bool(self.record and self.record.ok)

    @property
    def delivered(self) -> bool:
        return any(post.ok for post in self.posts)


@dataclass(frozen=True)
class InboundReply:
    """One message that arrived through a channel, normalized.

    ``work_item`` is resolved from the channel's own bindings — empty means the
    message could not be attributed to a conversation the-loop started, and the
    pipeline drops it as ``unmapped`` (unless it is a top-level message on a
    channel holding the ``work-item.create`` grant, which ``top_level`` marks).
    ``is_bot`` flags messages authored by any bot (the-loop's own included),
    dropped before authorization.
    """

    channel: str
    work_item: str
    author: str
    text: str
    thread: str
    ts: str
    is_bot: bool = False
    top_level: bool = False
    channel_id: str = ""


class Channel(Protocol):
    """Every conversation surface looks the same to the bus."""

    name: str

    def subscribes(self, event_type: str) -> bool: ...

    def may_publish(self, event_type: str) -> bool: ...

    def post(self, event: Event) -> PostResult: ...


class Ledger(Protocol):
    """The channel of record: a channel that also writes down what others said."""

    name: str

    def record(self, event: Event) -> PostResult: ...


def render(event: Event, verbosity: str) -> str:
    """``event`` as one plain-text message at ``verbosity`` (R2.2, issue-245).

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


def ledger_name(cli_config: Optional[Mapping[str, Any]]) -> str:
    """The configured ledger — ``github`` by default; an unknown name resolves
    to ``github`` with an error logged (load refuses it; this is the runtime's
    belt and braces, and it never resolves to *no* ledger)."""
    section = (dict(cli_config or {}).get("channels") or {}) if cli_config else {}
    name = (
        str((section or {}).get("ledger") or "github")
        if isinstance(section, Mapping)
        else "github"
    )
    if name not in LEDGERS:
        logger.error(
            "channels.ledger %r is not one of %s — recording on 'github'",
            name,
            "/".join(LEDGERS),
        )
        return "github"
    return name


def load_ledger(cli_config: Optional[Mapping[str, Any]]) -> Ledger:
    """The ledger channel. Always exists: GitHub needs no `channels` section."""
    from .github import GitHubLedger

    return GitHubLedger(dict(cli_config or {}))


def load_channels(
    cli_config: Optional[Mapping[str, Any]], client_factory=None
) -> List[Channel]:
    """The enabled **subscriber** channels from the CLI config's ``channels``
    section — the ledger is loaded separately (:func:`load_ledger`).

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
