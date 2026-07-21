"""Poll GitHub via ``gh`` and drive the existing router/dispatcher (issue-34).

Webhooks are push; the poller is *pull* for hosts a webhook cannot reach. It
periodically asks ``gh`` for the issues/PRs carrying the configured
auto-execute label and synthesises the same ``RoutedEvent`` shape the webhook
receiver produces — so **all** downstream behaviour is reused unchanged: the
session registry (one session per work item — no duplicate spawns), the
per-session FIFO dispatcher, the tmux runner, the harness adapters and the
prompt templates.

The poller's only new responsibilities are ingress-specific:

* **discover** labelled work items (``gh issue/pr list``);
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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..sessions import SessionRegistry, WorkItemRef
from ..webhook.dispatcher import Dispatcher
from ..webhook.router import RoutedEvent, event_carries_label, extract_work_items
from .github import GhClient, GhComment, GhError, GhItem, RepoSpec, parse_repos

logger = logging.getLogger("the-loop.gh-poll")

# Per item, how many comment ids we remember across polls. The set is re-seeded
# from the live comment list every cycle, so this only caps a single very
# chatty thread; the newest comments always stay in the window.
_SEEN_COMMENTS_CAP = 500


@dataclass
class PollConfig:
    """Python mirror of ``polling.ghPoll`` — poll-ingress knobs only.

    Dispatch behaviour (registry dir, harness, runner, spawn policy, templates)
    is reused from ``webhooks.ghWebhook.routing`` via :class:`RoutingConfig`,
    so polling and webhooks spawn/route identically.
    """

    interval_seconds: int = 60
    repos: List[str] = field(default_factory=list)
    monitor_issues: bool = True
    monitor_prs: bool = True
    label: str = ""  # empty -> routing.autoExecuteLabel
    state_file: str = ".the-loop/poll-state.json"
    gh_binary: str = "gh"

    @classmethod
    def from_mapping(cls, data: Optional[dict]) -> "PollConfig":
        data = data or {}
        monitor = data.get("monitor") or {}
        return cls(
            interval_seconds=int(data.get("intervalSeconds", 60)),
            repos=[str(r) for r in (data.get("repos") or [])],
            monitor_issues=bool(monitor.get("issues", True)),
            monitor_prs=bool(monitor.get("pullRequests", True)),
            label=str(data.get("label", "")),
            state_file=str(data.get("stateFile", ".the-loop/poll-state.json")),
            gh_binary=str(data.get("ghBinary", "gh")),
        )


class PollState:
    """Durable, atomic-write record of which comments each item has processed.

    One JSON file keyed by work-item ref. It exists so the poller is idempotent
    across cycles *and* restarts (there is no GitHub redelivery to lean on) —
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
        # Keep the most-recent ids (list order from gh is oldest-first).
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


class Poller:
    """Discover labelled items via ``gh`` and feed them to the dispatcher."""

    def __init__(
        self,
        gh: GhClient,
        registry: SessionRegistry,
        dispatcher: Dispatcher,
        config: PollConfig,
        auto_execute_label: str,
        state: PollState,
    ):
        self.gh = gh
        self.registry = registry
        self.dispatcher = dispatcher
        self.config = config
        # Poll-specific label wins; else fall back to the routing label.
        self.label = config.label or auto_execute_label
        self.state = state

    def repos(self) -> List[RepoSpec]:
        return parse_repos(self.config.repos)

    # -- one cycle --------------------------------------------------------------

    def poll_once(self) -> PollSummary:
        """Run a single discovery→dispatch pass over every configured repo."""
        summary = PollSummary()
        for spec in self.repos():
            self._poll_repo(spec, summary)
        self.state.save()
        logger.info(
            "poll cycle: %d item(s), %d spawn(s), %d comment(s) forwarded%s",
            summary.items_seen,
            summary.spawns,
            summary.comments_forwarded,
            f", {len(summary.errors)} error(s)" if summary.errors else "",
        )
        return summary

    def _poll_repo(self, spec: RepoSpec, summary: PollSummary) -> None:
        items: List[GhItem] = []
        try:
            if self.config.monitor_issues:
                items += self.gh.list_labeled_issues(spec.owner, spec.repo, self.label)
            if self.config.monitor_prs:
                items += self.gh.list_labeled_prs(spec.owner, spec.repo, self.label)
        except GhError as exc:
            logger.error("listing %s failed: %s", spec.full_name, exc)
            summary.errors.append(f"{spec.full_name}: {exc}")
            return
        for item in items:
            summary.items_seen += 1
            try:
                self._process_item(spec, item, summary)
            except GhError as exc:
                ref = f"github:{spec.full_name}#{item.number}"
                logger.error("processing %s failed: %s", ref, exc)
                summary.errors.append(f"{ref}: {exc}")

    def _process_item(self, spec: RepoSpec, item: GhItem, summary: PollSummary) -> None:
        payload = self._item_payload(spec, item)
        event = "pull_request" if item.is_pr else "issues"
        work_items = extract_work_items(event, payload)
        if not work_items:
            return
        ref = f"github:{spec.full_name}#{item.number}"

        comments = self.gh.list_comments(spec.owner, spec.repo, item.number, item.is_pr)
        first_sight = not self.state.is_known(ref)
        seen = self.state.seen_comments(ref)
        new_comments = [c for c in comments if c.id and c.id not in seen]
        has_session = any(
            self.registry.find_by_work_item(wi) is not None for wi in work_items
        )

        # Spawn a session for a labelled item that has none — on first sight, or
        # when fresh activity arrives after a prior session ended. The registry
        # (one active session per work item) is the source of truth, so a failed
        # spawn simply retries next cycle and a live session is never doubled.
        if not has_session and (first_sight or new_comments):
            self.dispatcher.handle(self._presence_event(event, payload, work_items))
            summary.spawns += 1

        # Forward only genuinely new comments; on first sight the existing
        # thread is the baseline (the spawned session reads it itself), matching
        # webhook semantics where you only receive events going forward.
        if not first_sight:
            for comment in new_comments:
                self.dispatcher.handle(
                    self._comment_event(spec, item, payload, work_items, comment)
                )
                summary.comments_forwarded += 1

        self.state.update(ref, [c.id for c in comments if c.id], _utcnow())

    # -- synthetic events -------------------------------------------------------

    def _item_payload(self, spec: RepoSpec, item: GhItem) -> dict:
        """A webhook-shaped payload so router helpers and templates work as-is."""
        labels = [{"name": name} for name in item.labels]
        payload: dict = {
            "action": "labeled",
            "repository": {"full_name": spec.full_name},
        }
        entity = {
            "number": item.number,
            "title": item.title,
            "html_url": item.url,
            "labels": labels,
        }
        if item.is_pr:
            entity["head"] = {"ref": item.head_ref}
            entity["body"] = item.body
            payload["pull_request"] = entity
        else:
            payload["issue"] = entity
        return payload

    def _presence_event(
        self, event: str, payload: dict, work_items: List[WorkItemRef]
    ) -> RoutedEvent:
        # Fresh delivery id every emission: we only emit while no session
        # exists, so a failed spawn retries next cycle instead of being deduped.
        ref = work_items[0].ref
        return RoutedEvent(
            event=event,
            action="labeled",
            delivery_id=f"poll-presence-{ref}-{uuid.uuid4()}",
            work_items=work_items,
            payload=payload,
            labeled=event_carries_label(payload, self.label),
        )

    def _comment_event(
        self,
        spec: RepoSpec,
        item: GhItem,
        item_payload: dict,
        work_items: List[WorkItemRef],
        comment: GhComment,
    ) -> RoutedEvent:
        # issue_comment carries both issues and PR conversation comments on
        # GitHub; reuse the item's work items so a PR comment still reaches a
        # session registered against the linked issue. labeled=False: comments
        # only feed existing sessions, never spawn (spawning is presence's job).
        payload = dict(item_payload)
        payload["action"] = "created"
        payload["comment"] = {
            "id": comment.id,
            "body": comment.body,
            "html_url": comment.url,
            "created_at": comment.created_at,
            "user": {"login": comment.author},
        }
        return RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id=f"poll-comment-{comment.id}",
            work_items=work_items,
            payload=payload,
            labeled=False,
        )

    # -- run loop ---------------------------------------------------------------

    def run(
        self,
        once: bool = False,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Poll forever (or once), waking early when ``stop_event`` is set."""
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001 — one bad cycle must not kill the loop
                logger.exception("poll cycle raised; continuing")
            if once:
                return
            stop_event.wait(self.config.interval_seconds)
