"""Provider-agnostic poll loop driving the existing router/dispatcher (issue-34).

Webhooks are push; the poller is *pull* for hosts a webhook cannot reach. It
periodically asks each configured :class:`PollProvider` for the labelled work
items in its scope and synthesises the same ``RoutedEvent`` shape the webhook
receiver produces — so **all** downstream behaviour is reused unchanged: the
session registry (one session per work item — no duplicate spawns), the
per-session FIFO dispatcher, the tmux runner, the harness adapters and the
prompt templates.

The core knows nothing about GitHub (or any provider): a ``polling.sources``
config entry selects a provider by name, and the provider owns all
provider-specific discovery and event construction. The poller's own
responsibilities are ingress-agnostic:

* **spawn** a session for a labelled item that has none yet (delegated to the
  dispatcher's ``spawnOnUnmatched`` policy) — retried each cycle until it
  exists, so a session is never spawned twice for the same item;
* **forward** genuinely new comments to the matched session, deduped across
  polls/restarts by a durable :class:`PollState`;
* **close** a session whose work item has ended — a listing only ever contains
  *open* items, so the poller reconciles the registry against it and asks the
  provider about anything that disappeared (issue-94).

Spec: docs/specs/issue-34/design.md; docs/specs/issue-94/design.md.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .. import __version__, eventlog
from ..authz import is_authorized, is_self_authored
from ..control import ControlConfig, ControlStore, parse_command
from ..reload import Reloader
from ..sessions import SessionRegistry, WorkItemRef
from ..workitem import POLL, WorkItemStore
from ..webhook.dispatcher import Dispatcher
from .base import Comment, PollProvider, ProviderError, WorkItem

logger = logging.getLogger("the-loop.poll")

# Per item, how many comment ids we remember across polls. The set is re-seeded
# from the live comment list every cycle, so this only caps a single very
# chatty thread; the newest comments always stay in the window.
_SEEN_COMMENTS_CAP = 500


@dataclass
class PollConfig:
    """Python mirror of the provider-agnostic ``polling`` config block.

    Per-source (provider) settings live in ``sources``; a provider parses its
    own entry. Dispatch behaviour (registry dir, harness, runner, spawn policy,
    templates) is reused from ``routing``.

    Where the ledger is stored is no longer one of these settings: issue-128 put
    it under ``state.root`` with the rest of the portable state, and retired
    ``polling.stateFile`` (a file where there is now a directory) through the
    version-gated config migration.
    """

    interval_seconds: int = 60
    max_retries: int = 3
    sources: List[dict] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "PollConfig":
        data = data or {}
        return cls(
            interval_seconds=int(data.get("intervalSeconds", 60)),
            max_retries=max(1, int(data.get("maxRetries", 3))),
            sources=[dict(s) for s in (data.get("sources") or []) if s],
        )


class PollState:
    """The poller's per-item ledger — the ``poll`` half of a work-item record.

    It exists so the poller is idempotent across cycles *and* restarts (there is
    no webhook redelivery to lean on), and so a *failed* spawn/forward is retried
    a bounded number of times instead of being baselined as "processed" on the
    first attempt (issue-80). Per work item it tracks:

    - ``seenComments`` — **resolved** comment ids (delivered *or* given up after
      the retry budget), the baseline the poller ignores. Pruned to the live
      thread each cycle so it stays bounded.
    - ``commentAttempts`` — ``{comment_id: attempts}`` for comments still in
      flight (forwarded but not yet confirmed delivered).
    - ``spawn`` — ``{attempts, gaveUp, deliveryId}`` for the presence/spawn
      retry (the presence delivery id is stored so the poller can tell an
      in-flight spawn from a failed one across cycles).
    - ``gaveUp`` — ``{comments, version}``: comments **abandoned** after their
      retry budget was spent, and the CLI version that abandoned them. What makes
      an item stranded by a bug recoverable once the bug is fixed (issue-146);
      without it an abandoned comment is indistinguishable from a delivered one.

    Storage moved in issue-128: one file per work item under
    ``<state.root>/portable/``, written through
    :class:`the_loop.workitem.WorkItemStore`, instead of a single
    ``poll-state.json`` holding every item. Same contents, three consequences —
    it sits beside that item's control record (both are facts about the world),
    two machines now conflict only over an item they *both* worked, and a cycle
    writes only the items it touched. Entries are read lazily and written back at
    the end of a cycle; :meth:`forget` writes through immediately, because a work
    item that ended must not be resurrected by a later flush.
    """

    def __init__(self, store: WorkItemStore):
        self.store = store
        self._items: Dict[str, dict] = {}
        self._dirty: set = set()

    @property
    def root(self) -> Path:
        return self.store.root

    def _read(self, ref: str) -> dict:
        """This item's ledger, loaded on first touch. Never marks it dirty."""
        if ref not in self._items:
            section = self.store.section(ref, POLL)
            if section is None:
                return {}
            self._items[ref] = dict(section)
        return self._items[ref]

    def _item(self, ref: str) -> dict:
        """The ledger to mutate — created if absent, and flushed by `save`."""
        item = self._items.setdefault(ref, dict(self._read(ref)))
        self._dirty.add(ref)
        return item

    def is_known(self, ref: str) -> bool:
        return ref in self._items or self.store.has_section(ref, POLL)

    def seen_comments(self, ref: str) -> set:
        return set(self._read(ref).get("seenComments") or [])

    # -- comment retry ledger ---------------------------------------------------

    def comment_attempts(self, ref: str, comment_id: str) -> int:
        return int((self._read(ref).get("commentAttempts") or {}).get(comment_id, 0))

    def note_comment_attempt(self, ref: str, comment_id: str) -> int:
        """Record one delivery attempt for a comment; return the new count."""
        item = self._item(ref)
        attempts = dict(item.get("commentAttempts") or {})
        attempts[comment_id] = attempts.get(comment_id, 0) + 1
        item["commentAttempts"] = attempts
        return attempts[comment_id]

    def resolve_comment(self, ref: str, comment_id: str, gave_up: bool = False) -> None:
        """Mark a comment done: baseline it, drop its in-flight counter.

        ``gave_up`` distinguishes the two ways a comment becomes "done"
        (issue-146). They used to be recorded identically, which is why an item
        stranded by a bug stayed stranded after the bug was fixed: nothing could
        tell an abandoned comment from a delivered one, so no later cycle would
        ever look at it again. An abandonment is now recorded **with the CLI
        version that gave up**, which :meth:`rearm_gave_up_comments` reads.
        """
        item = self._item(ref)
        seen = list(item.get("seenComments") or [])
        if comment_id not in seen:
            seen.append(comment_id)
        item["seenComments"] = seen[-_SEEN_COMMENTS_CAP:]
        attempts = dict(item.get("commentAttempts") or {})
        attempts.pop(comment_id, None)
        item["commentAttempts"] = attempts
        if not gave_up:
            return
        record = dict(item.get("gaveUp") or {})
        abandoned = [c for c in (record.get("comments") or []) if c != comment_id]
        abandoned.append(comment_id)
        item["gaveUp"] = {
            "comments": abandoned[-_SEEN_COMMENTS_CAP:],
            "version": __version__,
        }

    def rearm_gave_up_comments(self, ref: str) -> List[str]:
        """Un-resolve comments abandoned by a **different** CLI version.

        Returns what it re-armed (empty when there is nothing, or when the
        give-up was recorded by the version now running). Their attempt counters
        were already dropped when they were resolved, so they come back with a
        full retry budget and flow through the ordinary candidate path.

        Version-gated rather than "on every poller start" on purpose: `poll
        --once` from cron would otherwise re-forward abandoned comments every
        minute, turning a bounded give-up into the endless retry it exists to
        prevent. An upgrade is the event that actually invalidates a give-up —
        the reason those events were abandoned may well be what the upgrade
        fixed — and by construction a fix only reaches an operator through one.
        """
        record = self._read(ref).get("gaveUp") or {}
        abandoned = [c for c in (record.get("comments") or []) if c]
        if not abandoned or str(record.get("version") or "") == __version__:
            return []
        item = self._item(ref)
        item["seenComments"] = [
            c for c in (item.get("seenComments") or []) if c not in set(abandoned)
        ]
        item["gaveUp"] = {}
        return abandoned

    def baseline_comments(
        self, ref: str, comment_ids: Sequence[str], polled_at: str
    ) -> None:
        """First-sight baseline: mark the whole existing thread seen (the
        spawned session reads it itself), with no attempts pending."""
        ids = list(dict.fromkeys(comment_ids))[-_SEEN_COMMENTS_CAP:]
        spawn = dict(self._read(ref).get("spawn") or {})
        self._items[ref] = {
            "seenComments": ids,
            "commentAttempts": {},
            "spawn": spawn,
            "lastPolledAt": polled_at,
        }
        self._dirty.add(ref)

    # -- spawn retry ledger -----------------------------------------------------

    def _spawn(self, ref: str) -> dict:
        return self._read(ref).get("spawn") or {}

    def spawn_attempts(self, ref: str) -> int:
        return int(self._spawn(ref).get("attempts", 0))

    def spawn_gave_up(self, ref: str) -> bool:
        return bool(self._spawn(ref).get("gaveUp", False))

    def spawn_delivery_id(self, ref: str) -> str:
        return str(self._spawn(ref).get("deliveryId") or "")

    def note_spawn_attempt(self, ref: str, delivery_id: str) -> int:
        item = self._item(ref)
        spawn = dict(item.get("spawn") or {})
        spawn["attempts"] = int(spawn.get("attempts", 0)) + 1
        spawn["deliveryId"] = delivery_id
        spawn["gaveUp"] = False
        item["spawn"] = spawn
        return spawn["attempts"]

    def mark_spawn_gave_up(self, ref: str) -> None:
        item = self._item(ref)
        spawn = dict(item.get("spawn") or {})
        spawn["gaveUp"] = True
        item["spawn"] = spawn

    def reset_spawn(self, ref: str) -> None:
        """Clear spawn retry state — a session came up, or new activity re-arms
        a spawn that had been given up (issue-80, AC6)."""
        item = self._item(ref)
        item["spawn"] = {}

    def forget(self, ref: str) -> None:
        """Drop an item's whole ledger — it ended (issue-94).

        A **reopened** work item is then first-sight again: its thread is
        re-baselined and a fresh session spawned, instead of the item being
        skipped forever as already-known. Written through immediately so a later
        `save` cannot resurrect it.
        """
        self._items.pop(ref, None)
        self._dirty.discard(ref)
        self.store.write_section(ref, POLL, None)

    # -- end of cycle -----------------------------------------------------------

    def finalize(
        self, ref: str, live_comment_ids: Sequence[str], polled_at: str
    ) -> None:
        """Prune the ledger to the live thread and stamp the poll time.

        Comment ids no longer present upstream are dropped from both
        ``seenComments`` and ``commentAttempts`` (they can never reappear),
        keeping the record bounded — the same windowing the old flat baseline
        did, extended to the attempt counters.
        """
        live = set(live_comment_ids)
        item = self._item(ref)
        seen = [c for c in (item.get("seenComments") or []) if c in live]
        item["seenComments"] = seen[-_SEEN_COMMENTS_CAP:]
        attempts = {
            cid: n
            for cid, n in (item.get("commentAttempts") or {}).items()
            if cid in live
        }
        item["commentAttempts"] = attempts
        record = dict(item.get("gaveUp") or {})
        abandoned = [c for c in (record.get("comments") or []) if c in live]
        # A comment that is gone upstream can never be re-armed, so the record
        # follows the same pruning as the rest of the ledger (issue-146).
        item["gaveUp"] = {**record, "comments": abandoned} if abandoned else {}
        item["lastPolledAt"] = polled_at

    def save(self) -> None:
        """Flush every item this cycle touched, each into its own record."""
        for ref in sorted(self._dirty):
            self.store.write_section(ref, POLL, self._items[ref])
        self._dirty.clear()


@dataclass
class PollSummary:
    """What one poll cycle did (for logging / tests / --once output)."""

    items_seen: int = 0
    spawns: int = 0
    comments_forwarded: int = 0
    closures: int = 0  # sessions closed because their item ended (issue-94)
    failures: int = 0  # events given up after exhausting the retry budget (issue-80)
    errors: List[str] = field(default_factory=list)


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class PollPlan:
    """The mutable part of a running poller: which providers, how often.

    Rebuilt from config on a hot reload; the dispatcher/registry (routing) are
    established once at start and are not part of the plan.
    """

    providers: List[PollProvider]
    interval_seconds: int


class Poller:
    """Poll each provider and feed discovered work to the shared dispatcher."""

    def __init__(
        self,
        providers: Sequence[PollProvider],
        registry: SessionRegistry,
        dispatcher: Dispatcher,
        config: PollConfig,
        state: PollState,
        reloader: Optional[Reloader] = None,
        authorized_users: Sequence[str] = (),
        control: Optional[ControlConfig] = None,
        control_store: Optional[ControlStore] = None,
    ):
        self.providers = list(providers)
        self.registry = registry
        self.dispatcher = dispatcher
        self.config = config
        self.state = state
        self.reloader = reloader
        # Per-event delivery attempts before the poller gives up (issue-80).
        # Read once here — like the dispatch knobs a hot reload doesn't touch.
        self.max_retries = max(1, int(config.max_retries))
        # Prompt-injection guard: only these logins' items/comments are acted on
        # (empty => fail closed for human-authored input). See the_loop.authz.
        self.authorized_users = list(authorized_users)
        # Execution control (issue-106). The dispatcher owns *executing* the
        # commands; the poller only needs to know whether a work item has been
        # started, so it does not keep offering presence events the dispatcher
        # is bound to refuse (and spend the issue-80 retry budget on). Both
        # default to the dispatcher's, read per cycle rather than snapshotted,
        # so a hot-reloaded control policy is honoured without a restart.
        self._control = control
        self._control_store = control_store
        # Work items whose abandoned comments this *run* has already considered
        # re-arming (issue-146) — the check is once per item per run, and the
        # re-arm itself only fires when a different CLI version recorded the
        # give-up, so a long-running poller never revisits it.
        self._rearm_considered: set = set()

    @property
    def control(self) -> ControlConfig:
        return (
            self._control
            if self._control is not None
            else self.dispatcher.config.control
        )

    @property
    def control_store(self) -> ControlStore:
        if self._control_store is not None:
            return self._control_store
        return self.dispatcher.control_store

    # -- one cycle --------------------------------------------------------------

    def poll_once(self) -> PollSummary:
        """Run a single discovery→dispatch pass over every provider."""
        summary = PollSummary()
        for provider in self.providers:
            self._poll_provider(provider, summary)
        self.state.save()
        logger.info(
            "poll cycle: %d item(s), %d spawn(s), %d comment(s) forwarded%s%s%s",
            summary.items_seen,
            summary.spawns,
            summary.comments_forwarded,
            f", {summary.closures} closed" if summary.closures else "",
            f", {summary.failures} gave up" if summary.failures else "",
            f", {len(summary.errors)} error(s)" if summary.errors else "",
        )
        eventlog.emit(
            "poll.cycle",
            items_seen=summary.items_seen,
            spawns=summary.spawns,
            comments_forwarded=summary.comments_forwarded,
            closures=summary.closures or None,
            failures=summary.failures or None,
            errors=summary.errors or None,
        )
        return summary

    def _poll_provider(self, provider: PollProvider, summary: PollSummary) -> None:
        try:
            items = provider.list_work_items()
        except ProviderError as exc:
            logger.error("polling %s failed: %s", provider.describe(), exc)
            eventlog.emit(
                "poll.provider_error",
                level="error",
                provider=provider.describe(),
                error=str(exc),
                will_retry=True,
            )
            summary.errors.append(f"{provider.describe()}: {exc}")
            return
        open_refs = set()
        for item in items:
            summary.items_seen += 1
            # An item's *linked* refs, not just its own: a session registered
            # against an issue is still live while its PR is open and labelled.
            open_refs.update(ref.ref for ref in provider.refs(item))
            try:
                self._process_item(provider, item, summary)
            except ProviderError as exc:
                logger.error("processing %s failed: %s", item.ref, exc)
                eventlog.emit(
                    "poll.item_error",
                    level="error",
                    work_item=item.ref,
                    error=str(exc),
                    will_retry=True,
                )
                summary.errors.append(f"{item.ref}: {exc}")
        # Only ever reached on a SUCCESSFUL listing (the ProviderError path
        # above returns first), so a failed or partial listing can never be read
        # as "everything closed" (issue-94).
        self._reconcile_closures(provider, open_refs, summary)

    def _reconcile_closures(
        self, provider: PollProvider, open_refs: set, summary: PollSummary
    ) -> None:
        """Close sessions whose work item has ended (issue-94).

        A poll source lists only *open* items, so an issue that is closed or a
        PR that is merged simply disappears — nothing in the per-item loop can
        notice it. This walks the other way round, from the **registry**: every
        active session this source owns whose item is no longer in the listing
        is checked once against the provider, and a genuinely ended item is
        closed through the dispatcher's normal close path.

        Registry-driven rather than diffing successive listings, so it also
        catches items that ended while the poller was down — there is no memory
        to lose across restarts. Under any doubt (still open, or the provider
        could not answer) the session is left running.
        """
        for session in self.registry.list_sessions(status="active"):
            ref = session.work_item
            if ref.ref in open_refs or not provider.owns(ref):
                continue
            try:
                closure = provider.closure(ref)
            except ProviderError as exc:
                logger.warning(
                    "could not check whether %s is still open: %s", ref.ref, exc
                )
                eventlog.emit(
                    "poll.item_error",
                    level="warning",
                    work_item=ref.ref,
                    error=str(exc),
                    will_retry=True,
                )
                summary.errors.append(f"{ref.ref}: {exc}")
                continue
            if closure is None:
                continue  # still open (e.g. the label was removed) — leave it
            logger.info(
                "%s is %s upstream; closing its session",
                ref.ref,
                closure.state,
            )
            eventlog.emit(
                "poll.closure_detected",
                work_item=ref.ref,
                state=closure.state,
                kind=closure.kind or None,
            )
            self.dispatcher.handle(provider.closure_event(ref, closure))
            self.state.forget(ref.ref)
            summary.closures += 1

    def _process_item(
        self, provider: PollProvider, item: WorkItem, summary: PollSummary
    ) -> None:
        refs = provider.refs(item)
        if not refs:
            return
        ref = item.ref

        comments = provider.list_comments(item)
        live_ids = [c.id for c in comments if c.id]
        first_sight = not self.state.is_known(ref)
        # Authorization guard (prompt-injection remediation): only act on input
        # authored by an authorized user.
        item_authorized = is_authorized(item.author, self.authorized_users)
        if item.author and not item_authorized:
            logger.warning(
                "ignoring %s from unauthorized author %r (not in authorizedUsers)",
                ref,
                item.author,
            )
            eventlog.emit(
                "poll.unauthorized",
                level="warning",
                work_item=ref,
                actor=item.author,
            )
        has_session = any(
            self.registry.find_by_work_item(wi) is not None for wi in refs
        )

        # First sight: baseline the existing thread (the spawned session reads it
        # itself, matching webhook "only events going forward"), arm the spawn,
        # and stop. Only spawn for items an authorized user authored (the input
        # fed to /the-loop:work-on is that item's own body).
        #
        # Except for control commands nobody has processed yet (issue-119).
        # Baselining means "resolved, never look at this again" — true of an
        # ordinary comment, false of an instruction to the-loop that has not run.
        # Those flow through the ordinary comment path below instead, so a start
        # posted BEFORE the poller first saw the item behaves exactly like one
        # posted after it (which is all the webhook path ever sees, label and
        # comment being two deliveries).
        if first_sight:
            pending = (
                self._pending_control_ids(ref, comments) if item_authorized else set()
            )
            self.state.baseline_comments(
                ref, [cid for cid in live_ids if cid not in pending], _utcnow()
            )
            if not pending:
                if item_authorized and not has_session:
                    self._try_spawn(provider, item, refs, summary)
                return
            # Fall through to the known-item path with `pending` unbaselined: it
            # forwards them (in thread order) and takes the arming decision ONCE,
            # after they have been applied — so presence and a control-triggered
            # spawn are never enqueued for the same item on the same cycle.
            logger.info(
                "%s: first sight, and %d control comment(s) on it were never "
                "processed; handling them now instead of baselining them",
                ref,
                len(pending),
            )

        # Known item. Before reading the baseline, give comments that an OLDER
        # CLI abandoned one more chance (issue-146): the reason they were
        # abandoned may be exactly what the upgrade fixed, and until they are
        # un-resolved the item stays stuck forever with no signal.
        self._maybe_rearm(ref)

        # Sort unresolved comments into candidates (authorized, non-self) to
        # forward, and dropped ones (unauthorized, or issue-64 self-marked
        # replies) which are baselined so they are never re-evaluated —
        # matching the old unconditional baseline for those.
        seen = self.state.seen_comments(ref)
        candidates = []
        for comment in comments:
            if not comment.id or comment.id in seen:
                continue
            if not is_authorized(
                comment.author, self.authorized_users
            ) or is_self_authored(comment.body):
                self.state.resolve_comment(ref, comment.id)
                continue
            candidates.append(comment)
        # A genuinely-new comment (never attempted) re-arms a spawn that had been
        # given up — a new comment retriggers the item (issue-80, AC6).
        genuinely_new = any(
            self.state.comment_attempts(ref, c.id) == 0 for c in candidates
        )

        # Spawn only when there is a reason to: genuinely new activity, or a spawn
        # already in progress (attempts recorded). A dormant known item with no
        # session and no new activity must not spontaneously spawn.
        if item_authorized and not has_session:
            if genuinely_new:
                self.state.reset_spawn(ref)
            if genuinely_new or self.state.spawn_attempts(ref) > 0:
                self._try_spawn(provider, item, refs, summary)
        elif has_session:
            self.state.reset_spawn(ref)

        if item_authorized:
            for comment in candidates:
                self._process_comment(provider, item, comment, refs, summary)

        self.state.finalize(ref, live_ids, _utcnow())

    def _try_spawn(
        self,
        provider: PollProvider,
        item: WorkItem,
        refs: List[WorkItemRef],
        summary: PollSummary,
    ) -> None:
        """Spawn a session for a labelled item, bounded by the retry budget.

        Called once the spawn is *armed* (first sight, new activity, or a spawn
        already in progress). Unlike the old ``first_sight or new_comments``
        guard, a failed spawn no longer suppresses later attempts: the poller
        retries each cycle until a session exists or the budget is spent, then
        logs a terminal failure and gives up until new activity re-arms it
        (issue-80).
        """
        ref = item.ref
        if self.state.spawn_gave_up(ref):
            return
        if self._awaiting_start(item):
            return
        # A prior presence still enqueued/processing? Wait — don't pile a second
        # spawn behind it, and don't count it a failure (a process-runner spawn
        # runs the whole task and can outlast a poll cycle).
        last_did = self.state.spawn_delivery_id(ref)
        if last_did:
            status = self.dispatcher.delivery_status(last_did, refs)
            if status == "inflight":
                return
            if status == "done":  # session came up — belt and suspenders
                self.state.reset_spawn(ref)
                return
        attempts = self.state.spawn_attempts(ref)
        if attempts >= self.max_retries:
            logger.error(
                "giving up spawning a session for %s after %d attempt(s); "
                "further polls ignore it until new activity arrives",
                ref,
                attempts,
            )
            eventlog.emit(
                "poll.spawn_failed",
                level="error",
                work_item=ref,
                attempts=attempts,
                will_retry=False,
            )
            self.state.mark_spawn_gave_up(ref)
            summary.failures += 1
            return
        event = provider.presence_event(item, refs)
        self.dispatcher.handle(event)
        self.state.note_spawn_attempt(ref, event.delivery_id)
        summary.spawns += 1

    def _pending_control_ids(self, ref: str, comments: Sequence[Comment]) -> set:
        """Ids of comments carrying a control command nobody has processed (issue-119).

        The poller's *only* job here is to decide which comments are still
        unresolved; what a command means, who may issue it and what it does stay
        where they belong — :meth:`Dispatcher.handle`, which re-checks for a
        **named** authorized actor, refuses a start on an unarmed item, and is
        the single writer of the :class:`ControlStore`. So this returns comment
        ids and nothing else: no control state is recorded here, no spawn is
        triggered here, and no text from a body escapes this method.

        A comment qualifies only when it passes the very guards the known-item
        forward path applies to any candidate — authorized author (an empty
        allowlist authorizes nobody), not the-loop's own self-marked body — and
        carries an **unambiguous** command. An ambiguous body (two conflicting
        keywords) is left to the baseline: the dispatcher executes nothing for
        it, so forwarding it would only log a warning. ``control.enabled: false``
        yields no commands at all, i.e. the pre-issue-119 behaviour verbatim.

        A work item that **already has a control record** is skipped entirely:
        the record is the-loop's own durable answer to "has this been
        processed?", so re-reading the thread could only replay commands it has
        already acted on — e.g. re-applying a `stop` that a later
        `the-loop sessions start` (whose comment is self-marked, hence invisible
        here) has since superseded. This makes a first sight able to *bootstrap*
        control state, never to overwrite it.
        """
        if self.control_store.get(ref) is not None:
            return set()
        control = self.control
        pending = set()
        for comment in comments:
            if not comment.id:
                continue
            if not is_authorized(comment.author, self.authorized_users):
                continue
            if is_self_authored(comment.body):
                continue
            if parse_command(comment.body, control).command:
                pending.add(comment.id)
        return pending

    def _awaiting_start(self, item: WorkItem) -> bool:
        """Whether this item is labelled but nobody has started it (issue-106).

        A presence event for such an item would be refused by the dispatcher —
        correctly — but the poller has no way to tell a *refusal* from a
        *failure*, so it would retry it every cycle until the issue-80 budget is
        spent and then log a terminal `poll.spawn_failed`. Every labelled,
        unstarted item in the operator's repos would produce that noise.

        So the poller simply does not arm presence while a start is missing. The
        start command still gets through: it arrives as an ordinary comment
        event, which the dispatcher executes (and spawns from) on its own path —
        including a start that was already on the thread the first time the item
        was seen, which :meth:`_pending_control_ids` keeps out of the first-sight
        baseline for exactly this reason (issue-119).
        """
        control = self.control
        if not (control.enabled and control.require_start_command):
            return False
        if self.control_store.start_requested(item.ref):
            return False
        logger.debug(
            "%s is labelled but not started; not arming a spawn (comment %r on "
            "it, or run `the-loop sessions start`, to begin)",
            item.ref,
            control.keyword("start"),
        )
        return True

    def _maybe_rearm(self, ref: str) -> None:
        """Once per run per item: re-arm comments an older CLI gave up on.

        A give-up is a statement about a *failing* environment ("three attempts,
        this is not working"); a new CLI version is the one event that can
        invalidate it. :meth:`PollState.rearm_gave_up_comments` owns that gate and
        returns nothing when the running version is the one that gave up, so this
        is a no-op on every ordinary cycle — including repeated `poll --once`
        runs, which must not re-forward abandoned comments every minute.
        """
        if ref in self._rearm_considered:
            return
        self._rearm_considered.add(ref)
        rearmed = self.state.rearm_gave_up_comments(ref)
        if not rearmed:
            return
        logger.info(
            "%s: %d comment(s) were abandoned by an earlier the-loop version; "
            "re-arming them with a fresh retry budget (the-loop %s)",
            ref,
            len(rearmed),
            __version__,
        )
        eventlog.emit(
            "poll.rearmed",
            work_item=ref,
            comments=rearmed,
            version=__version__,
        )

    def _process_comment(
        self,
        provider: PollProvider,
        item: WorkItem,
        comment: Comment,
        refs: List[WorkItemRef],
        summary: PollSummary,
    ) -> None:
        """Forward a comment to its session with bounded retries (issue-80).

        Observes the async dispatch outcome via the dispatcher's durable dedup
        state instead of guessing at enqueue time: a delivered comment is
        baselined, an in-flight one is left to finish, and only a genuinely
        failed one spends a retry — giving up (with an audit log) after the
        budget is exhausted so later polls ignore it.
        """
        ref = item.ref
        event = provider.comment_event(item, comment, refs)
        status = self.dispatcher.delivery_status(event.delivery_id, refs)
        if status == "done":
            self.state.resolve_comment(ref, comment.id)
            return
        if status == "inflight":
            return
        attempts = self.state.comment_attempts(ref, comment.id)
        if attempts >= self.max_retries:
            logger.error(
                "giving up forwarding comment %s on %s after %d attempt(s); "
                "further polls ignore it",
                comment.id,
                ref,
                attempts,
            )
            eventlog.emit(
                "poll.comment_failed",
                level="error",
                work_item=ref,
                comment_id=comment.id,
                actor=comment.author,
                attempts=attempts,
                will_retry=False,
            )
            self.state.resolve_comment(ref, comment.id, gave_up=True)
            summary.failures += 1
            return
        self.dispatcher.handle(event)
        attempt = self.state.note_comment_attempt(ref, comment.id)
        eventlog.emit(
            "poll.comment_forwarded",
            work_item=ref,
            comment_id=comment.id,
            actor=comment.author,
            attempt=attempt,
        )
        summary.comments_forwarded += 1

    # -- hot reload -------------------------------------------------------------

    def _maybe_reload(self) -> None:
        """Swap in a fresh plan if the config file changed since last cycle."""
        if self.reloader is None:
            return
        plan = self.reloader.poll_for_change()
        if plan is None:
            return
        self.providers = plan.providers
        self.config.interval_seconds = plan.interval_seconds
        logger.info(
            "hot-reloaded polling: %d source(s), interval=%ss",
            len(plan.providers),
            plan.interval_seconds,
        )
        eventlog.emit(
            "config.reloaded",
            detail=(
                f"polling: {len(plan.providers)} source(s), "
                f"interval={plan.interval_seconds}s"
            ),
        )

    # -- run loop ---------------------------------------------------------------

    def run(
        self,
        once: bool = False,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Poll forever (or once), waking early when ``stop_event`` is set.

        The config file is re-checked before every cycle (hot reload): edits to
        ``polling.sources`` / ``intervalSeconds`` take effect on the next cycle
        with no restart.
        """
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            self._maybe_reload()
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
                logger.exception("poll cycle raised; continuing")
            if once:
                return
            stop_event.wait(self.config.interval_seconds)
