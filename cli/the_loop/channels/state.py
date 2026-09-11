"""Thread bindings, per-work-item conversations, read cursors and the questions
the-loop is still waiting on — one JSON file per channel type (issue-245 D4,
issue-312, issue-349).

Local, not portable: a binding is a handle into one deployment's conversation
(a Slack thread this machine's bot started), and the cursor records what THIS
deployment already mirrored and delivered — carried elsewhere it would suppress
replies the other machine never processed, or double-process the ones it did.
Registered in :data:`the_loop.state.GENERATED_PATHS` and documented in
``docs/cli/state.md`` like every other generated file.

Three maps since issue-312. ``threads`` (thread ts → work item, channel) is the
**reader's** map — the poll transport iterates it, the socket transport looks a
``thread_ts`` up in it. ``conversations`` (work item → channel, thread, opened,
origin, permalink) is the **writer's** answer to "where does this work item's
next message go": keyed by work item, so one work item has one thread by
construction, and a file written before issue-312 (threads only) is backfilled
from its newest binding on load. ``cursors`` is unchanged.

A fourth map since issue-349: ``pending`` (message ts -> the question the-loop asked
about it). It is the one piece of state a kickoff has ever needed -- a member's
top-level message, held while they are asked **which repository** it goes in, so a
pick can finish opening it. Unlike the other three it is **transient by
construction**: a record is invisible past :data:`PENDING_TTL_SECONDS`, the map is
capped at :data:`PENDING_CAP`, and an answered record is *claimed* (popped under the
lock) before the issue is created, which is what makes two presses open one issue.

Every mutation is a read-modify-write, and four writers share the file — the
agent's session (``the-loop ask``, the graph's ``notify`` hook), the two daemons'
ingress and the poll watcher's thread — so the critical section is
:meth:`ChannelState.locked`: an exclusive ``flock`` on a **sibling** lock file
(a lock on the state file itself would be released by the atomic ``os.replace``
that writes it). Without ``flock`` the section runs unlocked, once logged.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from .. import runlock

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "CONVERSATION_ORIGINS",
    "PENDING_CAP",
    "PENDING_TTL_SECONDS",
    "THREAD_CAP",
    "ChannelState",
    "canonical",
]

#: How many conversations one channel file remembers. Past the cap the OLDEST
#: binding is dropped: an unmapped thread is inert (the pipeline drops its
#: replies as ``unmapped``), so forgetting an old conversation only means the
#: bot stops listening to it — never that it mis-attributes a reply.
THREAD_CAP = 200

#: How a conversation came to be bound: the-loop opened a root for an event;
#: a member's top-level message became the work item (``work-item.create``);
#: the binding predates issue-312 and was derived from the thread map; or
#: the-loop opened the root when the work item **started** (issue-317) — before
#: any event, on the dispatcher's spawn path.
CONVERSATION_ORIGINS: Tuple[str, ...] = ("event", "kickoff", "legacy", "start")

#: How long an unanswered kickoff question stays answerable (issue-349 R3.2).
#: A day is phone-shaped: long enough to answer in the morning, short enough that
#: the answer still refers to a message right above it in the thread.
PENDING_TTL_SECONDS = 24 * 60 * 60

#: How many outstanding questions one channel file remembers (R3.3). Smaller than
#: :data:`THREAD_CAP` on purpose — a question is transient, a binding is not — and
#: past it the OLDEST goes, so a burst of new questions can never bury a fresh one.
PENDING_CAP = 50

_LOCK_WARNED = False


def canonical(work_item: str) -> str:
    """``work_item`` as :class:`WorkItemRef` spells it — so ``github:o/r#7`` and
    ``github:github.com/o/r#7`` are one conversation (issue-312 R1.3). A string
    that is not a work-item ref (a standing session's) is its own key."""
    from ..sessions import WorkItemRef

    try:
        return WorkItemRef.parse(work_item).ref
    except ValueError:
        return work_item


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class ChannelState:
    """The bindings (thread → work item), the conversations (work item → thread),
    the cursors (thread → last-seen ts) and the pending questions (message ts →
    the kickoff the-loop is waiting on an answer for)."""

    threads: Dict[str, Dict[str, str]] = field(default_factory=dict)
    cursors: Dict[str, str] = field(default_factory=dict)
    conversations: Dict[str, Dict[str, str]] = field(default_factory=dict)
    #: Unanswered kickoff questions (issue-349): message ts → ``{channel, author,
    #: text, options, asked}``. Insertion-ordered, so the cap drops the oldest.
    pending: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    #: True when :meth:`load` derived a conversation from a pre-issue-312 file —
    #: the next writer saves so the file converges on the keyed shape (R3.4).
    backfilled: bool = field(default=False, repr=False, compare=False)

    @classmethod
    def load(cls, path: Union[str, Path]) -> "ChannelState":
        """The state at ``path`` — empty on a missing or unreadable file.

        Corrupt state resolves to empty rather than raising: the cost is
        re-reading a thread from its root (the marker and the cursor default
        make that harmless), while a crash here would take the daemon with it.
        A pre-issue-312 file (no ``conversations``) is backfilled: each work
        item's conversation is its **newest** binding, marked ``legacy``.
        """
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        threads = raw.get("threads")
        cursors = raw.get("cursors")
        conversations = raw.get("conversations")
        # A file written before issue-349 has no `pending` key: it loads as an
        # empty map and is written back with the key by the next writer. No
        # migration, no version — a question nobody asked is simply not pending.
        pending = raw.get("pending")
        state = cls(
            threads={
                str(ts): {str(k): str(v) for k, v in info.items()}
                for ts, info in (threads or {}).items()
                if isinstance(info, dict)
            },
            cursors={str(ts): str(cur) for ts, cur in (cursors or {}).items()},
            conversations={
                str(item): {str(k): str(v) for k, v in info.items()}
                for item, info in (conversations or {}).items()
                if isinstance(info, dict) and info.get("thread")
            },
            pending={
                str(ts): _pending_record(info)
                for ts, info in (pending or {}).items()
                if isinstance(info, dict) and info.get("asked")
            },
        )
        for ts, info in state.threads.items():  # oldest → newest: newest wins
            work_item = info.get("workItem") or ""
            if not work_item:
                continue
            known = state.conversations.get(work_item)
            if known is None or known.get("origin") == "legacy":
                if known is None:
                    state.backfilled = True
                state.conversations[work_item] = _record(
                    ts, info.get("channel", ""), origin="legacy"
                )
        return state

    def save(self, path: Union[str, Path]) -> None:
        """Atomic write (tmp + rename), directories created on demand."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {
                "threads": self.threads,
                "cursors": self.cursors,
                "conversations": self.conversations,
                "pending": self.pending,
            },
            indent=2,
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

    @classmethod
    @contextmanager
    def locked(cls, path: Union[str, Path]) -> Iterator["ChannelState"]:
        """Load ``path`` under an exclusive lock held until the block ends.

        The caller mutates and :meth:`save`\\ s inside the block; every writer
        of one state file goes through here so a bind never races an advance
        and two first events for one work item open one thread (issue-312
        R1.4). The lock is ``<path>.lock``, ``flock``\\ ed through
        :mod:`the_loop.runlock`'s platform check; without ``flock`` the block
        runs unlocked — today's behaviour — and says so once at debug.
        """
        global _LOCK_WARNED
        target = Path(path)
        if not runlock.HAVE_FLOCK:
            if not _LOCK_WARNED:
                logger.debug(
                    "channel state %s: no flock on this platform — read-modify-"
                    "write runs unlocked",
                    target,
                )
                _LOCK_WARNED = True
            yield cls.load(target)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(
            str(target) + ".lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600
        )
        try:
            runlock.fcntl.flock(lock_fd, runlock.fcntl.LOCK_EX)
            yield cls.load(target)
        finally:
            try:
                runlock.fcntl.flock(lock_fd, runlock.fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)

    def bind(
        self,
        thread: str,
        work_item: str,
        channel_id: str,
        *,
        origin: str = "event",
        permalink: str = "",
    ) -> None:
        """Record that ``thread`` carries ``work_item``'s conversation.

        Writes both maps: the reader's (thread → work item) and the writer's
        (work item → thread). A work item bound again moves to the new thread;
        the old thread stays readable and still attributed, as before.
        """
        work_item = canonical(work_item) if work_item else work_item
        self.threads.pop(thread, None)  # re-binding moves it to newest
        self.threads[thread] = {"workItem": work_item, "channel": channel_id}
        if work_item:
            self.conversations[work_item] = _record(
                thread, channel_id, origin=origin, permalink=permalink
            )
        while len(self.threads) > THREAD_CAP:
            oldest = next(iter(self.threads))
            dropped = self.threads.pop(oldest, None) or {}
            self.cursors.pop(oldest, None)
            item = dropped.get("workItem") or ""
            if item and self.conversations.get(item, {}).get("thread") == oldest:
                self.conversations.pop(item, None)

    def thread_for(self, work_item: str) -> Optional[Tuple[str, str]]:
        """``(channel_id, thread_ts)`` of ``work_item``'s conversation, or None."""
        record = self.conversations.get(canonical(work_item)) if work_item else None
        if record and record.get("thread"):
            return (record.get("channel", ""), record["thread"])
        return None

    def conversation(self, work_item: str) -> Optional[Dict[str, str]]:
        """The per-work-item record — channel, thread, opened, origin, permalink."""
        record = self.conversations.get(canonical(work_item)) if work_item else None
        return dict(record) if record else None

    def work_item_for(self, thread: str) -> Optional[str]:
        info = self.threads.get(thread)
        return info.get("workItem") if info else None

    def cursor(self, thread: str) -> str:
        """The last-processed ts in ``thread`` — the thread root when new."""
        return self.cursors.get(thread, thread)

    def advance(self, thread: str, ts: str) -> None:
        self.cursors[thread] = ts

    # -- pending kickoff questions (issue-349) ---------------------------------

    def ask(
        self,
        ts: str,
        channel_id: str,
        author: str,
        text: str,
        options: Sequence[str],
    ) -> None:
        """Record that ``ts`` is waiting on an answer (R3.1).

        Sweeps the expired first, then caps: past :data:`PENDING_CAP` the OLDEST
        question goes, exactly as :data:`THREAD_CAP` drops the oldest binding.
        Forgetting a question only means the member is never able to answer it —
        never that the wrong message is opened.
        """
        self.prune_pending()
        self.pending.pop(ts, None)  # re-asking moves it to newest
        self.pending[ts] = {
            "channel": channel_id,
            "author": author,
            "text": text,
            "options": [str(option) for option in options],
            "asked": _now(),
        }
        while len(self.pending) > PENDING_CAP:
            self.pending.pop(next(iter(self.pending)), None)

    def pending_for(self, ts: str) -> Optional[Dict[str, Any]]:
        """The live question about ``ts``, or ``None`` when there is none — an
        EXPIRED record reads as absent (R3.2) rather than being deleted here, so
        no read path has to write. The sweep is :meth:`prune_pending`'s."""
        record = self.pending.get(ts)
        if not record or _expired(record):
            return None
        return dict(record)

    def claim(self, ts: str) -> Optional[Dict[str, Any]]:
        """Pop ``ts``'s question if it is live, else ``None`` (R3.4).

        The answer-once rule, and the reason it is a pop rather than a flag: the
        caller claims under the state lock and publishes outside it, so a second
        press arriving in between finds nothing to answer. An expired record is
        removed too — it was never answerable.
        """
        record = self.pending.pop(ts, None)
        if not record or _expired(record):
            return None
        return dict(record)

    def restore(self, ts: str, record: Dict[str, Any]) -> None:
        """Put a claimed question back after the create failed (R3.5) — so the
        picker the press report left in place still answers something."""
        self.pending[ts] = dict(record)

    def forget(self, ts: str) -> None:
        """Drop ``ts``'s question — the post of the question itself failed, so a
        record nobody can see must not suppress the next one (R3.7)."""
        self.pending.pop(ts, None)

    def prune_pending(self) -> None:
        """Drop every expired question. Called on write, never on read."""
        for ts in [ts for ts, rec in self.pending.items() if _expired(rec)]:
            self.pending.pop(ts, None)


def _pending_record(info: Dict[str, Any]) -> Dict[str, Any]:
    """One question as it is held in memory — every field coerced, ``options``
    kept a list of strings. A record read back from disk is data the daemon
    itself wrote, but it is parsed like anything else: a malformed ``options``
    contributes nothing, which can only make the offered set smaller."""
    raw = info.get("options")
    options: List[str] = (
        [str(option) for option in raw] if isinstance(raw, (list, tuple)) else []
    )
    return {
        "channel": str(info.get("channel") or ""),
        "author": str(info.get("author") or ""),
        "text": str(info.get("text") or ""),
        "options": options,
        "asked": str(info.get("asked") or ""),
    }


def _expired(record: Dict[str, Any]) -> bool:
    """Whether a pending question is past :data:`PENDING_TTL_SECONDS`.

    An unparseable or absent ``asked`` is **expired**, not eternal: a record the
    daemon cannot date is one it cannot honour, and the fail-closed direction
    here is to refuse the answer rather than open an issue from a message of
    unknown age.
    """
    stamp = str(record.get("asked") or "")
    try:
        asked = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return True
    if asked.tzinfo is None:
        asked = asked.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - asked).total_seconds() > PENDING_TTL_SECONDS


def _record(
    thread: str, channel_id: str, *, origin: str, permalink: str = ""
) -> Dict[str, str]:
    return {
        "channel": channel_id,
        "thread": thread,
        "opened": _now(),
        "origin": origin if origin in CONVERSATION_ORIGINS else "event",
        "permalink": permalink or "",
    }
