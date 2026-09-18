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
from typing import (
    Any,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
)

from .. import runlock

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "CONVERSATION_ORIGINS",
    "PENDING_CAP",
    "PENDING_TTL_SECONDS",
    "ROOM_MODE",
    "THREAD_CAP",
    "ChannelState",
    "ChannelStores",
    "canonical",
]

#: A conversation's ``mode`` when it is a whole channel rather than a thread
#: (issue-378): the work item was declared into a room of its own, so every
#: update is a top-level message there. Absent on every thread record.
ROOM_MODE = "channel"

#: How many conversations one channel file remembers. Past the cap the OLDEST
#: binding is dropped: an unmapped thread is inert (the pipeline drops its
#: replies as ``unmapped``), so forgetting an old conversation only means the
#: bot stops listening to it — never that it mis-attributes a reply.
THREAD_CAP = 200

#: How a conversation came to be bound: the-loop opened a root for an event;
#: a member's top-level message became the work item (``work-item.create``);
#: the binding predates issue-312 and was derived from the thread map;
#: the-loop opened the root when the work item **started** (issue-317) — before
#: any event, on the dispatcher's spawn path; or the work item was **declared**
#: into a collaboration channel after its conversation had started somewhere
#: else, so the root was re-opened there (issue-375).
CONVERSATION_ORIGINS: Tuple[str, ...] = (
    "event",
    "kickoff",
    "legacy",
    "start",
    "declared",
)

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


def _is_work_item(key: str) -> bool:
    """Whether ``key`` names a work item — as opposed to a standing session.

    A standing session (``standing:<name>``) belongs to no work item: it has no
    portable record to hold its binding and no ticket anywhere, so its thread
    binding and its cursor stay in this machine's channel file, beside the
    per-channel kickoff cursors. Everything the-loop tracks per work item goes
    to that work item's records (issue-368).
    """
    from ..sessions import WorkItemRef

    try:
        WorkItemRef.parse(key)
    except ValueError:
        return False
    return True


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass
class ChannelStores:
    """Where a work item's channel facts live **outside** this file (issue-368).

    Two of the four maps below are not this file's to keep:

    * a **binding** — which thread carries which work item's conversation — is a
      remote entity the-loop created. It is true whoever runs the daemon, so it
      belongs in that work item's portable record; the machine that opened the
      thread must not be the only one that knows, or a second machine opens a
      second root and drops replies in the first as ``unmapped``. It stays in
      the OPERATOR's record rather than the work item's repository because a
      channel id, a thread ts and a workspace permalink are the operator's
      workspace's, not the repository's;
    * a **cursor** — the last reply THIS deployment mirrored — is a statement
      about this machine, so it sits with the handles in the session record.

    What stays in the file is what belongs to no work item: the per-channel
    kickoff cursors and the pending questions.

    ``None`` anywhere a :class:`ChannelStores` is expected means "no stores" —
    the file answers for everything, which is what a test with a bare path and
    every pre-issue-368 deployment get.
    """

    channel: str
    portable_dir: str
    registry_dir: str

    @classmethod
    def beside(
        cls, state_path: Union[str, Path], channel: str = "slack"
    ) -> "ChannelStores":
        """The stores under the same ``state.root`` as ``<root>/channels/<c>.json``.

        The layout is one root with three directories (decision-046), so the
        channel file's grandparent *is* that root. Derived rather than passed so
        every construction site of a channel keeps its one argument.
        """
        root = Path(state_path).parent.parent
        return cls(
            channel=channel,
            portable_dir=str(root / "portable"),
            registry_dir=str(root / "local"),
        )

    # -- bindings, in the operator's portable records --------------------------

    def _store(self):
        from ..workitem import WorkItemStore

        return WorkItemStore(self.portable_dir)

    def bindings(self) -> Dict[str, Dict[str, str]]:
        """``{work item: {channel, thread, opened, origin, permalink}}``.

        Read from every portable record that carries one. A record without a
        binding for this channel contributes nothing, and an unreadable
        directory answers ``{}`` — a channel that cannot find its bindings
        drops replies as ``unmapped``, which is what it already did for an
        unknown thread.
        """
        found: Dict[str, Dict[str, str]] = {}
        try:
            store = self._store()
            for _, record in store._records():  # noqa: SLF001 — same package's store
                entry = (record.get("channels") or {}).get(self.channel)
                if isinstance(entry, dict) and (entry.get("thread") or _is_room(entry)):
                    found[str(record["ref"])] = {
                        str(k): str(v) for k, v in entry.items()
                    }
        except (OSError, ValueError, KeyError) as exc:
            logger.warning("could not read the channel bindings: %s", exc)
        return found

    def write_binding(self, work_item: str, record: Dict[str, str]) -> None:
        """Record (or replace) ``work_item``'s conversation on this channel."""
        try:
            store = self._store()
            channels = dict(store.section(work_item, "channels") or {})
            channels[self.channel] = dict(record)
            store.write_section(work_item, "channels", channels)
        except (OSError, ValueError) as exc:
            logger.warning("could not record %s's channel binding: %s", work_item, exc)

    def drop_binding(self, work_item: str) -> None:
        """Forget ``work_item``'s conversation on this channel."""
        try:
            store = self._store()
            channels = dict(store.section(work_item, "channels") or {})
            if channels.pop(self.channel, None) is None:
                return
            store.write_section(work_item, "channels", channels or None)
        except (OSError, ValueError) as exc:
            logger.warning("could not drop %s's channel binding: %s", work_item, exc)

    # -- declarations, in the same portable records (issue-375) ----------------

    def _declarations(self):
        from ..workchannels import CollaborationChannelStore

        return CollaborationChannelStore(self.portable_dir)

    def declared(self, work_item: str) -> str:
        """The channel ``work_item`` was DECLARED to live in, or ``""``.

        The difference from :meth:`bindings` is the difference the feature turns
        on: a binding says where this work item's conversation *is*, a
        declaration says where it *belongs*. When the two disagree the channel
        moves the conversation; when there is no declaration the operator's
        central channel answers, exactly as it did before issue-375.
        """
        if not work_item:
            return ""
        try:
            record = self._declarations().for_type(work_item, self.channel)
        except (OSError, ValueError) as exc:
            logger.debug("could not read %s's declared channel: %s", work_item, exc)
            return ""
        return record.target if record else ""

    def declared_work_item(self, target: str) -> str:
        """The work item that declared ``target`` — ``""`` when none did.

        The reverse lookup the ingress reads to decide whose conversation a room
        is. A target two work items claim answers ``""``: see
        :meth:`the_loop.workchannels.CollaborationChannelStore.declared_by`.
        """
        if not target:
            return ""
        try:
            return self._declarations().declared_by(f"{self.channel}@{target}")
        except (OSError, ValueError) as exc:
            logger.debug("could not read the declaration for %s: %s", target, exc)
            return ""

    def declared_targets(self) -> Dict[str, str]:
        """``{target: work item}`` for every declared channel of this type."""
        try:
            return self._declarations().targets(self.channel)
        except (OSError, ValueError) as exc:
            logger.debug("could not read the channel declarations: %s", exc)
            return {}

    # -- cursors, in this machine's session records ----------------------------

    def _registry(self):
        from ..sessions import SessionRegistry

        return SessionRegistry(self.registry_dir)

    def cursor(self, work_item: str, thread: str) -> str:
        """What this machine has already mirrored in ``thread``, or ``""``."""
        if not work_item:
            return ""
        try:
            return self._registry().cursor(work_item, self.channel, thread)
        except (OSError, ValueError) as exc:
            logger.debug("could not read %s's read cursor: %s", work_item, exc)
            return ""

    def advance(self, work_item: str, thread: str, ts: str) -> bool:
        """Record that ``thread`` is mirrored up to ``ts`` on this machine."""
        if not work_item:
            return False
        try:
            return self._registry().advance_cursor(work_item, self.channel, thread, ts)
        except (OSError, ValueError) as exc:
            logger.debug("could not advance %s's read cursor: %s", work_item, exc)
            return False


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
    #: Where the bindings and the cursors actually live (issue-368). ``None``
    #: keeps everything in the file, which is the pre-issue-368 behaviour and
    #: what a bare path still gets.
    stores: Optional[ChannelStores] = field(default=None, repr=False, compare=False)
    #: Work items whose binding this instance changed, and threads whose cursor
    #: it advanced — so a save writes the two records it touched rather than
    #: every record it read.
    _dirty_bindings: set = field(default_factory=set, repr=False, compare=False)
    _dirty_cursors: set = field(default_factory=set, repr=False, compare=False)
    #: Threads whose cursor this file keeps because no session record on this
    #: machine can hold it. Seeded from what the file already carries, so a
    #: cursor written before issue-368 is honoured until its work item has a
    #: session record to move it into.
    _file_cursors: set = field(default_factory=set, repr=False, compare=False)

    @classmethod
    def load(
        cls, path: Union[str, Path], stores: Optional[ChannelStores] = None
    ) -> "ChannelState":
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
            # An absent or corrupt file is empty, not store-less: the bindings
            # are not in this file any more, and a first run has no file at all.
            return cls(stores=stores)._with_bindings()
        if not isinstance(raw, dict):
            return cls(stores=stores)._with_bindings()
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
            stores=stores,
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
        state._file_cursors = {
            key for key in state.cursors if not key.startswith("channel:")
        }
        return state._with_bindings()

    def save(self, path: Union[str, Path]) -> None:
        """Atomic write (tmp + rename), directories created on demand.

        With :class:`ChannelStores` the two maps that are not this file's are
        written where they belong first — a changed binding into its work
        item's portable record, an advanced cursor into its session record —
        and this file keeps only what belongs to no work item: the per-channel
        kickoff cursors and the pending questions (issue-368). Only what THIS
        instance changed is written out, so a save costs the records it touched
        rather than every record it read.
        """
        self._flush_stores()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._file_payload(), indent=2)
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

    def _with_bindings(self) -> "ChannelState":
        """Overlay the bindings the portable records hold (issue-368).

        They WIN over anything this file still carries: a binding in the file
        was written before the change and is honoured only until the work
        item's next write puts it in its record (R5.4) — it is never written
        back here. Without stores this is a no-op, which is the pre-issue-368
        behaviour a bare path still gets.
        """
        if self.stores is None:
            return self
        # Whatever this FILE still holds was written before issue-368, and this
        # file stops carrying bindings on the next save — so every one of them
        # is marked for migration into its work item's portable record (R5.4).
        # Without this the first save would drop a binding nobody had copied.
        self._dirty_bindings.update(
            key for key in self.conversations if _is_work_item(key)
        )
        for work_item, record in self.stores.bindings().items():
            self.conversations[work_item] = dict(record)
            thread = record.get("thread") or ""
            if thread:
                self.threads[thread] = {
                    "workItem": work_item,
                    "channel": record.get("channel", ""),
                }
        return self

    def _file_payload(self) -> Dict[str, Any]:
        """What this file keeps.

        With stores, only what belongs to no work item (issue-368): the
        per-channel kickoff cursors — keyed ``channel:<id>``, which can never
        collide with a thread ts — and the pending questions. Without them, all
        four maps, exactly as before.
        """
        if self.stores is None:
            return {
                "threads": self.threads,
                "cursors": self.cursors,
                "conversations": self.conversations,
                "pending": self.pending,
            }
        kept = {
            item: record
            for item, record in self.conversations.items()
            if not _is_work_item(item)
        }
        payload: Dict[str, Any] = {
            "cursors": {
                key: value
                for key, value in self.cursors.items()
                if key.startswith("channel:") or key in self._file_cursors
            },
            "pending": self.pending,
        }
        if kept:
            # A standing session's conversation is nobody's work item, so it
            # keeps both halves of its binding here (issue-368).
            payload["conversations"] = kept
            payload["threads"] = {
                thread: info
                for thread, info in self.threads.items()
                if not _is_work_item(info.get("workItem") or "")
            }
        return payload

    def _flush_stores(self) -> None:
        """Write the bindings and cursors this instance changed to their homes."""
        stores = self.stores
        if stores is None:
            return
        for work_item in sorted(self._dirty_bindings):
            if not _is_work_item(work_item):
                continue  # a standing session's binding stays in this file
            record = self.conversations.get(work_item)
            if record is None:
                stores.drop_binding(work_item)
            else:
                stores.write_binding(work_item, record)
        for thread in sorted(self._dirty_cursors):
            work_item = (self.threads.get(thread) or {}).get("workItem") or ""
            if _is_work_item(work_item) and stores.advance(
                work_item, thread, self.cursors.get(thread, "")
            ):
                self._file_cursors.discard(thread)
            else:
                # No session record here to hold it — an armed work item whose
                # session has not spawned, or one whose local resources were
                # released. The cursor is still this machine's, so it stays in
                # this machine's channel file: losing it would re-process every
                # reply in that thread on the next cycle, and at-most-once is
                # the one contract a cursor exists for.
                self._file_cursors.add(thread)
        self._dirty_bindings.clear()
        self._dirty_cursors.clear()

    @classmethod
    @contextmanager
    def locked(
        cls, path: Union[str, Path], stores: Optional[ChannelStores] = None
    ) -> Iterator["ChannelState"]:
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
            yield cls.load(target, stores)
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = os.open(
            str(target) + ".lock", os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600
        )
        try:
            runlock.fcntl.flock(lock_fd, runlock.fcntl.LOCK_EX)
            yield cls.load(target, stores)
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
        mode: str = "",
    ) -> None:
        """Record that ``thread`` carries ``work_item``'s conversation.

        Writes both maps: the reader's (thread → work item) and the writer's
        (work item → thread). A work item bound again moves to the new thread;
        the old thread stays readable and still attributed, as before.

        With ``mode="channel"`` and an empty ``thread`` (issue-378) the
        conversation is the room ``channel_id`` itself: only the writer's map is
        written, because there is no thread for the reader to look up — a
        message in the room is attributed through the declaration instead.
        """
        work_item = canonical(work_item) if work_item else work_item
        if thread:
            self.threads.pop(thread, None)  # re-binding moves it to newest
            self.threads[thread] = {"workItem": work_item, "channel": channel_id}
        if work_item:
            self.conversations[work_item] = _record(
                thread, channel_id, origin=origin, permalink=permalink, mode=mode
            )
            self._dirty_bindings.add(work_item)
        while len(self.threads) > THREAD_CAP:
            oldest = next(iter(self.threads))
            dropped = self.threads.pop(oldest, None) or {}
            self.cursors.pop(oldest, None)
            item = dropped.get("workItem") or ""
            if item and self.conversations.get(item, {}).get("thread") == oldest:
                self.conversations.pop(item, None)
                self._dirty_bindings.add(item)

    def thread_for(self, work_item: str) -> Optional[Tuple[str, str]]:
        """``(channel_id, thread_ts)`` of ``work_item``'s conversation, or None —
        also None for a **room** conversation, which has no thread to reply in
        or to read (issue-378); the writer's view is :meth:`conversation_for`."""
        record = self.conversations.get(canonical(work_item)) if work_item else None
        if record and record.get("thread"):
            return (record.get("channel", ""), record["thread"])
        return None

    def conversation_for(self, work_item: str) -> Optional[Tuple[str, str]]:
        """``(channel_id, thread_ts)`` of where ``work_item``'s next message goes
        (issue-378): a thread, or a room with ``thread_ts == ""``. None when the
        work item has no conversation on this channel."""
        record = self.conversations.get(canonical(work_item)) if work_item else None
        if not record:
            return None
        if record.get("thread"):
            return (record.get("channel", ""), record["thread"])
        if _is_room(record) and record.get("channel"):
            return (record["channel"], "")
        return None

    def conversation(self, work_item: str) -> Optional[Dict[str, str]]:
        """The per-work-item record — channel, thread, opened, origin, permalink."""
        record = self.conversations.get(canonical(work_item)) if work_item else None
        return dict(record) if record else None

    def work_item_for(self, thread: str) -> Optional[str]:
        info = self.threads.get(thread)
        return info.get("workItem") if info else None

    def cursor(self, thread: str) -> str:
        """The last-processed ts in ``thread`` — the thread root when new.

        With stores, a thread's cursor is read from the work item's session
        record on this machine (issue-368); a work item with no session here
        has none, and the thread is read from its root, exactly as an unknown
        thread always was.
        """
        if thread in self.cursors:
            return self.cursors[thread]
        if self.stores is not None:
            work_item = (self.threads.get(thread) or {}).get("workItem") or ""
            recorded = self.stores.cursor(work_item, thread)
            if recorded:
                self.cursors[thread] = recorded
                return recorded
        return thread

    def advance(self, thread: str, ts: str) -> None:
        self.cursors[thread] = ts
        if not thread.startswith("channel:"):
            self._dirty_cursors.add(thread)

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
    thread: str,
    channel_id: str,
    *,
    origin: str,
    permalink: str = "",
    mode: str = "",
) -> Dict[str, str]:
    record = {
        "channel": channel_id,
        "thread": thread,
        "opened": _now(),
        "origin": origin if origin in CONVERSATION_ORIGINS else "event",
        "permalink": permalink or "",
    }
    if mode == ROOM_MODE:
        # A room conversation (issue-378): the channel itself, no thread. The key
        # is written only for a room, so every record from before the feature —
        # and every thread — reads exactly as it did.
        record["mode"] = ROOM_MODE
    return record


def _is_room(record: Optional[Mapping[str, Any]]) -> bool:
    return bool(record) and str(record.get("mode") or "") == ROOM_MODE
