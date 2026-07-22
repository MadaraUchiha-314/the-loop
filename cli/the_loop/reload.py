"""Config hot-reload primitive shared by the poller and the webhook receiver.

A tiny, thread-unsafe-by-design change detector: content-hash a file and, when
it changes, call a ``build`` callback to produce a fresh value (a poll plan, a
routing config, …). Callers check it at a natural point (each poll cycle / each
received event), so there is no watcher thread — stdlib only.

A ``build`` that raises (invalid config) is logged and the previous value is
kept, so a bad edit never takes the process down.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable, Generic, Optional, TypeVar

logger = logging.getLogger("the-loop.reload")

T = TypeVar("T")


class Reloader(Generic[T]):
    """Detects changes to ``path`` and rebuilds a value of type ``T`` on change.

    Change detection is a content hash checked on demand (no watcher thread), so
    reload granularity is however often the caller polls it. Callers that share
    the value across threads must serialize their check-and-apply themselves.
    """

    def __init__(
        self,
        path,
        build: Callable[[], T],
        baseline: Optional[str] = None,
    ):
        self.path = Path(path)
        self._build = build
        # Baseline to the current file so the first check doesn't rebuild the
        # value the caller already constructed; None => read it now.
        self._fingerprint = baseline if baseline is not None else self._read_fp()

    def _read_fp(self) -> str:
        try:
            return hashlib.sha256(self.path.read_bytes()).hexdigest()
        except OSError:
            return ""  # no file (or unreadable) => nothing to hot-reload

    def poll_for_change(self) -> Optional[T]:
        """Return a freshly built value iff the file changed since last check."""
        fingerprint = self._read_fp()
        if fingerprint == self._fingerprint:
            return None
        self._fingerprint = fingerprint
        try:
            value = self._build()
        except Exception as exc:  # noqa: BLE001 — a bad edit must not crash us
            logger.error("config reload failed; keeping previous config: %s", exc)
            return None
        logger.info("config change detected at %s; reloaded", self.path)
        return value
