"""The queue, behind one interface (issue-496, R2, R3, R4, R11).

:class:`Store` is the protocol a replica would have to re-implement and nothing else
(R11.2); :class:`SqliteStore` is the only implementation in this work item — SQLite from
the standard library, in the gateway's state root, no broker (R6.5). Why SQLite beside a
JSONL event log is design §Trade-offs: one writer process, transactional offsets, a
unique index for dedup and a bounded delete — JSONL cannot do the last three.

The queue is the ``deliveries`` table: one row per *(event, consuming instance)*, with the
table's ``seq`` as every instance's cursor space. ``append`` writes the ``events`` row
and the fan-out rows in **one transaction**, so a provider's acknowledgement implies the
fan-out is durable (R2.4). ``fetch`` is one range read on ``deliveries(instance, seq)``,
so its cost is the fetching instance's backlog alone (NFR *Scalability*). Nothing is kept
in process memory except the :class:`threading.Condition` that wakes long-polls (R11.1):
a gateway restart loses no offset, claim or registration.

Every public method is one transaction on a per-thread connection
(``check_same_thread`` is left at its default; a thread gets its own connection),
``journal_mode=WAL``, ``synchronous=NORMAL``. SQL is bound parameters only — a test greps
this module for an f-string next to ``execute`` (§Security design).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    Any,
    Set,
    Dict,
    Iterator,
    List,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)

from .envelope import (
    DEAD_LETTERED,
    Delivery,
    Envelope,
    is_outcome,
    subject_for_slug,
    utcnow,
)

__all__ = [
    "AppendResult",
    "Claim",
    "CommitResult",
    "ExpireResult",
    "InstanceRow",
    "Lease",
    "QueueRow",
    "Refused",
    "SCHEMA_VERSION",
    "SqliteStore",
    "Store",
    "StoreError",
    "SubjectRow",
]

SCHEMA_VERSION = 1

PENDING, COMMITTED, DEAD = "pending", "committed", "dead"


class StoreError(RuntimeError):
    """A store call that cannot be honoured — the message names why."""


@dataclass(frozen=True)
class Refused:
    """A registration-shaped request the store will not apply (409 at the API)."""

    reason: str  # duplicate-instance | duplicate-actor | commit-undelivered
    holder: str = ""
    since: str = ""
    detail: str = ""


@dataclass(frozen=True)
class AppendResult:
    event_id: int
    inserted: bool  # False: dedup hit, nothing written
    consumers: Tuple[str, ...]  # the queues a delivery row was written to
    seqs: Tuple[int, ...] = ()
    held: bool = False  # True: no consumer, waiting on `unassigned`


@dataclass(frozen=True)
class CommitResult:
    committed: int  # the queue's committed offset after this commit
    applied: Tuple[Tuple[int, str], ...]  # (seq, outcome) rows now committed
    pending: Tuple[int, ...]  # seqs whose outcome was `failed`, left pending


@dataclass(frozen=True)
class Lease:
    instance: str
    peer: str
    expires_in: float


@dataclass(frozen=True)
class Claim:
    subject: str
    instance: str
    role: str
    since: str


@dataclass(frozen=True)
class SubjectRow:
    subject: str
    first_seen: str
    claimants: Tuple[Claim, ...]
    events: int
    held: int
    pending: int
    oldest_pending_at: Optional[str]
    dead: int


@dataclass(frozen=True)
class QueueRow:
    instance: str
    committed: int
    backlog: int
    oldest_pending_at: Optional[str]
    dead: int


@dataclass(frozen=True)
class InstanceRow:
    instance: str
    peer: str
    committed: int
    first_seen: str
    last_fetch_at: Optional[str]
    lease_until: float
    actors: Mapping[str, Tuple[str, ...]]
    backlog: int

    def lease_live(self, now: Optional[float] = None) -> bool:
        return self.lease_until > (time.time() if now is None else now)


@dataclass(frozen=True)
class ExpireResult:
    expired: Tuple[Tuple[str, int, str], ...] = ()  # (subject, event_id, instance | "")
    dead_lettered: Tuple[Tuple[str, int, int], ...] = ()  # (instance, seq, event_id)
    deleted_events: int = 0
    deleted_deliveries: int = 0


@dataclass
class DeadLettered:
    instance: str
    seq: int
    event_id: int
    attempts: int


@dataclass
class FetchResult:
    deliveries: List[Delivery]
    committed: int
    redelivered: List[Tuple[int, int, int]] = field(
        default_factory=list
    )  # (seq, event_id, attempt)
    dead_lettered: List[DeadLettered] = field(default_factory=list)


class Store(Protocol):
    """What a replica would need to replace (R11.2). Documented on :class:`SqliteStore`."""

    def append(
        self, env: Envelope, consumers: Sequence[str], *, held_key: str = ""
    ) -> AppendResult: ...
    def fetch(self, instance: str, cursor: int, limit: int) -> FetchResult: ...
    def commit(
        self, instance: str, outcomes: Sequence[Tuple[int, str]]
    ) -> Union[CommitResult, Refused]: ...
    def touch(
        self, instance: str, peer: str, lease_s: float
    ) -> Union[Lease, Refused]: ...
    def peer_conflict(self, instance: str, peer: str) -> Optional[Refused]: ...
    def claim(self, subject: str, instance: str, role: str) -> List[int]: ...
    def release(
        self, subject: str, instance: str, role: Optional[str] = None
    ) -> int: ...
    def claimants(self, subject: str) -> List[Claim]: ...
    def register_actors(
        self, instance: str, actors: Mapping[str, Sequence[str]], peer: str = ""
    ) -> Optional[Refused]: ...
    def instance_for_actor(self, provider: str, actor: str) -> Optional[str]: ...
    def route_held_by_actors(self, instance: str) -> List[Tuple[int, str]]: ...
    def bind(
        self, provider: str, key: str, ref: str, slug: str, own_subject: str = ""
    ) -> List[int]: ...
    def resolve(self, provider: str, key: str) -> Optional[str]: ...
    def resolve_slug(self, provider: str, key: str) -> Optional[Tuple[str, str]]: ...
    def claims_of(self, instance: str) -> List[Claim]: ...
    def actors_of(self, instance: str) -> Dict[str, Tuple[str, ...]]: ...
    def committed(self, instance: str) -> int: ...
    def event_of_seq(self, seq: int) -> Optional[Envelope]: ...
    def queue(self, instance: str) -> QueueRow: ...
    def poll_seen(self, ref: str, delivery_id: str) -> bool: ...
    def poll_mark_seen(self, ref: str, delivery_id: str) -> None: ...
    def poll_known(self, ref: str) -> bool: ...
    def poll_state(self, ref: str) -> str: ...
    def set_poll_state(self, ref: str, state: str) -> None: ...
    def has_pending_presence(self, ref: str) -> bool: ...
    def poll_refs(self) -> List[str]: ...
    def subjects(self) -> List[SubjectRow]: ...
    def queues(self) -> List[QueueRow]: ...
    def instances(self) -> List[InstanceRow]: ...
    def expire(self, now: Optional[float] = None) -> ExpireResult: ...
    def wait(self, instance: str, timeout: float) -> bool: ...
    def wake_all(self) -> None: ...


_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject TEXT NOT NULL,
  provider TEXT NOT NULL,
  source TEXT NOT NULL,
  kind TEXT NOT NULL,
  delivery_id TEXT NOT NULL,
  dedup_key TEXT NOT NULL UNIQUE,
  work_item TEXT,
  actor TEXT,
  headers_json TEXT NOT NULL,
  payload BLOB NOT NULL,
  received_at TEXT NOT NULL,
  routed INTEGER NOT NULL DEFAULT 0,
  held_key TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS events_subject ON events(subject, id);
CREATE INDEX IF NOT EXISTS events_held ON events(routed, provider, held_key);
CREATE TABLE IF NOT EXISTS deliveries (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL REFERENCES events(id),
  instance TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'pending',
  outcome TEXT,
  created_at TEXT NOT NULL,
  fetched_at TEXT,
  committed_at TEXT
);
CREATE INDEX IF NOT EXISTS deliveries_queue ON deliveries(instance, seq);
CREATE INDEX IF NOT EXISTS deliveries_event ON deliveries(event_id);
CREATE TABLE IF NOT EXISTS instances (
  instance TEXT PRIMARY KEY,
  peer TEXT NOT NULL DEFAULT '',
  committed INTEGER NOT NULL DEFAULT 0,
  first_seen TEXT NOT NULL,
  last_fetch_at TEXT,
  lease_until REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS claims (
  subject TEXT NOT NULL,
  instance TEXT NOT NULL,
  role TEXT NOT NULL,
  since TEXT NOT NULL,
  PRIMARY KEY (subject, instance, role)
);
CREATE TABLE IF NOT EXISTS actors (
  provider TEXT NOT NULL,
  actor TEXT NOT NULL,
  instance TEXT NOT NULL,
  since TEXT NOT NULL,
  PRIMARY KEY (provider, actor)
);
CREATE TABLE IF NOT EXISTS subjects (
  subject TEXT PRIMARY KEY,
  first_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bindings (
  provider TEXT NOT NULL,
  key TEXT NOT NULL,
  ref TEXT NOT NULL,
  slug TEXT NOT NULL,
  published_at TEXT NOT NULL,
  PRIMARY KEY (provider, key)
);
CREATE TABLE IF NOT EXISTS poll_ledger (
  ref TEXT PRIMARY KEY,
  presence_state TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS poll_seen (
  ref TEXT NOT NULL,
  delivery_id TEXT NOT NULL,
  seen_at TEXT NOT NULL,
  PRIMARY KEY (ref, delivery_id)
);
CREATE TABLE IF NOT EXISTS dedup_keys (
  dedup_key TEXT PRIMARY KEY,
  retired_at TEXT NOT NULL
);
"""


class SqliteStore:
    """The file-backed store. See the module docstring for the invariants."""

    def __init__(
        self,
        path: Union[str, Path],
        *,
        retention_days: int = 7,
        max_attempts: int = 3,
        dedup_window: int = 10_000,
    ) -> None:
        self.path = Path(path)
        self.retention_s = float(retention_days) * 86_400.0
        self.max_attempts = max(1, int(max_attempts))
        self.dedup_window = max(0, int(dedup_window))
        self._local = threading.local()
        self._cond_lock = threading.Lock()
        self._conditions: Dict[str, threading.Condition] = {}
        self._closing = False
        self._woken: Set[str] = set()  # a notify nobody was waiting for (R5)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._memory_conn: Optional[sqlite3.Connection] = None
        self._memory_lock = threading.RLock()
        # executescript commits on its own, so the schema runs outside _tx().
        conn = self._connect()
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )

    # -- connections ----------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            # One shared in-memory database for tests: a per-thread connection would
            # see its own empty database.
            if self._memory_conn is None:
                self._memory_conn = sqlite3.connect(
                    ":memory:", check_same_thread=False, isolation_level=None
                )
            return self._memory_conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=30.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Cursor]:
        conn = self._connect()
        lock = self._memory_lock if str(self.path) == ":memory:" else None
        if lock is not None:
            lock.acquire()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            try:
                yield cur
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                cur.close()
        finally:
            if lock is not None:
                lock.release()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
        if self._memory_conn is not None:
            self._memory_conn.close()
            self._memory_conn = None

    # -- the condition that wakes long-polls (the one in-memory thing) ---------------------

    def _condition(self, instance: str) -> threading.Condition:
        with self._cond_lock:
            cond = self._conditions.get(instance)
            if cond is None:
                cond = self._conditions[instance] = threading.Condition()
            return cond

    def _notify(self, instances: Sequence[str]) -> None:
        for instance in set(instances):
            cond = self._condition(instance)
            with cond:
                # the flag outlives the notify: a fetch that read an empty queue just
                # before this append must not sleep its whole `wait` (self-review R5)
                self._woken.add(instance)
                cond.notify_all()

    def wait(self, instance: str, timeout: float) -> bool:
        """Block until ``append``/``claim``/``bind`` routes something to ``instance`` or
        ``timeout`` elapses. Returns whether a wake-up happened. The caller re-reads
        either way: a wake-up is a hint, the queue is the truth."""
        if self._closing:
            return True
        cond = self._condition(instance)
        with cond:
            if self._closing:
                return True
            if instance in self._woken:
                self._woken.discard(instance)
                return True
            woke = cond.wait(timeout=max(0.0, timeout))
            self._woken.discard(instance)
            return woke

    def wake_all(self) -> None:
        """Release every long-poll now and let none block from here on — the first
        thing a shutdown does, so an open fetch cannot hold the process past its
        stop timeout (R8.5)."""
        with self._cond_lock:
            self._closing = True
            conds = list(self._conditions.values())
        for cond in conds:
            with cond:
                cond.notify_all()

    # -- append (R2.1, R2.4, R2.6, R4.1) -------------------------------------------------------

    def append(
        self, env: Envelope, consumers: Sequence[str], *, held_key: str = ""
    ) -> AppendResult:
        """Store ``env`` once (``dedup_key`` is UNIQUE) and fan it out to ``consumers``.

        ``consumers`` empty → the event is **held** (``routed = 0``) until a claim or
        binding covers it (R2.2); ``held_key`` is what a later ``bind`` matches against
        (a pull request's number, a Slack thread). Returns ``inserted=False`` on a dedup
        hit, with the existing row's id and no new deliveries (R2.6, R7.3).
        """
        dedup_key = _dedup_key_of(env)
        consumers = tuple(dict.fromkeys(c for c in consumers if c))
        now = utcnow()
        with self._tx() as cur:
            cur.execute("SELECT 1 FROM dedup_keys WHERE dedup_key = ?", (dedup_key,))
            if cur.fetchone() is not None:
                return AppendResult(event_id=0, inserted=False, consumers=())
            cur.execute("SELECT id FROM events WHERE dedup_key = ?", (dedup_key,))
            row = cur.fetchone()
            if row is not None:
                return AppendResult(event_id=int(row[0]), inserted=False, consumers=())
            cur.execute(
                "INSERT INTO events(subject, provider, source, kind, delivery_id, dedup_key,"
                " work_item, actor, headers_json, payload, received_at, routed, held_key)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    env.subject,
                    env.provider,
                    env.source,
                    env.kind,
                    env.delivery_id,
                    dedup_key,
                    env.work_item,
                    env.actor,
                    json.dumps(dict(env.headers), separators=(",", ":")),
                    env.payload_bytes(),
                    env.received_at or now,
                    1 if consumers else 0,
                    held_key or "",
                ),
            )
            event_id = int(cur.lastrowid or 0)
            cur.execute(
                "INSERT OR IGNORE INTO subjects(subject, first_seen) VALUES (?, ?)",
                (env.subject, now),
            )
            seqs = self._fan_out(cur, event_id, consumers, now)
        self._notify(consumers)
        return AppendResult(
            event_id=event_id,
            inserted=True,
            consumers=consumers,
            seqs=tuple(seqs),
            held=not consumers,
        )

    def _fan_out(
        self, cur: sqlite3.Cursor, event_id: int, consumers: Sequence[str], now: str
    ) -> List[int]:
        seqs: List[int] = []
        for instance in consumers:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            cur.execute(
                "INSERT INTO deliveries(event_id, instance, created_at) VALUES (?, ?, ?)",
                (event_id, instance, now),
            )
            seqs.append(int(cur.lastrowid or 0))
        return seqs

    # -- fetch (R3.2, R3.6) ----------------------------------------------------------------------

    def fetch(self, instance: str, cursor: int, limit: int) -> FetchResult:
        """This instance's pending deliveries after ``max(cursor, committed)``, oldest
        first, at most ``limit``, each with ``attempts`` incremented. A delivery already
        fetched ``max_attempts`` times is dead-lettered here instead of returned (R3.6).

        The cursor is a hint: the client sends the ``committed`` the server last
        returned, so a `failed` outcome (left pending) is re-read, and a client with no
        memory sends 0 and reads from ``committed``.
        """
        now = utcnow()
        limit = max(1, int(limit))
        result = FetchResult(deliveries=[], committed=0)
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            cur.execute(
                "SELECT committed FROM instances WHERE instance = ?", (instance,)
            )
            committed = int(cur.fetchone()[0])
            start = max(int(cursor or 0), committed)
            # dead-letter what has exhausted its attempts
            cur.execute(
                "SELECT seq, event_id, attempts FROM deliveries"
                " WHERE instance = ? AND state = ? AND attempts >= ? AND seq > ?",
                (instance, PENDING, self.max_attempts, start),
            )
            for seq, event_id, attempts in cur.fetchall():
                cur.execute(
                    "UPDATE deliveries SET state = ?, outcome = ?, committed_at = ?"
                    " WHERE seq = ?",
                    (DEAD, DEAD_LETTERED, now, seq),
                )
                result.dead_lettered.append(
                    DeadLettered(instance, int(seq), int(event_id), int(attempts))
                )
            cur.execute(
                "SELECT d.seq, d.attempts, e.id, e.subject, e.provider, e.source, e.kind,"
                " e.delivery_id, e.work_item, e.headers_json, e.payload, e.received_at"
                " FROM deliveries d JOIN events e ON e.id = d.event_id"
                " WHERE d.instance = ? AND d.state = ? AND d.seq > ?"
                " ORDER BY d.seq LIMIT ?",
                (instance, PENDING, start, limit),
            )
            rows = cur.fetchall()
            for row in rows:
                seq, attempts = int(row[0]), int(row[1]) + 1
                cur.execute(
                    "UPDATE deliveries SET attempts = ?, fetched_at = ? WHERE seq = ?",
                    (attempts, now, seq),
                )
                env = _envelope_from_row(row[2:], attempt=attempts)
                result.deliveries.append(
                    Delivery(seq=seq, attempt=attempts, event=env, subject=env.subject)
                )
                if attempts > 1:
                    result.redelivered.append((seq, int(row[2]), attempts))
            cur.execute(
                "UPDATE instances SET last_fetch_at = ? WHERE instance = ?",
                (now, instance),
            )
            if result.dead_lettered:
                committed = self._advance(cur, instance)
            result.committed = committed
        return result

    # -- commit (R3.4, R3.5; abuse case 5) ---------------------------------------------------------

    def commit(
        self, instance: str, outcomes: Sequence[Tuple[int, str]]
    ) -> Union[CommitResult, Refused]:
        """Record each ``(seq, outcome)`` and advance ``committed`` contiguously.

        Every ``seq`` must be a delivery of **this** queue that was fetched; otherwise
        nothing is applied and ``Refused("commit-undelivered")`` names the first offender
        (abuse case 5). ``failed`` leaves its row pending, so a later fetch returns it
        with ``attempt + 1``. Re-committing an already committed seq is idempotent.
        """
        now = utcnow()
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            for seq, outcome in outcomes:
                if not isinstance(outcome, str) or not is_outcome(outcome):
                    return Refused(
                        "commit-undelivered",
                        detail=f"seq {seq}: unknown outcome {outcome!r}",
                    )
                cur.execute(
                    "SELECT attempts, state FROM deliveries WHERE seq = ? AND instance = ?",
                    (int(seq), instance),
                )
                row = cur.fetchone()
                if row is None or int(row[0]) == 0:
                    return Refused(
                        "commit-undelivered",
                        detail=f"seq {seq} was never delivered to {instance}",
                    )
            applied: List[Tuple[int, str]] = []
            pending: List[int] = []
            for seq, outcome in outcomes:
                if outcome.split(":", 1)[0] == "failed":
                    cur.execute(
                        "UPDATE deliveries SET outcome = ? WHERE seq = ? AND state = ?",
                        (outcome, int(seq), PENDING),
                    )
                    pending.append(int(seq))
                    continue
                cur.execute(
                    "UPDATE deliveries SET state = ?, outcome = ?, committed_at = ?"
                    " WHERE seq = ? AND state = ?",
                    (COMMITTED, outcome, now, int(seq), PENDING),
                )
                if cur.rowcount:
                    applied.append((int(seq), outcome))
            committed = self._advance(cur, instance)
        return CommitResult(
            committed=committed, applied=tuple(applied), pending=tuple(pending)
        )

    def _advance(self, cur: sqlite3.Cursor, instance: str) -> int:
        """``committed`` = the highest seq below which nothing of this queue is pending.
        Never decreases."""
        cur.execute("SELECT committed FROM instances WHERE instance = ?", (instance,))
        current = int(cur.fetchone()[0])
        cur.execute(
            "SELECT MIN(seq) FROM deliveries WHERE instance = ? AND state = ?",
            (instance, PENDING),
        )
        first_pending = cur.fetchone()[0]
        if first_pending is None:
            cur.execute(
                "SELECT MAX(seq) FROM deliveries WHERE instance = ?", (instance,)
            )
            top = cur.fetchone()[0]
            new = int(top) if top is not None else current
        else:
            cur.execute(
                "SELECT MAX(seq) FROM deliveries WHERE instance = ? AND seq < ?",
                (instance, int(first_pending)),
            )
            top = cur.fetchone()[0]
            new = int(top) if top is not None else current
        new = max(new, current)
        if new != current:
            cur.execute(
                "UPDATE instances SET committed = ? WHERE instance = ?", (new, instance)
            )
        return new

    # -- the lease per instance name, by peer (R4.3; abuse case 4) -------------------------------

    def touch(self, instance: str, peer: str, lease_s: float) -> Union[Lease, Refused]:
        """Record a fetch by ``peer`` under ``instance`` and hold the name for ``lease_s``.

        A **different** peer while the lease is live is ``Refused("duplicate-instance")``
        naming the holder; the same peer (a restart persists its id) is admitted at once,
        and an expired lease admits anyone. ``peer`` empty means an unidentified client,
        which never holds the name and is admitted only while nobody does.
        """
        now_s = time.time()
        now = utcnow()
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            refused = self._other_peer_holds(cur, instance, peer, now_s)
            if refused is not None:
                return refused
            expires = now_s + max(0.0, float(lease_s))
            cur.execute(
                "UPDATE instances SET peer = ?, lease_until = ?, last_fetch_at = ?"
                " WHERE instance = ?",
                (peer or "", expires if peer else 0.0, now, instance),
            )
        return Lease(instance=instance, peer=peer, expires_in=max(0.0, expires - now_s))

    @staticmethod
    def _other_peer_holds(
        cur: sqlite3.Cursor, instance: str, peer: str, now_s: float
    ) -> Optional[Refused]:
        """``Refused("duplicate-instance")`` when ``instance``'s name is held by a
        different peer whose lease is live; the row must exist."""
        cur.execute(
            "SELECT peer, lease_until, first_seen FROM instances WHERE instance = ?",
            (instance,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        holder, lease_until, first_seen = row
        if holder and holder != peer and float(lease_until) > now_s:
            return Refused(
                "duplicate-instance",
                holder=str(holder),
                since=str(first_seen),
                detail=f"{instance} is being polled by another peer",
            )
        return None

    def peer_conflict(self, instance: str, peer: str) -> Optional[Refused]:
        """The fetch's peer rule for the writes that are not a fetch — commit, claim,
        release (self-review R6): a stale peer under a live name may not commit the
        live peer's seqs or release its claims. Refreshes nothing."""
        with self._tx() as cur:
            return self._other_peer_holds(cur, instance, peer, time.time())

    def _lease_live(self, cur: sqlite3.Cursor, instance: str, now_s: float) -> bool:
        cur.execute("SELECT lease_until FROM instances WHERE instance = ?", (instance,))
        row = cur.fetchone()
        return row is not None and float(row[0]) > now_s

    # -- claims (R5.3, R2.2) -------------------------------------------------------------------

    def claim(self, subject: str, instance: str, role: str) -> List[int]:
        """Record that ``instance`` consumes ``subject`` as ``role`` and route the events
        held on it (``routed = 0``) onto that queue, in the same transaction. Returns the
        ids routed. Idempotent for an existing claim."""
        now = utcnow()
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            cur.execute(
                "INSERT OR IGNORE INTO subjects(subject, first_seen) VALUES (?, ?)",
                (subject, now),
            )
            cur.execute(
                "INSERT OR IGNORE INTO claims(subject, instance, role, since)"
                " VALUES (?, ?, ?, ?)",
                (subject, instance, role, now),
            )
            routed = self._route_held(cur, subject, [instance], now)
        if routed:
            self._notify([instance])
        return routed

    def _route_held(
        self, cur: sqlite3.Cursor, subject: str, consumers: Sequence[str], now: str
    ) -> List[int]:
        cur.execute(
            "SELECT id FROM events WHERE subject = ? AND routed = 0 ORDER BY id",
            (subject,),
        )
        ids = [int(r[0]) for r in cur.fetchall()]
        for event_id in ids:
            self._fan_out(cur, event_id, consumers, now)
            cur.execute("UPDATE events SET routed = 1 WHERE id = ?", (event_id,))
        return ids

    def release(self, subject: str, instance: str, role: Optional[str] = None) -> int:
        with self._tx() as cur:
            if role is None:
                cur.execute(
                    "DELETE FROM claims WHERE subject = ? AND instance = ?",
                    (subject, instance),
                )
            else:
                cur.execute(
                    "DELETE FROM claims WHERE subject = ? AND instance = ? AND role = ?",
                    (subject, instance, role),
                )
            return int(cur.rowcount)

    def claimants(self, subject: str) -> List[Claim]:
        with self._tx() as cur:
            cur.execute(
                "SELECT subject, instance, role, since FROM claims WHERE subject = ?"
                " ORDER BY since, instance",
                (subject,),
            )
            return [Claim(*row) for row in cur.fetchall()]

    def claims_of(self, instance: str) -> List[Claim]:
        with self._tx() as cur:
            cur.execute(
                "SELECT subject, instance, role, since FROM claims WHERE instance = ?"
                " ORDER BY since",
                (instance,),
            )
            return [Claim(*row) for row in cur.fetchall()]

    # -- actors (R5.5; abuse case 8) --------------------------------------------------------------

    def register_actors(
        self, instance: str, actors: Mapping[str, Sequence[str]], peer: str = ""
    ) -> Optional[Refused]:
        """Replace ``instance``'s registration. An actor held by **another** instance
        whose lease is live is ``Refused("duplicate-actor")`` naming the holder, and
        nothing is applied; an expired holder is taken over. A **different peer** under
        a name whose lease is live is ``Refused("duplicate-instance")`` before anything
        is read (R4.3): the second peer's fetch would be refused, so its registration
        must not replace the live instance's actors either."""
        now = utcnow()
        now_s = time.time()
        wanted = [
            (provider, str(actor))
            for provider, names in actors.items()
            for actor in names
            if actor
        ]
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO instances(instance, first_seen) VALUES (?, ?)",
                (instance, now),
            )
            refused = self._other_peer_holds(cur, instance, peer, now_s)
            if refused is not None:
                return refused
            for provider, actor in wanted:
                cur.execute(
                    "SELECT instance FROM actors WHERE provider = ? AND actor = ?",
                    (provider, actor),
                )
                row = cur.fetchone()
                if row and row[0] != instance and self._lease_live(cur, row[0], now_s):
                    return Refused(
                        "duplicate-actor",
                        holder=str(row[0]),
                        detail=f"{provider}:{actor} is registered by {row[0]}",
                    )
            cur.execute("DELETE FROM actors WHERE instance = ?", (instance,))
            for provider, actor in wanted:
                cur.execute(
                    "INSERT OR REPLACE INTO actors(provider, actor, instance, since)"
                    " VALUES (?, ?, ?, ?)",
                    (provider, actor, instance, now),
                )
        return None

    def route_held_by_actors(self, instance: str) -> List[Tuple[int, str]]:
        """Route onto ``instance``'s queue every held event whose actor it now
        registers (R2.2: an actor registration routes what was held for it — the
        event that arrived before the instance registered). Returns
        ``(event_id, subject)`` per event routed (self-review R4)."""
        now = utcnow()
        routed: List[Tuple[int, str]] = []
        with self._tx() as cur:
            cur.execute(
                "SELECT provider, actor FROM actors WHERE instance = ?", (instance,)
            )
            wanted = [(str(p), str(a)) for p, a in cur.fetchall()]
            for provider, actor in wanted:
                cur.execute(
                    "SELECT id, subject FROM events WHERE routed = 0 AND provider = ?"
                    " AND actor = ? ORDER BY id",
                    (provider, actor),
                )
                for event_id, subject in cur.fetchall():
                    self._fan_out(cur, int(event_id), [instance], now)
                    cur.execute(
                        "UPDATE events SET routed = 1 WHERE id = ?", (int(event_id),)
                    )
                    routed.append((int(event_id), str(subject)))
        if routed:
            self._notify([instance])
        return routed

    def instance_for_actor(self, provider: str, actor: str) -> Optional[str]:
        if not actor:
            return None
        with self._tx() as cur:
            cur.execute(
                "SELECT instance FROM actors WHERE provider = ? AND actor = ?",
                (provider, actor),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None

    def actors_of(self, instance: str) -> Dict[str, Tuple[str, ...]]:
        with self._tx() as cur:
            return self._actors_of(cur, instance)

    @staticmethod
    def _actors_of(cur: sqlite3.Cursor, instance: str) -> Dict[str, Tuple[str, ...]]:
        cur.execute(
            "SELECT provider, actor FROM actors WHERE instance = ? ORDER BY provider, actor",
            (instance,),
        )
        out: Dict[str, List[str]] = {}
        for provider, actor in cur.fetchall():
            out.setdefault(str(provider), []).append(str(actor))
        return {k: tuple(v) for k, v in out.items()}

    # -- bindings (R5.7, R5.8) ---------------------------------------------------------------------

    def bind(
        self, provider: str, key: str, ref: str, slug: str, own_subject: str = ""
    ) -> List[int]:
        """Record that ``(provider, key)`` belongs to work item ``ref`` (subject
        ``loop-<slug>``) and route the events held under that key — and, when the
        bound object has a subject of its own (``own_subject``, a pull request's), the
        events held there (critic C3, R5.7) — onto the subject's claimants, else the
        event's actor's instance, else they stay held. Returns the ids routed."""
        now = utcnow()
        subject = subject_for_slug(slug)
        routed: List[int] = []
        consumers_touched: List[str] = []
        with self._tx() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO bindings(provider, key, ref, slug, published_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (provider, key, ref, slug, now),
            )
            cur.execute(
                "INSERT OR IGNORE INTO subjects(subject, first_seen) VALUES (?, ?)",
                (subject, now),
            )
            cur.execute(
                "SELECT subject, instance, role, since FROM claims WHERE subject = ?",
                (subject,),
            )
            claimants = [str(r[1]) for r in cur.fetchall()]
            cur.execute(
                "SELECT id, actor FROM events WHERE routed = 0 AND provider = ?"
                " AND held_key = ? ORDER BY id",
                (provider, key),
            )
            held = [(int(r[0]), r[1], True) for r in cur.fetchall()]
            if own_subject and own_subject != subject:
                cur.execute(
                    "SELECT id, actor FROM events WHERE routed = 0 AND provider = ?"
                    " AND subject = ? ORDER BY id",
                    (provider, own_subject),
                )
                held.extend((int(r[0]), r[1], False) for r in cur.fetchall())
            for event_id, actor, re_subject in held:
                if re_subject:
                    # held under a key with no subject of its own: it takes the work item's
                    cur.execute(
                        "UPDATE events SET subject = ?, work_item = ? WHERE id = ?",
                        (subject, ref, int(event_id)),
                    )
                consumers = list(dict.fromkeys(claimants))
                if not consumers and actor:
                    cur.execute(
                        "SELECT instance FROM actors WHERE provider = ? AND actor = ?",
                        (provider, str(actor)),
                    )
                    row = cur.fetchone()
                    if row:
                        consumers = [str(row[0])]
                if consumers:
                    self._fan_out(cur, int(event_id), consumers, now)
                    cur.execute(
                        "UPDATE events SET routed = 1 WHERE id = ?", (int(event_id),)
                    )
                    routed.append(int(event_id))
                    consumers_touched.extend(consumers)
        if consumers_touched:
            self._notify(consumers_touched)
        return routed

    def resolve(self, provider: str, key: str) -> Optional[str]:
        with self._tx() as cur:
            cur.execute(
                "SELECT ref FROM bindings WHERE provider = ? AND key = ?",
                (provider, key),
            )
            row = cur.fetchone()
            return str(row[0]) if row else None

    def resolve_slug(self, provider: str, key: str) -> Optional[Tuple[str, str]]:
        with self._tx() as cur:
            cur.execute(
                "SELECT ref, slug FROM bindings WHERE provider = ? AND key = ?",
                (provider, key),
            )
            row = cur.fetchone()
            return (str(row[0]), str(row[1])) if row else None

    # -- the poll ledger, relocated (design §gateway/adapters/poll.py) ----------------------------

    def poll_seen(self, ref: str, delivery_id: str) -> bool:
        with self._tx() as cur:
            cur.execute(
                "SELECT 1 FROM poll_seen WHERE ref = ? AND delivery_id = ?",
                (ref, delivery_id),
            )
            return cur.fetchone() is not None

    def poll_mark_seen(self, ref: str, delivery_id: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR IGNORE INTO poll_seen(ref, delivery_id, seen_at) VALUES (?, ?, ?)",
                (ref, delivery_id, utcnow()),
            )

    def has_pending_presence(self, ref: str) -> bool:
        """Whether a presence event for ``ref`` is still on some queue, uncommitted, or
        held with no consumer yet — the poll adapter re-emits presence only once the
        previous one was judged (self-review R1: a held presence counts, else every
        cycle would add one more until retention)."""
        with self._tx() as cur:
            cur.execute(
                "SELECT 1 FROM deliveries d JOIN events e ON e.id = d.event_id"
                " WHERE e.work_item = ? AND e.source = 'poll' AND d.state = ?"
                " AND e.delivery_id LIKE 'poll-presence-%' LIMIT 1",
                (ref, PENDING),
            )
            if cur.fetchone() is not None:
                return True
            cur.execute(
                "SELECT 1 FROM events WHERE work_item = ? AND source = 'poll'"
                " AND routed = 0 AND delivery_id LIKE 'poll-presence-%' LIMIT 1",
                (ref,),
            )
            return cur.fetchone() is not None

    def poll_refs(self) -> List[str]:
        """Every ref the poll ledger knows that is not closed — what a listing is
        reconciled against."""
        with self._tx() as cur:
            cur.execute(
                "SELECT ref FROM poll_ledger WHERE presence_state != 'closed' ORDER BY ref"
            )
            return [str(r[0]) for r in cur.fetchall()]

    def poll_known(self, ref: str) -> bool:
        """Whether the ledger has ever recorded ``ref`` — false exactly once, at the
        poller's first sight of an item, when its existing thread is baselined rather
        than stored (the instance poller's rule, kept across the process boundary)."""
        with self._tx() as cur:
            cur.execute("SELECT 1 FROM poll_ledger WHERE ref = ?", (ref,))
            return cur.fetchone() is not None

    def poll_state(self, ref: str) -> str:
        with self._tx() as cur:
            cur.execute("SELECT presence_state FROM poll_ledger WHERE ref = ?", (ref,))
            row = cur.fetchone()
            return str(row[0]) if row else "unknown"

    def set_poll_state(self, ref: str, state: str) -> None:
        with self._tx() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO poll_ledger(ref, presence_state, updated_at)"
                " VALUES (?, ?, ?)",
                (ref, state, utcnow()),
            )

    # -- the read-only views (R9.2) ------------------------------------------------------------------

    def subjects(self) -> List[SubjectRow]:
        with self._tx() as cur:
            cur.execute("SELECT subject, first_seen FROM subjects ORDER BY first_seen")
            rows = cur.fetchall()
            out: List[SubjectRow] = []
            for subject, first_seen in rows:
                cur.execute(
                    "SELECT subject, instance, role, since FROM claims WHERE subject = ?"
                    " ORDER BY since",
                    (subject,),
                )
                claims = tuple(Claim(*r) for r in cur.fetchall())
                cur.execute(
                    "SELECT COUNT(*), SUM(routed = 0) FROM events WHERE subject = ?",
                    (subject,),
                )
                events, held = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*), MIN(d.created_at) FROM deliveries d"
                    " JOIN events e ON e.id = d.event_id"
                    " WHERE e.subject = ? AND d.state = ?",
                    (subject, PENDING),
                )
                pending, oldest = cur.fetchone()
                cur.execute(
                    "SELECT COUNT(*) FROM deliveries d JOIN events e ON e.id = d.event_id"
                    " WHERE e.subject = ? AND d.state = ?",
                    (subject, DEAD),
                )
                (dead,) = cur.fetchone()
                out.append(
                    SubjectRow(
                        subject=str(subject),
                        first_seen=str(first_seen),
                        claimants=claims,
                        events=int(events or 0),
                        held=int(held or 0),
                        pending=int(pending or 0),
                        oldest_pending_at=oldest,
                        dead=int(dead or 0),
                    )
                )
            return out

    def queues(self) -> List[QueueRow]:
        with self._tx() as cur:
            cur.execute("SELECT instance, committed FROM instances ORDER BY instance")
            rows = cur.fetchall()
            return [self._queue_row(cur, str(i), int(c)) for i, c in rows]

    @staticmethod
    def _queue_row(cur: sqlite3.Cursor, instance: str, committed: int) -> QueueRow:
        cur.execute(
            "SELECT COUNT(*), MIN(created_at) FROM deliveries"
            " WHERE instance = ? AND state = ?",
            (instance, PENDING),
        )
        backlog, oldest = cur.fetchone()
        cur.execute(
            "SELECT COUNT(*) FROM deliveries WHERE instance = ? AND state = ?",
            (instance, DEAD),
        )
        (dead,) = cur.fetchone()
        return QueueRow(
            instance=instance,
            committed=committed,
            backlog=int(backlog or 0),
            oldest_pending_at=oldest,
            dead=int(dead or 0),
        )

    def queue(self, instance: str) -> QueueRow:
        with self._tx() as cur:
            cur.execute(
                "SELECT committed FROM instances WHERE instance = ?", (instance,)
            )
            row = cur.fetchone()
            return self._queue_row(cur, instance, int(row[0]) if row else 0)

    def instances(self) -> List[InstanceRow]:
        with self._tx() as cur:
            cur.execute(
                "SELECT instance, peer, committed, first_seen, last_fetch_at, lease_until"
                " FROM instances ORDER BY instance"
            )
            rows = cur.fetchall()
            out: List[InstanceRow] = []
            for instance, peer, committed, first_seen, last_fetch, lease_until in rows:
                queue = self._queue_row(cur, str(instance), int(committed))
                out.append(
                    InstanceRow(
                        instance=str(instance),
                        peer=str(peer or ""),
                        committed=int(committed),
                        first_seen=str(first_seen),
                        last_fetch_at=last_fetch,
                        lease_until=float(lease_until or 0),
                        actors=self._actors_of(cur, str(instance)),
                        backlog=queue.backlog,
                    )
                )
            return out

    # -- retention (R2.8; abuse case 6) ---------------------------------------------------------------

    def expire(self, now: Optional[float] = None) -> ExpireResult:
        """Apply retention: delete committed deliveries older than ``retention``, dead
        rows after twice that, expire pending deliveries and held events older than
        ``retention`` (recorded as ``subject.expired`` by the caller), and delete an event
        with no remaining deliveries — retiring its dedup key into a bounded table so a
        provider's late redelivery is still recognised."""
        now_s = time.time() if now is None else now
        cutoff = _iso(now_s - self.retention_s)
        dead_cutoff = _iso(now_s - 2 * self.retention_s)
        expired: List[Tuple[str, int, str]] = []
        with self._tx() as cur:
            cur.execute(
                "DELETE FROM deliveries WHERE state = ? AND committed_at < ?",
                (COMMITTED, cutoff),
            )
            deleted = int(cur.rowcount)
            cur.execute(
                "DELETE FROM deliveries WHERE state = ? AND committed_at < ?",
                (DEAD, dead_cutoff),
            )
            deleted += int(cur.rowcount)
            cur.execute(
                "SELECT d.seq, d.instance, e.subject, e.id FROM deliveries d"
                " JOIN events e ON e.id = d.event_id"
                " WHERE d.state = ? AND d.created_at < ?",
                (PENDING, cutoff),
            )
            stale = cur.fetchall()
            for seq, instance, subject, event_id in stale:
                cur.execute("DELETE FROM deliveries WHERE seq = ?", (int(seq),))
                expired.append((str(subject), int(event_id), str(instance)))
                deleted += 1
            for _seq, instance, _subject, _event_id in stale:
                self._advance(cur, str(instance))
            cur.execute(
                "SELECT id, subject FROM events WHERE routed = 0 AND received_at < ?",
                (cutoff,),
            )
            for event_id, subject in cur.fetchall():
                expired.append((str(subject), int(event_id), ""))
                cur.execute(
                    "UPDATE events SET routed = 1 WHERE id = ?", (int(event_id),)
                )
            # events with no remaining deliveries go, their key retired
            cur.execute(
                "SELECT id, dedup_key FROM events e WHERE routed = 1"
                " AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.event_id = e.id)"
            )
            gone = cur.fetchall()
            retired_at = _iso(now_s)
            for event_id, dedup_key in gone:
                cur.execute("DELETE FROM events WHERE id = ?", (int(event_id),))
                cur.execute(
                    "INSERT OR REPLACE INTO dedup_keys(dedup_key, retired_at) VALUES (?, ?)",
                    (str(dedup_key), retired_at),
                )
            if self.dedup_window >= 0:
                cur.execute(
                    "DELETE FROM dedup_keys WHERE dedup_key NOT IN"
                    " (SELECT dedup_key FROM dedup_keys ORDER BY retired_at DESC LIMIT ?)",
                    (self.dedup_window,),
                )
        return ExpireResult(
            expired=tuple(expired),
            deleted_events=len(gone),
            deleted_deliveries=deleted,
        )

    # -- views used by the API and the verbs ------------------------------------------------------

    def committed(self, instance: str) -> int:
        with self._tx() as cur:
            cur.execute(
                "SELECT committed FROM instances WHERE instance = ?", (instance,)
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def event_of_seq(self, seq: int) -> Optional[Envelope]:
        with self._tx() as cur:
            cur.execute("SELECT event_id FROM deliveries WHERE seq = ?", (int(seq),))
            row = cur.fetchone()
        return self.event(int(row[0])) if row else None

    def event(self, event_id: int) -> Optional[Envelope]:
        with self._tx() as cur:
            cur.execute(
                "SELECT id, subject, provider, source, kind, delivery_id, work_item,"
                " headers_json, payload, received_at FROM events WHERE id = ?",
                (int(event_id),),
            )
            row = cur.fetchone()
        return _envelope_from_row(row, attempt=1) if row else None

    def schema_version(self) -> int:
        with self._tx() as cur:
            cur.execute("SELECT value FROM meta WHERE key = 'schema_version'")
            row = cur.fetchone()
        return int(row[0]) if row else 0

    def query_plan(self, instance: str) -> str:
        """The plan of the fetch's range read, for the scalability budget (T7)."""
        with self._tx() as cur:
            cur.execute(
                "EXPLAIN QUERY PLAN SELECT d.seq FROM deliveries d"
                " WHERE d.instance = ? AND d.state = ? AND d.seq > ? ORDER BY d.seq LIMIT ?",
                (instance, PENDING, 0, 64),
            )
            return "\n".join(str(r[-1]) for r in cur.fetchall())


# -- helpers ---------------------------------------------------------------------------------


def _dedup_key_of(env: Envelope) -> str:
    """The adapter's cross-transport key (R7.3), else ``<provider>:<deliveryId>``."""
    return env.dedup_key or f"{env.provider}:{env.delivery_id}"


def _iso(seconds: float) -> str:
    from datetime import datetime, timezone

    return (
        datetime.fromtimestamp(max(0.0, seconds), timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3]
        + "Z"
    )


def _envelope_from_row(row: Sequence[Any], *, attempt: int) -> Envelope:
    (
        event_id,
        subject,
        provider,
        source,
        kind,
        delivery_id,
        work_item,
        headers_json,
        payload,
        received_at,
    ) = row
    raw = bytes(payload) if payload is not None else b"null"
    try:
        decoded: Any = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        decoded = raw.decode("utf-8", "replace")
    return Envelope(
        id=int(event_id),
        subject=str(subject),
        provider=str(provider),
        source=str(source),
        delivery_id=str(delivery_id),
        kind=str(kind),
        payload=decoded,
        work_item=work_item,
        headers=json.loads(headers_json or "{}"),
        received_at=str(received_at),
        attempt=attempt,
    )
