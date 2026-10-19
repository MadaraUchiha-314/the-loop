"""The gateway's poller (issue-496, R1.5, R1.6, R7.1, R7.3, R7.4).

Reuses the instance poller's **source** layer — :class:`~the_loop.poller.base.PollProvider`
and its GitHub and Jira implementations — and replaces its core: the ledger lives in the
store (``poll_ledger`` and ``poll_seen``), the retry and dispatch half is the subject's
(``attempt`` on the delivery, dead-letter at ``store.maxAttempts``), and the dispatcher's
synchronous ``delivery_outcome`` becomes the instance's **commit outcome**, which the
client sends back with its next fetch and :meth:`PollAdapter.on_commit` applies.

The events are the provider's own builders — ``presence_event``, ``comment_event``,
``ci_events``, ``closure_event`` — so a polled delivery carries the same id
(``poll-comment-<id>``, ``poll-presence-<ref>-<uuid>``, …) and the same webhook-shaped
payload the instance poller produces today (R1.5), and the cross-transport dedup key
(``gh-comment-<id>``) makes a webhook and a poll of one comment one row (R7.3, R7.4).
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, List, Optional, Sequence

from ...poller.base import PollProvider, ProviderError, WorkItem
from ..config import GatewayConfig
from .ingest import Ingest, Outcome

__all__ = [
    "PollAdapter",
    "PollCycle",
    "apply_commit_outcome",
    "build_github_providers",
    "build_jira_providers",
]

logger = logging.getLogger("the-loop.gateway.poll")

#: Presence states the ledger keeps (design §gateway/adapters/poll.py).
UNKNOWN, AWAITING_START, SPAWNED, SETTLED, CLOSED = (
    "unknown",
    "awaiting-start",
    "spawned",
    "settled",
    "closed",
)
#: Read CI this often, in cycles, so a 60 s poll asks the checks API every 5 minutes
#: — the instance poller's `polling.ci.intervalSeconds` default.
CI_INTERVAL_S = 300


@dataclass
class PollCycle:
    items: int = 0
    stored: int = 0
    duplicates: int = 0
    dropped: int = 0
    errors: List[str] = field(default_factory=list)


class PollAdapter:
    """One poll source, polled on a thread every ``interval_s``."""

    def __init__(
        self,
        provider: PollProvider,
        ingest: Ingest,
        *,
        interval_s: float,
        provider_name: str = "github",
    ) -> None:
        self.provider = provider
        self.ingest = ingest
        self.store = ingest.state.store
        self.interval_s = max(1.0, float(interval_s))
        self.provider_name = provider_name
        self._ci_last: Optional[float] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- lifecycle --------------------------------------------------------------------------

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"gateway-poll-{self.provider.describe()}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 — a cycle never ends the poller
                logger.exception(
                    "gateway: poll cycle of %s raised", self.provider.describe()
                )
            self._stop.wait(self.interval_s)

    # -- one cycle ----------------------------------------------------------------------------

    def poll_once(self) -> PollCycle:
        cycle = PollCycle()
        try:
            listing = self.provider.listing()
        except ProviderError as exc:
            logger.error(
                "gateway: polling %s failed: %s", self.provider.describe(), exc
            )
            cycle.errors.append(str(exc))
            return cycle
        open_refs: set = set()
        ci_due = self._ci_due()
        for item in listing.items:
            if self._stop.is_set():
                break
            cycle.items += 1
            try:
                refs = self.provider.refs(item)
                open_refs.update(ref.ref for ref in refs)
                self._item(item, refs, cycle, ci_due)
            except ProviderError as exc:
                logger.error("gateway: processing %s failed: %s", item.ref, exc)
                cycle.errors.append(f"{item.ref}: {exc}")
        if not listing.failures and not listing.skipped:
            self._reconcile(open_refs, cycle)
        return cycle

    def _ci_due(self) -> bool:
        now = time.monotonic()
        if self._ci_last is not None and now - self._ci_last < CI_INTERVAL_S:
            return False
        self._ci_last = now
        return True

    def _accept(self, routed: Any, cycle: PollCycle, actor: str = "") -> Outcome:
        outcome = self.ingest.accept(
            self.provider_name,
            "poll",
            routed.event,
            routed.delivery_id,
            {},
            b"",
            payload=routed.payload,
            actor=actor or None,
        )
        if outcome.status == "stored":
            cycle.stored += 1
        elif outcome.status == "duplicate":
            cycle.duplicates += 1
        else:
            cycle.dropped += 1
        return outcome

    def _item(
        self, item: WorkItem, refs: Sequence[Any], cycle: PollCycle, ci_due: bool
    ) -> None:
        ref = item.ref
        state = self.store.poll_state(ref)
        if state == UNKNOWN:
            self.store.set_poll_state(ref, UNKNOWN)
        # presence: offered while nobody has judged the item started, and never twice at once
        if state in (UNKNOWN, AWAITING_START) and not self.store.has_pending_presence(
            ref
        ):
            self._accept(
                self.provider.presence_event(item, list(refs)), cycle, actor=item.author
            )
        # comments: each new one once; "seen" means stored durably
        for comment in self.provider.list_comments(item):
            if self.store.poll_seen(ref, comment.id):
                continue
            outcome = self._accept(
                self.provider.comment_event(item, comment, list(refs)),
                cycle,
                actor=comment.author,
            )
            if outcome.accepted:
                self.store.poll_mark_seen(ref, comment.id)
        if ci_due:
            try:
                for _check, _value, routed in self.provider.ci_events(item, list(refs)):
                    self._accept(routed, cycle)
            except ProviderError as exc:
                cycle.errors.append(f"{ref} checks: {exc}")

    def _reconcile(self, open_refs: set, cycle: PollCycle) -> None:
        """A ref the ledger knows that the listing no longer shows has ended, or lost
        its labels: ask the provider, and store the webhook-shaped closure once."""
        from ...sessions import WorkItemRef

        for ref in self.store.poll_refs():
            if ref in open_refs:
                continue
            try:
                parsed = WorkItemRef.parse(ref)
            except Exception:  # noqa: BLE001 — a ref another provider wrote
                continue
            if not self.provider.owns(parsed):
                continue
            try:
                closure = self.provider.closure(parsed)
            except ProviderError as exc:
                cycle.errors.append(f"{ref} closure: {exc}")
                continue
            if closure is None:
                continue
            self._accept(self.provider.closure_event(parsed, closure), cycle)
            self.store.set_poll_state(ref, CLOSED)


def apply_commit_outcome(store: Any, event: Any, outcome: str) -> None:
    """Update the poll ledger from one committed delivery's outcome — the half of R3.4
    that crosses the process boundary. Called by the consume API for every applied
    commit; a non-presence event is ignored."""
    if event is None or not event.work_item:
        return
    if not str(event.delivery_id).startswith("poll-presence-"):
        return
    head, _, reason = outcome.partition(":")
    if head in ("spawned", "delivered"):
        store.set_poll_state(event.work_item, SPAWNED)
    elif head == "dropped" and reason == "awaiting-start":
        store.set_poll_state(event.work_item, AWAITING_START)
    elif head == "dropped":
        store.set_poll_state(event.work_item, f"{SETTLED}:{reason}")


# -- providers from the gateway config -----------------------------------------------------------


def build_github_providers(
    config: GatewayConfig, *, api: Any = None
) -> List[PollProvider]:
    """One :class:`~the_loop.poller.github.GitHubPollProvider` per declared source,
    reading with the token the config names (read access is all it needs)."""
    from ...ghapi import GitHubApiConfig, GitHubClient
    from ...poller.github import GitHubPollProvider, parse_repos

    if config.github is None or not config.github.poll.enabled:
        return []
    client = api or GitHubClient(
        GitHubApiConfig(token_envs=(config.github.poll.token_env,))
    )
    providers: List[PollProvider] = []
    for source in config.github.poll.sources:
        providers.append(
            GitHubPollProvider(
                repos=parse_repos([source.repository]),
                labels=list(source.labels),
                monitor_issues=source.issues,
                monitor_prs=source.pull_requests,
                api=client,
            )
        )
    return providers


def build_jira_providers(config: GatewayConfig) -> List[PollProvider]:
    from ...jiraapi import JiraApiConfig, JiraClient
    from ...poller.jira import JiraPollProvider

    if config.jira is None or not config.jira.poll.enabled or not config.jira.projects:
        return []
    poll = config.jira.poll
    api = JiraApiConfig(
        site=poll.site, email_env=(poll.email_env,), token_env=(poll.token_env,)
    )
    return [
        JiraPollProvider(
            projects=list(config.jira.projects),
            labels=list(poll.labels),
            site=poll.site,
            client=JiraClient.shared(api),
        )
    ]
