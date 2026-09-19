"""One ring for every interactive trigger (issue-389 design §6).

Slack delivers a slash command, a shortcut and a modal submission each with a
one-shot id — ``trigger_id`` for the first two, the view's ``id`` for the
third — and may redeliver an envelope the listener did not acknowledge in
time. A trigger acts once (issue-334 A9): the id is remembered in a bounded,
per-process ring, and a second sight is a ``duplicate`` drop. Three surfaces,
one ring, one eviction rule.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Set

__all__ = ["first_sight", "reset"]

_SEEN_MAX = 256
_SEEN: Deque[str] = deque()
_SEEN_SET: Set[str] = set()


def first_sight(trigger: str) -> bool:
    """Whether ``trigger`` is new to this process; remembers it in the ring.
    An empty trigger is always new — there is nothing to remember."""
    if not trigger:
        return True
    if trigger in _SEEN_SET:
        return False
    _SEEN.append(trigger)
    _SEEN_SET.add(trigger)
    while len(_SEEN) > _SEEN_MAX:
        _SEEN_SET.discard(_SEEN.popleft())
    return True


def reset() -> None:
    """Forget every trigger (tests)."""
    _SEEN.clear()
    _SEEN_SET.clear()
