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

Stopping and starting it is meant to be invisible (issue-159): each work item's
ledger is persisted as soon as that item is done, a stop is honoured *within* a
cycle (and an interrupted cycle never reconciles closures — a partial listing is
not proof anything ended), and a shutdown hands back the retry budget of
dispatches that died queued.

Spec: docs/specs/issue-34/design.md; docs/specs/issue-94/design.md;
docs/specs/issue-159/design.md.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence

from .. import __version__, eventlog
from ..authz import is_authorized, is_self_authored, mark_self_authored
from ..comments import post_issue_comment
from ..control import ControlConfig, ControlStore, parse_command
from ..reload import Reloader
from ..sessions import SessionRegistry, WorkItemRef
from ..workitem import POLL, WorkItemStore
from ..webhook.dispatcher import Dispatcher
from .base import (
    REPROBE_EVERY_CYCLES,
    Comment,
    Listing,
    PollProvider,
    ProviderError,
    ScopeFailure,
    WorkItem,
)

if TYPE_CHECKING:  # the roster is the dispatcher's, read here (issue-307)
    from ..collaborators import CollaboratorStore

logger = logging.getLogger("the-loop.poll")

# Per item, how many comment ids we remember across polls. The set is re-seeded
# from the live comment list every cycle, so this only caps a single very
# chatty thread; the newest comments always stay in the window.
#
# Raised from 500 with issue-246, which put three streams of ids into this one
# ledger — conversation comments, review bodies and inline review-thread
# comments — so the old bound is reached roughly three times sooner. It matters
# because of what eviction does here: an id dropped while it is still live
# upstream reads as new on the next cycle, is forwarded again, resolves, and is
# evicted again. That is a delivery loop, not a forgotten comment.
_SEEN_COMMENTS_CAP = 2000


def giveup_notice(*, ref: str, comment_id: str, comment_url: str, attempts: int) -> str:
    """The comment the poller posts when it abandons a comment (issue-240).

    A give-up used to be visible only in the local event log and as a 😕
    reaction, so a human who told an agent to do something had no way to learn
    the agent was never told. This is what says so on the ticket.

    Pure, and **deliberately unable to echo the comment it reports**: there is no
    parameter through which a commenter's body could reach a comment the-loop
    posts with the operator's own credentials. Everything here is either
    the-loop's own prose or a value it minted (the ref, the attempt count, the
    provider's own comment id/URL), which is what makes
    :func:`~the_loop.authz.mark_self_authored` safe to apply — it asserts
    authorship, and must never be applied to foreign text.
    """
    # The id is named even when a URL is available: the reader follows the link,
    # and an operator greps the event log by the same id `poll.comment_failed`
    # recorded.
    named = (
        f"[a comment]({comment_url}) (`{comment_id}`)"
        if comment_url
        else f"comment `{comment_id}`"
    )
    attempt_word = "attempt" if attempts == 1 else "attempts"
    return mark_self_authored(
        f"😕 **the-loop could not deliver {named} to the session for `{ref}`.**\n"
        "\n"
        f"Every one of {attempts} delivery {attempt_word} failed, so the comment "
        "has been abandoned: the session never received it, and the poller will "
        "not try again on its own.\n"
        "\n"
        "**To get it through:** post the instruction again. A new comment is a "
        "new delivery with a full retry budget — nothing the-loop stores needs "
        "editing.\n"
        "\n"
        "**Before you do,** check the session is still there and attachable:\n"
        "\n"
        "```sh\n"
        "the-loop sessions list\n"
        "```\n"
        "\n"
        "The cause of each failed delivery is in the daemon's event log, as the "
        "`error` field of the `dispatch.failed` entries for this work item.\n"
    )


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
      flight (forwarded but not yet confirmed delivered). Only deliveries that
      may still be **retried** are counted: a comment the dispatcher refused on
      purpose — the work item is not started, its session is paused — or consumed
      as a control command is baselined into ``seenComments`` instead
      (``poll.comment_settled``, issue-270), because no number of retries would
      change that answer.
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
    writes only the items it touched. Entries are read lazily and written back by
    :meth:`flush` as soon as their work item is done (issue-159 — a poller killed
    mid-cycle then loses the item in flight rather than everything the cycle
    learned), with :meth:`save` as the end-of-cycle backstop; :meth:`forget`
    writes through immediately, because a work item that ended must not be
    resurrected by a later flush.
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
        self, ref: str, comment_ids: Sequence[str], polled_at: str, title: str = ""
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
        if title:
            self._items[ref]["title"] = title
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

    # -- returning unspent budget (issue-159) -----------------------------------

    def release_comment_attempt(self, ref: str, comment_id: str) -> None:
        """Un-count one recorded attempt for a comment that was never delivered.

        An attempt is recorded when the poller *enqueues* an event, and the
        outcome is observed on a later cycle (issue-80). A shutdown that
        abandons the event while it is still queued therefore leaves an attempt
        spent on a dispatch that never happened — and three restarts would
        exhaust the budget and abandon a comment nothing ever tried to deliver.

        Deliberately does **not** touch ``seenComments``: the comment stays
        unresolved, exactly as if it had never been enqueued, so the next start
        rediscovers it as an ordinary candidate.
        """
        item = self._item(ref)
        attempts = dict(item.get("commentAttempts") or {})
        remaining = int(attempts.get(comment_id, 0)) - 1
        if remaining > 0:
            attempts[comment_id] = remaining
        else:
            attempts.pop(comment_id, None)
        item["commentAttempts"] = attempts

    def release_spawn_attempt(self, ref: str) -> None:
        """The spawn-ledger twin of :meth:`release_comment_attempt`.

        Also clears the in-flight delivery id, because the delivery it named
        died with the process — leaving it would make the next start read a
        presence event that no longer exists anywhere as "still in flight".
        """
        item = self._item(ref)
        spawn = dict(item.get("spawn") or {})
        remaining = int(spawn.get("attempts", 0)) - 1
        spawn["attempts"] = remaining if remaining > 0 else 0
        spawn["deliveryId"] = ""
        item["spawn"] = spawn

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
        self, ref: str, live_comment_ids: Sequence[str], polled_at: str, title: str = ""
    ) -> None:
        """Prune the ledger to the live thread and stamp the poll time.

        Comment ids no longer present upstream are dropped from both
        ``seenComments`` and ``commentAttempts`` (they can never reappear),
        keeping the record bounded — the same windowing the old flat baseline
        did, extended to the attempt counters.

        ``title`` caches the ticket's title in the portable record so the
        control plane can serve it (issue-283 B1): the listing already carried
        it, and without a cached copy every dashboard falls back to a bare
        ref-and-link. Refreshed each cycle, so a renamed ticket converges.
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
        if title:
            item["title"] = title

    def flush(self, ref: str) -> None:
        """Write **one** item's record, if this cycle changed it (issue-159).

        Called as soon as a work item is done rather than at the end of the
        cycle, so a poller killed while processing item 40 of 50 loses what it
        learned about item 40 and nothing else. Storage is unchanged — records
        were already one atomic file per work item — only the schedule is: same
        bytes, same records, written sooner.
        """
        if ref not in self._dirty:
            return
        self.store.write_section(ref, POLL, self._items[ref])
        self._dirty.discard(ref)

    def save(self) -> None:
        """Flush every item still dirty, each into its own record.

        The end-of-cycle backstop now that :meth:`flush` writes each item as it
        finishes: whatever a cycle touched outside the per-item path still lands.
        """
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
    interrupted: bool = False  # a stop was requested mid-cycle (issue-159)
    # Which scopes (repositories, for GitHub) answered, failed or were skipped
    # this cycle (issue-315) — what `the-loop status` names as degraded.
    scopes_polled: int = 0
    scopes_failed: List[ScopeFailure] = field(default_factory=list)
    scopes_skipped: List[ScopeFailure] = field(default_factory=list)


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
        collaborator_store: Optional["CollaboratorStore"] = None,
        heartbeat: Optional[Callable[["PollSummary"], None]] = None,
        comment_runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        publisher: Optional[Callable[[str, str, str, str, str], None]] = None,
    ):
        # The bus (issue-309): a comment this ingress drops as the agent's own, or
        # forwards as a human's, is published to the subscribed channels —
        # `comment.agent` / `comment.human`. Injected like the router's, so a
        # poller built without one publishes nothing.
        self.publisher = publisher
        self.providers = list(providers)
        self.registry = registry
        self.dispatcher = dispatcher
        self.config = config
        self.state = state
        self.reloader = reloader
        # Per-event delivery attempts before the poller gives up (issue-80).
        # Read once here — like the dispatch knobs a hot reload doesn't touch.
        self.max_retries = max(1, int(config.max_retries))
        # Prompt-injection guard: only these logins' comments are acted on, and
        # only an item one of them opened (or armed) is started (empty => fail
        # closed for human-authored input). See the_loop.authz, decision-074.
        self.authorized_users = list(authorized_users)
        # Called with each cycle's summary so `the-loop status` can report
        # progress, not just liveness (issue-191). Injected rather than owned:
        # the run loop should not hold a file handle, and a poller under test
        # should not write one. A raising heartbeat must never end a cycle, so
        # it is called defensively below.
        self._heartbeat = heartbeat
        # Execution control (issue-106). The dispatcher owns *executing* the
        # commands; the poller only needs to know whether a work item has been
        # started, so it does not keep offering presence events the dispatcher
        # is bound to refuse (and spend the issue-80 retry budget on). Both
        # default to the dispatcher's, read per cycle rather than snapshotted,
        # so a hot-reloaded control policy is honoured without a restart.
        self._control = control
        self._control_store = control_store
        self._collaborator_store = collaborator_store
        # Work items whose abandoned comments this *run* has already considered
        # re-arming (issue-146) — the check is once per item per run, and the
        # re-arm itself only fires when a different CLI version recorded the
        # give-up, so a long-running poller never revisits it.
        self._rearm_considered: set = set()
        # Attempts this process has recorded but not yet seen resolved, keyed by
        # the delivery id they were spent on: `{delivery_id: (ref, comment_id)}`,
        # with an empty comment id meaning a presence/spawn attempt. Read only by
        # `release_abandoned` (issue-159), to hand back the budget of events that
        # died queued in the dispatcher at shutdown. In-memory on purpose: it
        # answers "did *this* process abandon that event?", which no other
        # process can answer — and a SIGKILL, where there is no shutdown to roll
        # back, must leave the ledger exactly as the per-item flush left it.
        self._attempted: Dict[str, tuple] = {}
        # How the give-up notice reaches GitHub (issue-240). Injectable for the
        # same reason `SessionAnnouncer`/`GitHubReactor` are: tests drive the
        # notice without a real `gh`.
        self._comment_runner = comment_runner
        self._warned_missing_gh = False

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

    @property
    def collaborator_store(self) -> "CollaboratorStore":
        """The work-item collaborator rosters (issue-307).

        The dispatcher's, exactly as ``control_store`` is: one roster per work item,
        in one directory, whichever ingress reads it.
        """
        if self._collaborator_store is not None:
            return self._collaborator_store
        return self.dispatcher.collaborator_store

    # -- one cycle --------------------------------------------------------------

    def poll_once(self, stop_event: Optional[threading.Event] = None) -> PollSummary:
        """Run a single discovery→dispatch pass over every provider.

        ``stop_event`` makes a shutdown observable *inside* the cycle
        (issue-159): without it, `SIGTERM` was only ever checked between cycles,
        so a stop could take as long as every remaining item's dispatch — up to
        ``routing.dispatchTimeoutSeconds`` each — and every item processed in
        that window is a session spawned after the operator asked it to stop.
        The item in flight always finishes; nothing below it starts.
        """
        summary = PollSummary()
        for provider in self.providers:
            if stop_event is not None and stop_event.is_set():
                summary.interrupted = True
                break
            self._poll_provider(provider, summary, stop_event)
        self.state.save()
        # Distinct scopes: a repository whose issues AND pull requests failed is
        # one degraded scope, not two.
        degraded = list(
            dict.fromkeys(
                s.scope for s in summary.scopes_failed + summary.scopes_skipped
            )
        )
        logger.info(
            "poll cycle: %d item(s), %d spawn(s), %d comment(s) forwarded%s%s%s%s%s",
            summary.items_seen,
            summary.spawns,
            summary.comments_forwarded,
            f", {summary.closures} closed" if summary.closures else "",
            f", {summary.failures} gave up" if summary.failures else "",
            f", {len(summary.errors)} error(s)" if summary.errors else "",
            f", {len(degraded)} scope(s) degraded" if degraded else "",
            " (interrupted by a stop request)" if summary.interrupted else "",
        )
        eventlog.emit(
            "poll.cycle",
            items_seen=summary.items_seen,
            spawns=summary.spawns,
            comments_forwarded=summary.comments_forwarded,
            closures=summary.closures or None,
            failures=summary.failures or None,
            errors=summary.errors or None,
            scopes_polled=summary.scopes_polled or None,
            scopes_degraded=degraded or None,
            interrupted=summary.interrupted or None,
        )
        self._beat(summary)
        return summary

    def _beat(self, summary: PollSummary) -> None:
        """Record the cycle in the heartbeat, if one was injected.

        Swallows everything: a health file that cannot be written is a reason to
        warn, never a reason to stop delivering events (the writer itself already
        warns once on ``OSError``).
        """
        if self._heartbeat is None:
            return
        try:
            self._heartbeat(summary)
        except Exception:  # noqa: BLE001 — o11y must never break ingress
            logger.exception("recording the poll heartbeat failed; continuing")

    def _poll_provider(
        self,
        provider: PollProvider,
        summary: PollSummary,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        try:
            listing = provider.listing()
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
        self._record_scopes(provider, listing, summary)
        open_refs = set()
        for item in listing.items:
            if stop_event is not None and stop_event.is_set():
                # Stop between work items, never inside one: an item abandoned
                # half-processed is exactly the partially-written state the
                # per-item flush exists to prevent (issue-159).
                logger.info(
                    "stop requested; ending this poll cycle after %d item(s) of %s",
                    summary.items_seen,
                    provider.describe(),
                )
                summary.interrupted = True
                return
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
            finally:
                # Persist what this item learned before touching the next one —
                # including after a failure, so an attempt already spent cannot
                # be spent twice by the next start (issue-159, AC3.2).
                self.state.flush(item.ref)
        # Only ever reached on a SUCCESSFUL and COMPLETE listing: the
        # ProviderError path above returns first, and so does an interrupted
        # walk. Reconciliation closes every active session whose item is absent
        # from `open_refs`, so a partial set would read as "everything below the
        # interruption closed" and end live sessions — the same reason issue-94
        # skips it for a failed listing (issue-159, AC4.2). A listing that is
        # complete for some scopes and failed for others (issue-315) reconciles
        # the former and leaves the latter alone: the rule, at the finer grain.
        self._reconcile_closures(provider, open_refs, summary, listing.degraded)

    def _record_scopes(
        self, provider: PollProvider, listing: Listing, summary: PollSummary
    ) -> None:
        """Log, event and count what a listing could not ask (issue-315).

        A transient failure is an error every cycle it recurs, like a provider
        failure was. A permanent one is a *warning*, once: the provider has
        already stopped asking, and while it stays skipped the only trace is
        the heartbeat — which is what `the-loop status` renders as degraded —
        so a log is not the same line every minute for a condition that only an
        operator can change. A recovery is said once too.
        """
        name = provider.describe()
        for failure in listing.failures:
            summary.errors.append(f"{failure.scope}: {failure.error}")
            summary.scopes_failed.append(failure)
            if failure.permanent:
                logger.warning(
                    "polling %s: %s cannot be listed and will not be retried "
                    "every cycle — %s. Re-probed every %d cycles, on a config "
                    "reload and on restart; `the-loop status` shows it as "
                    "degraded meanwhile",
                    name,
                    failure.scope,
                    failure.error,
                    REPROBE_EVERY_CYCLES,
                )
                eventlog.emit(
                    "poll.scope_degraded",
                    level="warning",
                    provider=name,
                    scope=failure.scope,
                    error=failure.error,
                    retry_after_cycles=REPROBE_EVERY_CYCLES,
                )
                continue
            logger.error(
                "polling %s: %s could not be listed (the source's other scopes "
                "were still polled): %s",
                name,
                failure.scope,
                failure.error,
            )
            eventlog.emit(
                "poll.scope_error",
                level="error",
                provider=name,
                scope=failure.scope,
                error=failure.error,
                will_retry=True,
            )
        for skip in listing.skipped:
            summary.scopes_skipped.append(skip)
            logger.debug("polling %s: %s skipped — %s", name, skip.scope, skip.error)
        for scope in listing.recovered:
            logger.info(
                "polling %s: %s answers again; polling it normally", name, scope
            )
            eventlog.emit("poll.scope_recovered", provider=name, scope=scope)
        summary.scopes_polled += len(listing.polled)

    def _reconcile_closures(
        self,
        provider: PollProvider,
        open_refs: set,
        summary: PollSummary,
        degraded: Optional[set] = None,
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

        ``degraded`` names the scopes this cycle's listing could not ask
        (issue-315); a session in one of them is not even checked, because its
        absence from ``open_refs`` says nothing about it.
        """
        degraded = degraded or set()
        for session in self.registry.list_sessions(status="active"):
            ref = session.work_item
            if ref.ref in open_refs or not provider.owns(ref):
                continue
            if provider.scope_of(ref) in degraded:
                logger.debug(
                    "%s is in a scope this cycle could not list; not asking "
                    "whether it ended",
                    ref.ref,
                )
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
        # Authorization guard (prompt-injection remediation). Who OPENED the work
        # item is evidence about exactly one thing: whether the poller may start
        # work on it by itself — a presence event spawns a session whose *subject*
        # is that item, and a listing carries the label but never who applied it,
        # so the author is the only proxy available for "a human wanted this"
        # (issue-197, decision-074). It is not evidence about a comment, which
        # carries its own author; those are judged one by one below, exactly as
        # the webhook path judges an event by its actor.
        item_authorized = is_authorized(item.author, self.authorized_users)
        # An authorized user's *recorded* arming command is better evidence of the
        # same thing — it names who asked and when — so either satisfies the
        # presence gate. Only the dispatcher writes that record, and only for a
        # NAMED allowlisted actor; a later stop/pause/cleanup revokes it, because
        # `start_requested` reads the last command.
        spawn_authorized = item_authorized or self.control_store.start_requested(ref)
        if item.author and not spawn_authorized:
            logger.warning(
                "not starting %s by myself: its author %r is not in "
                "authorizedUsers, and nobody has started it. Everything else on "
                "it is still acted on — an authorized user's comment is judged "
                "by its own author, and %s starts the item",
                ref,
                item.author,
                (
                    f"commenting {self.control.keyword('start')!r} on it"
                    if self.control.enabled and self.control.keyword("start")
                    else "`the-loop sessions start`"
                ),
            )
            eventlog.emit(
                "poll.unauthorized",
                level="warning",
                work_item=ref,
                actor=item.author,
            )
        # Resolved through stored bindings (issue-172): a PR whose linkage GitHub
        # no longer reports has only its own ref here, and asking the registry
        # directly would call it session-less — so a running item would be
        # treated as first sight, its whole thread baselined away, and a second
        # session armed against the PR.
        has_session = any(self.registry.record_owning(wi) is not None for wi in refs)

        # First sight: baseline the existing thread (the spawned session reads it
        # itself, matching webhook "only events going forward"), arm the spawn,
        # and stop. Only spawn when the item is vouched for (the input fed to
        # /the-loop:work-on is that item's own body).
        #
        # Except for control commands nobody has processed yet (issue-119).
        # Baselining means "resolved, never look at this again" — true of an
        # ordinary comment, false of an instruction to the-loop that has not run.
        # Those flow through the ordinary comment path below instead, so a start
        # posted BEFORE the poller first saw the item behaves exactly like one
        # posted after it (which is all the webhook path ever sees, label and
        # comment being two deliveries). Asked unconditionally: the method's own
        # guards are per COMMENT, so who opened the item never silences an
        # authorized user's instruction (issue-197).
        if first_sight:
            pending = self._pending_control_ids(ref, comments)
            self.state.baseline_comments(
                ref,
                [cid for cid in live_ids if cid not in pending],
                _utcnow(),
                title=item.title,
            )
            if not pending:
                if spawn_authorized and not has_session:
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
            # Two ways to be an input, one of them narrower (issue-307): the
            # global allow-list, or a collaborator grant on THIS item's refs. The
            # grant buys delivery and nothing else — `spawn_authorized` above and
            # `_pending_control_ids` below keep asking `is_authorized` alone, so a
            # collaborator can neither arm the item nor command the daemon.
            allowed = is_authorized(
                comment.author, self.authorized_users
            ) or self.collaborator_store.permits(comment.author, refs)
            if not allowed or is_self_authored(comment.body):
                if is_self_authored(comment.body):
                    self._publish("agent", ref, comment)
                self.state.resolve_comment(ref, comment.id)
                continue
            if self.state.comment_attempts(ref, comment.id) == 0:
                # First sight only: a forward retried on a later cycle must not
                # re-publish the comment to every channel each time.
                self._publish("human", ref, comment)
            candidates.append(comment)
        # A genuinely-new comment (never attempted) re-arms a spawn that had been
        # given up — a new comment retriggers the item (issue-80, AC6).
        genuinely_new = any(
            self.state.comment_attempts(ref, c.id) == 0 for c in candidates
        )

        # Spawn only when there is a reason to: genuinely new activity, or a spawn
        # already in progress (attempts recorded). A dormant known item with no
        # session and no new activity must not spontaneously spawn.
        if spawn_authorized and not has_session:
            if genuinely_new:
                self.state.reset_spawn(ref)
            if genuinely_new or self.state.spawn_attempts(ref) > 0:
                self._try_spawn(provider, item, refs, summary)
        elif has_session:
            self.state.reset_spawn(ref)

        # Forwarded whoever opened the item: every candidate has already passed
        # the guards that apply to a comment — its own author is allowlisted, and
        # it is not one of the-loop's own replies (issue-197).
        for comment in candidates:
            self._process_comment(provider, item, comment, refs, summary)

        self.state.finalize(ref, live_ids, _utcnow(), title=item.title)

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
        # spawn behind it, and don't count it a failure (a spawn can outlast a
        # poll cycle).
        last_did = self.state.spawn_delivery_id(ref)
        if last_did:
            status = self.dispatcher.delivery_status(last_did, refs)
            if status == "inflight":
                return
            if status == "done":  # session came up — belt and suspenders
                self._attempted.pop(last_did, None)
                self.state.reset_spawn(ref)
                return
            if status == "settled":
                # The dispatcher refused this presence on purpose (issue-270).
                # Resolved, not spent: a refusal must not accumulate toward
                # `maxRetries` and must not become a terminal `poll.spawn_failed`.
                # Reset rather than give up — the refusal says "not now", not
                # "never here", and `_try_spawn` is only reached again on
                # genuinely new activity.
                self._attempted.pop(last_did, None)
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
            self._attempted.pop(last_did, None)  # resolved: nothing left to release
            summary.failures += 1
            return
        event = provider.presence_event(item, refs)
        self.dispatcher.handle(event)
        self.state.note_spawn_attempt(ref, event.delivery_id)
        self._attempted[event.delivery_id] = (ref, "")
        summary.spawns += 1

    def _publish(self, kind: str, ref: str, comment: Comment) -> None:
        """Hand a comment to the bus as ``comment.<kind>`` — best-effort."""
        if self.publisher is None or not comment.body:
            return
        from ..channels.envelope import has_envelope

        if has_envelope(comment.body):
            return  # the bus's own record (A10): its source channel has it
        try:
            self.publisher(kind, ref, comment.author or "", comment.body, comment.url)
        except Exception:  # noqa: BLE001 — the bus never touches ingress
            logger.exception("comment publisher raised for %s", ref)

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
            self._attempted.pop(event.delivery_id, None)
            self.state.resolve_comment(ref, comment.id)
            return
        if status == "settled":
            # Settled on an earlier cycle, or by a worker after this cycle
            # recorded an attempt (a session paused between enqueue and
            # dispatch). Either way the retry counter must not be left standing.
            self._settle_comment(
                ref,
                comment,
                self.dispatcher.delivery_outcome(event.delivery_id),
                event.delivery_id,
            )
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
            self._attempted.pop(event.delivery_id, None)  # resolved, one way or another
            summary.failures += 1
            # The ledger is written FIRST, on purpose (issue-240): a slow or
            # hanging `gh` must never sit between "we gave up" and "it is
            # recorded", or a process killed in that window would retry a comment
            # it had already announced as abandoned.
            self._report_giveup(item, comment, attempts)
            return
        self.dispatcher.handle(event)
        outcome = self.dispatcher.delivery_outcome(event.delivery_id)
        if outcome:
            # Settled by the very call above — the item is not started, its
            # session is paused, or the comment WAS a control command. Resolved
            # here, before any attempt is recorded, so the ledger never claims a
            # pending retry for a delivery nobody is attempting (issue-270).
            self._settle_comment(ref, comment, outcome, event.delivery_id)
            return
        attempt = self.state.note_comment_attempt(ref, comment.id)
        self._attempted[event.delivery_id] = (ref, comment.id)
        eventlog.emit(
            "poll.comment_forwarded",
            work_item=ref,
            comment_id=comment.id,
            actor=comment.author,
            attempt=attempt,
        )
        summary.comments_forwarded += 1

    def _settle_comment(
        self, ref: str, comment: Comment, outcome: str, delivery_id: str
    ) -> None:
        """Resolve a comment the dispatcher is finished with (issue-270).

        Baselined — **not** abandoned. The difference is `gaveUp`, which records
        the CLI version that gave up so a later one can re-arm the comment
        (issue-146): a give-up is a statement about a *failing environment*, and
        an upgrade can invalidate it. A settlement is a decision, and re-arming a
        decision would re-forward the comment after the next upgrade — replay
        semantics nobody asked for, on a schedule nobody chose (the owner's call
        on the ticket was that the session re-reads the thread instead).

        `outcome` is the dispatcher's own literal and is recorded, not branched
        on: which suppressions and consumptions exist is the dispatcher's
        vocabulary, not the poller's.
        """
        self._attempted.pop(delivery_id, None)
        self.state.resolve_comment(ref, comment.id)
        logger.info(
            "%s: comment %s was not delivered as an event (%s); baselining it — "
            "nothing is replayed, and a session reads the thread itself",
            ref,
            comment.id,
            outcome,
        )
        eventlog.emit(
            "poll.comment_settled",
            work_item=ref,
            comment_id=comment.id,
            actor=comment.author,
            outcome=outcome,
            will_retry=False,
        )

    def _report_giveup(
        self, work_item: WorkItem, comment: Comment, attempts: int
    ) -> None:
        """Tell the ticket that ``comment`` was abandoned (issue-240).

        Best-effort in one direction only: it can fail to appear, and it can
        never change what the ledger already recorded — the caller writes the
        give-up before calling this, and every failure here is swallowed. A
        notice must not end a poll cycle.

        Posted **once** per abandoned comment, which follows from the caller's
        control flow rather than from bookkeeping here: the give-up baselines the
        comment id, so no later cycle reaches this branch for it again.

        Addressed to the **polled item**, not to ``refs[0]``: a PR's refs lead
        with the issue it is linked to (issue-93), which is the right target for
        *routing* the event and the wrong one for *answering* a comment — the
        human wrote it on the PR, and that is where they will look for the reply.
        """
        item = WorkItemRef(
            provider=work_item.provider,
            owner=work_item.owner,
            repo=work_item.repo,
            number=work_item.number,
            host=work_item.host,
        )
        try:
            ok, error = post_issue_comment(
                item,
                giveup_notice(
                    ref=item.ref,
                    comment_id=comment.id,
                    comment_url=comment.url,
                    attempts=attempts,
                ),
                gh_binary=self.dispatcher.config.announce.gh_binary,
                runner=self._comment_runner,
            )
        except Exception as exc:  # noqa: BLE001 — a notice never ends a cycle
            logger.warning(
                "could not report the abandoned comment %s on %s: %s",
                comment.id,
                item.ref,
                exc,
            )
            eventlog.emit(
                "poll.giveup_report_failed",
                level="warning",
                work_item=item.ref,
                comment_id=comment.id,
                error=str(exc),
            )
            return
        if ok:
            eventlog.emit(
                "poll.giveup_reported",
                work_item=item.ref,
                comment_id=comment.id,
                attempts=attempts,
            )
            return
        if error.endswith("not found on PATH"):
            # One warning per process, then silence — a machine without `gh`
            # would otherwise log this on every give-up.
            if not self._warned_missing_gh:
                self._warned_missing_gh = True
                logger.warning("%s — abandoned comments cannot be reported", error)
        elif "is not a GitHub one" in error or "unusable repo coordinates" in error:
            # A Jira (or other) provider has no `gh` endpoint. Not an error.
            logger.debug("%s; not reporting the abandoned comment", error)
        else:
            logger.warning(
                "could not report the abandoned comment %s on %s: %s",
                comment.id,
                item.ref,
                error,
            )
        eventlog.emit(
            "poll.giveup_report_failed",
            level="warning",
            work_item=item.ref,
            comment_id=comment.id,
            error=error,
        )

    # -- shutdown (issue-159) ---------------------------------------------------

    def release_abandoned(self, delivery_ids: Sequence[str]) -> int:
        """Hand back the retry budget of events that died queued at shutdown.

        The poller records an attempt when it *enqueues* an event and reads the
        outcome on a later cycle (issue-80). A shutdown drains what it can and
        the process then exits, so anything left in the dispatcher's queues was
        counted as an attempt but never delivered — and with
        ``polling.maxRetries`` at its default, three restarts would permanently
        abandon a comment nothing ever tried to deliver (the give-up is
        version-gated, issue-146, so nothing re-arms it until an upgrade).

        Takes the delivery ids :meth:`Dispatcher.stop` reports as abandoned,
        keeps the ones *this* process spent an attempt on, and un-counts them.
        The events stay **unresolved** — no baseline is written — so the next
        start rediscovers them with the budget it started with. Returns how many
        were released, for the log line.
        """
        released = 0
        for delivery_id in delivery_ids or ():
            entry = self._attempted.pop(delivery_id, None)
            if entry is None:
                continue
            ref, comment_id = entry
            if comment_id:
                self.state.release_comment_attempt(ref, comment_id)
            else:
                self.state.release_spawn_attempt(ref)
            released += 1
        if released:
            logger.info(
                "shutdown: %d dispatch(es) were still queued and never "
                "delivered; their retry attempts were returned so the next "
                "start retries them with a full budget",
                released,
            )
            eventlog.emit("poll.attempts_released", released=released)
        self.state.save()
        return released

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

        The event is passed *into* the cycle as well as checked around it
        (issue-159), so a stop is honoured within one work item rather than
        within one cycle.
        """
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            self._maybe_reload()
            try:
                self.poll_once(stop_event)
            except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
                logger.exception("poll cycle raised; continuing")
            if once:
                return
            stop_event.wait(self.config.interval_seconds)
