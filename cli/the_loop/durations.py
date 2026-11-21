"""Durations a session or an operator types: ``45s``, ``30m``, ``2h``.

One strict form, a positive whole number with one unit. The value becomes a
deadline the daemon acts on by itself (an ask's default, a declared wait), so
text that is nearly a duration is refused instead of guessed at.
"""

from __future__ import annotations

import re

from . import strings

__all__ = ["clamp", "in_words", "parse_duration"]

# ASCII digits only (`\d` also matches other scripts' digits), no leading zero,
# and `fullmatch` so that a trailing newline is not accepted the way `$` would.
_DURATION_RE = re.compile(r"([1-9][0-9]*)([smh])")
_SECONDS = {"s": 1, "m": 60, "h": 3600}


def parse_duration(text: str) -> int:
    """``45s`` / ``30m`` / ``2h`` → seconds. Anything else raises ``ValueError``."""
    match = _DURATION_RE.fullmatch(text) if isinstance(text, str) else None
    if match is None:
        raise ValueError(strings.t("durations.invalid", text=repr(text)))
    return int(match.group(1)) * _SECONDS[match.group(2)]


def clamp(seconds: int, minimum: int) -> int:
    """``seconds``, raised to the operator's ``minimum`` when it is under it."""
    return max(seconds, minimum)


def in_words(seconds: int) -> str:
    """``1800`` → ``30 minutes``, for a sentence a person reads. Whole minutes
    when it is whole minutes, else seconds: a wait is never rounded in words."""
    if seconds % 60:
        return strings.t("durations.seconds", count=seconds)
    if seconds == 60:
        return strings.t("durations.minute")
    return strings.t("durations.minutes", count=seconds // 60)
