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
  polls/restarts by a durable :class:`PollState`.

Spec: docs/specs/issue-34/design.md.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .. import eventlog
from ..authz import is_authorized, is_self_authored
from ..reload import Reloader
from ..sessions import SessionRegistry, WorkItemRef
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
    templates) is reused from ``webhooks.ghWebhook.routing``.
    """

    interval_seconds: int = 60
    state_file: str = ".the-loop/poll-state.json"
    max_retries: int = 3
    sources: List[dict] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "PollConfig":
        data = data or {}
        return cls(
            interval_seconds=int(data.get("intervalSeconds", 60)),
            state_file=str(data.get("stateFile", ".the-loop/poll-state.json")),
            max_retries=max(1, int(data.get("maxRetries", 3))),
            sources=[dict(s) for s in (data.get("sources") or []) if s],
        )


class PollState:
    """Durable, atomic-write per-item retry ledger for the poller (issue-80).

    One JSON file keyed by work-item ref. It exists so the poller is idempotent
    across cycles *and* restarts (there is no webhook redelivery to lean on),
    and so a *failed* spawn/forward is retried a bounded number of times instead
    of being baselined as "processed" on the first attempt. Per ref it tracks:

    - ``seenComments`` — **resolved** comment ids (delivered *or* given up after
      the retry budget), the baseline the poller ignores. Pruned to the live
      thread each cycle so it stays bounded.
    - ``commentAttempts`` — ``{comment_id: attempts}`` for comments still in
      flight (forwarded but not yet confirmed delivered).
    - ``spawn`` — ``{attempts, gaveUp, deliveryId}`` for the presence/spawn
      retry (the presence delivery id is stored so the poller can tell an
      in-flight spawn from a failed one across cycles).
    """

    def __init__(self, path):
        self.path = Path(path)
        self._items: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            logger.warning("ignoring unreadable poll state %s: %s", self.path, exc)
            return
        self._items = dict((data or {}).get("items") or {})

    def _item(self, ref: str) -> dict:
        return self._items.setdefault(ref, {})

    def is_known(self, ref: str) -> bool:
        return ref in self._items

    def seen_comments(self, ref: str) -> set:
        return set((self._items.get(ref) or {}).get("seenComments") or [])

    # -- comment retry ledger ---------------------------------------------------

    def comment_attempts(self, ref: str, comment_id: str) -> int:
        item = self._items.get(ref) or {}
        return int((item.get("commentAttempts") or {}).get(comment_id, 0))

    def note_comment_attempt(self, ref: str, comment_id: str) -> int:
        """Record one delivery attempt for a comment; return the new count."""
        item = self._item(ref)
        attempts = dict(item.get("commentAttempts") or {})
        attempts[comment_id] = attempts.get(comment_id, 0) + 1
        item["commentAttempts"] = attempts
        return attempts[comment_id]

    def resolve_comment(self, ref: str, comment_id: str) -> None:
        """Mark a comment done (delivered or given up): baseline it, drop its
        in-flight counter so it is ignored on later polls."""
        item = self._item(ref)
        seen = list(item.get("seenComments") or [])
        if comment_id not in seen:
            seen.append(comment_id)
        item["seenComments"] = seen[-_SEEN_COMMENTS_CAP:]
        attempts = dict(item.get("commentAttempts") or {})
        attempts.pop(comment_id, None)
        item["commentAttempts"] = attempts

    def baseline_comments(
        self, ref: str, comment_ids: Sequence[str], polled_at: str
    ) -> None:
        """First-sight baseline: mark the whole existing thread seen (the
        spawned session reads it itself), with no attempts pending."""
        ids = list(dict.fromkeys(comment_ids))[-_SEEN_COMMENTS_CAP:]
        self._items[ref] = {
            "seenComments": ids,
            "commentAttempts": {},
            "spawn": (self._items.get(ref) or {}).get("spawn") or {},
            "lastPolledAt": polled_at,
        }

    # -- spawn retry ledger -----------------------------------------------------

    def _spawn(self, ref: str) -> dict:
        return (self._items.get(ref) or {}).get("spawn") or {}

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
        item["lastPolledAt"] = polled_at

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as handle:
                json.dump({"items": self._items}, handle, indent=2)
                handle.write("\n")
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            raise


@dataclass
class PollSummary:
    """What one poll cycle did (for logging / tests / --once output)."""

    items_seen: int = 0
    spawns: int = 0
    comments_forwarded: int = 0
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

    # -- one cycle --------------------------------------------------------------

    def poll_once(self) -> PollSummary:
        """Run a single discovery→dispatch pass over every provider."""
        summary = PollSummary()
        for provider in self.providers:
            self._poll_provider(provider, summary)
        self.state.save()
        logger.info(
            "poll cycle: %d item(s), %d spawn(s), %d comment(s) forwarded%s%s",
            summary.items_seen,
            summary.spawns,
            summary.comments_forwarded,
            f", {summary.failures} gave up" if summary.failures else "",
            f", {len(summary.errors)} error(s)" if summary.errors else "",
        )
        eventlog.emit(
            "poll.cycle",
            items_seen=summary.items_seen,
            spawns=summary.spawns,
            comments_forwarded=summary.comments_forwarded,
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
        for item in items:
            summary.items_seen += 1
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
        if first_sight:
            if item_authorized and not has_session:
                self._try_spawn(provider, item, refs, summary)
            self.state.baseline_comments(ref, live_ids, _utcnow())
            return

        # Known item. Sort unresolved comments into candidates (authorized,
        # non-self) to forward, and dropped ones (unauthorized, or issue-64
        # self-marked replies) which are baselined so they are never
        # re-evaluated — matching the old unconditional baseline for those.
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
            self.state.resolve_comment(ref, comment.id)
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
