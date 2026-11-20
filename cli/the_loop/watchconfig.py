"""``routing.watchdog`` and ``routing.asks`` — the idle watcher's knobs.

Kept apart from the watcher so that the dispatcher, the stop check and the
status surfaces can read the same numbers without importing each other.

The schema is the gate for these values. ``from_mapping`` still falls back to
the default for one the schema would refuse, as ``routing.ci`` does: a mapping
that never met the schema (a test, an embedder) must not yield a zero idle
threshold, which would nudge a session on every tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

__all__ = [
    "AsksConfig",
    "DEFAULT_IDLE_SECONDS",
    "DEFAULT_MAX_NUDGES",
    "DEFAULT_MAX_WAIT_SECONDS",
    "DEFAULT_MIN_DEFAULT_WAIT_SECONDS",
    "DEFAULT_REMINDER_SECONDS",
    "WatchdogConfig",
]

DEFAULT_IDLE_SECONDS = 600
DEFAULT_MAX_NUDGES = 2
DEFAULT_MAX_WAIT_SECONDS = 3600
DEFAULT_MIN_DEFAULT_WAIT_SECONDS = 1800
DEFAULT_REMINDER_SECONDS = 7200


def _whole(raw: Any, default: int, minimum: int) -> int:
    """``raw`` when it is a whole number of at least ``minimum``, else ``default``."""
    if isinstance(raw, int) and not isinstance(raw, bool) and raw >= minimum:
        return raw
    return default


@dataclass
class WatchdogConfig:
    """``routing.watchdog`` — when an idle session is nudged, and how often."""

    #: ``False`` sends no nudge and no stall notice. The Stop gate and the turn
    #: records do not read it.
    enabled: bool = True
    idle_seconds: int = DEFAULT_IDLE_SECONDS
    #: ``0`` skips the nudges and goes to the notice.
    max_nudges: int = DEFAULT_MAX_NUDGES
    #: The longest declared wait, and the longest time background work is
    #: believed without a new turn.
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "WatchdogConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            idle_seconds=_whole(data.get("idleSeconds"), DEFAULT_IDLE_SECONDS, 1),
            max_nudges=_whole(data.get("maxNudges"), DEFAULT_MAX_NUDGES, 0),
            max_wait_seconds=_whole(
                data.get("maxWaitSeconds"), DEFAULT_MAX_WAIT_SECONDS, 1
            ),
        )


@dataclass
class AsksConfig:
    """``routing.asks`` — the deadline of an ask's default, and the reminder."""

    #: A shorter `--after` is raised to this.
    min_default_wait_seconds: int = DEFAULT_MIN_DEFAULT_WAIT_SECONDS
    #: ``0`` sends no reminder.
    reminder_seconds: int = DEFAULT_REMINDER_SECONDS

    @classmethod
    def from_mapping(cls, data: Optional[Mapping[str, Any]]) -> "AsksConfig":
        data = data or {}
        return cls(
            min_default_wait_seconds=_whole(
                data.get("minDefaultWaitSeconds"), DEFAULT_MIN_DEFAULT_WAIT_SECONDS, 1
            ),
            reminder_seconds=_whole(
                data.get("reminderSeconds"), DEFAULT_REMINDER_SECONDS, 0
            ),
        )
