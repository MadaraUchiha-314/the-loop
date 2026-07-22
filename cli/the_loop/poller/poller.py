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

from ..authz import is_authorized
from ..reload import Reloader
from ..sessions import SessionRegistry
from ..webhook.dispatcher import Dispatcher
from .base import PollProvider, ProviderError, WorkItem

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
    sources: List[dict] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "PollConfig":
        data = data or {}
        return cls(
            interval_seconds=int(data.get("intervalSeconds", 60)),
            state_file=str(data.get("stateFile", ".the-loop/poll-state.json")),
            sources=[dict(s) for s in (data.get("sources") or []) if s],
        )


class PollState:
    """Durable, atomic-write record of which comments each item has processed.

    One JSON file keyed by work-item ref. It exists so the poller is idempotent
    across cycles *and* restarts (there is no webhook redelivery to lean on) —
    the very guarantee that keeps a comment from re-triggering the harness.
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

    def is_known(self, ref: str) -> bool:
        return ref in self._items

    def seen_comments(self, ref: str) -> set:
        return set((self._items.get(ref) or {}).get("seenComments") or [])

    def update(self, ref: str, comment_ids: Sequence[str], polled_at: str) -> None:
        # Keep the most-recent ids (list order from providers is oldest-first).
        ids = list(dict.fromkeys(comment_ids))[-_SEEN_COMMENTS_CAP:]
        self._items[ref] = {"seenComments": ids, "lastPolledAt": polled_at}

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
            "poll cycle: %d item(s), %d spawn(s), %d comment(s) forwarded%s",
            summary.items_seen,
            summary.spawns,
            summary.comments_forwarded,
            f", {len(summary.errors)} error(s)" if summary.errors else "",
        )
        return summary

    def _poll_provider(self, provider: PollProvider, summary: PollSummary) -> None:
        try:
            items = provider.list_work_items()
        except ProviderError as exc:
            logger.error("polling %s failed: %s", provider.describe(), exc)
            summary.errors.append(f"{provider.describe()}: {exc}")
            return
        for item in items:
            summary.items_seen += 1
            try:
                self._process_item(provider, item, summary)
            except ProviderError as exc:
                logger.error("processing %s failed: %s", item.ref, exc)
                summary.errors.append(f"{item.ref}: {exc}")

    def _process_item(
        self, provider: PollProvider, item: WorkItem, summary: PollSummary
    ) -> None:
        refs = provider.refs(item)
        if not refs:
            return
        ref = item.ref

        comments = provider.list_comments(item)
        first_sight = not self.state.is_known(ref)
        seen = self.state.seen_comments(ref)
        # Authorization guard (prompt-injection remediation): only act on input
        # authored by an authorized user. A dropped comment is still baselined
        # below, so it is never re-evaluated on later cycles.
        item_authorized = is_authorized(item.author, self.authorized_users)
        new_comments = [
            c
            for c in comments
            if c.id
            and c.id not in seen
            and is_authorized(c.author, self.authorized_users)
        ]
        if item.author and not item_authorized:
            logger.warning(
                "ignoring %s from unauthorized author %r (not in authorizedUsers)",
                ref,
                item.author,
            )
        has_session = any(
            self.registry.find_by_work_item(wi) is not None for wi in refs
        )

        # Spawn a session for a labelled item that has none — on first sight, or
        # when fresh activity arrives after a prior session ended. The registry
        # (one active session per work item) is the source of truth, so a failed
        # spawn simply retries next cycle and a live session is never doubled.
        # Only spawn for items an authorized user authored (the input we'd feed
        # to /the-loop:work-on is that item's own body).
        if item_authorized and not has_session and (first_sight or new_comments):
            self.dispatcher.handle(provider.presence_event(item, refs))
            summary.spawns += 1

        # Forward only genuinely new, authorized comments; on first sight the
        # existing thread is the baseline (the spawned session reads it itself),
        # matching webhook semantics where you only receive events going forward.
        if not first_sight:
            for comment in new_comments:
                self.dispatcher.handle(provider.comment_event(item, comment, refs))
                summary.comments_forwarded += 1

        self.state.update(ref, [c.id for c in comments if c.id], _utcnow())

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
