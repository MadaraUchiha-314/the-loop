"""Thread bindings and read cursors — one JSON file per channel type (D4).

Local, not portable: a binding is a handle into one deployment's conversation
(a Slack thread this machine's bot started), and the cursor records what THIS
deployment already mirrored and delivered — carried elsewhere it would suppress
replies the other machine never processed, or double-process the ones it did.
Registered in :data:`the_loop.state.GENERATED_PATHS` and documented in
``docs/cli/state.md`` like every other generated file.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

logger = logging.getLogger("the-loop.channels")

__all__ = ["THREAD_CAP", "ChannelState"]

#: How many conversations one channel file remembers. Past the cap the OLDEST
#: binding is dropped: an unmapped thread is inert (the pipeline drops its
#: replies as ``unmapped``), so forgetting an old conversation only means the
#: bot stops listening to it — never that it mis-attributes a reply.
THREAD_CAP = 200


@dataclass
class ChannelState:
    """The bindings (thread → work item) and cursors (thread → last-seen ts)."""

    threads: Dict[str, Dict[str, str]] = field(default_factory=dict)
    cursors: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ChannelState":
        """The state at ``path`` — empty on a missing or unreadable file.

        Corrupt state resolves to empty rather than raising: the cost is
        re-reading a thread from its root (the marker and the cursor default
        make that harmless), while a crash here would take the daemon with it.
        """
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        threads = raw.get("threads")
        cursors = raw.get("cursors")
        return cls(
            threads={
                str(ts): {str(k): str(v) for k, v in info.items()}
                for ts, info in (threads or {}).items()
                if isinstance(info, dict)
            },
            cursors={str(ts): str(cur) for ts, cur in (cursors or {}).items()},
        )

    def save(self, path: Union[str, Path]) -> None:
        """Atomic write (tmp + rename), directories created on demand."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"threads": self.threads, "cursors": self.cursors}, indent=2
        )
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            os.replace(tmp, target)
        except OSError as exc:
            logger.warning("could not write channel state %s: %s", target, exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def bind(self, thread: str, work_item: str, channel_id: str) -> None:
        """Record that ``thread`` carries ``work_item``'s conversation."""
        self.threads.pop(thread, None)  # re-binding moves it to newest
        self.threads[thread] = {"workItem": work_item, "channel": channel_id}
        while len(self.threads) > THREAD_CAP:
            oldest = next(iter(self.threads))
            self.threads.pop(oldest, None)
            self.cursors.pop(oldest, None)

    def thread_for(self, work_item: str) -> Optional[Tuple[str, str]]:
        """``(channel_id, thread_ts)`` of the newest binding for ``work_item``."""
        for thread in reversed(list(self.threads)):
            info = self.threads[thread]
            if info.get("workItem") == work_item:
                return (info.get("channel", ""), thread)
        return None

    def work_item_for(self, thread: str) -> Optional[str]:
        info = self.threads.get(thread)
        return info.get("workItem") if info else None

    def cursor(self, thread: str) -> str:
        """The last-processed ts in ``thread`` — the thread root when new."""
        return self.cursors.get(thread, thread)

    def advance(self, thread: str, ts: str) -> None:
        self.cursors[thread] = ts
