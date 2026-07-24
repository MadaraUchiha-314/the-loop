"""Best-effort emoji reactions acknowledging dispatch lifecycle (issue-84).

Before this module, the first visible signal that the-loop picked up a comment
or work item was the harness's reply after the work was done. Now the
dispatcher acknowledges on the triggering GitHub entity itself: the configured
*started* reaction (default 👀 ``eyes``) when an event is dequeued for
delivery/spawn, *completed* (default 🎉 ``hooray``) when the dispatch
succeeds, and *error* (default 😕 ``confused``) when it fails.

GitHub's reaction palette is fixed (``+1 -1 laugh confused heart hooray rocket
eyes``) — ✅/⁉️ from the original ask do not exist, so the defaults map each
state to the closest supported emoji and the mapping is operator-configurable
(``webhooks.ghWebhook.routing.reactions`` in the CLI config; disabled by
default — this is the daemon's first write surface to GitHub).

Everything is best-effort by design: a reaction must never fail, delay or drop
the dispatch itself, so every failure inside this module degrades to a logged
no-op. Reactions post through the operator's own ``gh`` CLI (the poller's auth
posture — no token of the-loop's own); a missing ``gh`` no-ops with a single
warning so the CLI's zero-required-dependency guarantee holds. Events from a
non-GitHub provider, or with no reactable target in their payload, no-op too.

Spec: docs/specs/issue-84/design.md.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from . import eventlog
from .webhook.router import RoutedEvent

logger = logging.getLogger("the-loop.reactions")

STATE_STARTED = "started"
STATE_COMPLETED = "completed"
STATE_ERROR = "error"

# GitHub's fixed reaction palette: REST `content` value -> GraphQL
# ReactionContent enum member. The config accepts exactly these names (or "").
REACTION_CONTENTS = {
    "+1": "THUMBS_UP",
    "-1": "THUMBS_DOWN",
    "laugh": "LAUGH",
    "confused": "CONFUSED",
    "heart": "HEART",
    "hooray": "HOORAY",
    "rocket": "ROCKET",
    "eyes": "EYES",
}

_ADD_REACTION_MUTATION = (
    "mutation($subjectId: ID!, $content: ReactionContent!) "
    "{ addReaction(input: {subjectId: $subjectId, content: $content}) "
    "{ clientMutationId } }"
)

# Defensive validation of payload-derived API coordinates (the payloads are
# HMAC-verified / gh-sourced and authz-gated already, but they are still
# external data placed into a gh argv).
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")  # owner / repo path segments
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_=+/-]+$")  # GraphQL node ids


@dataclass
class ReactionConfig:
    """Mirror of ``webhooks.ghWebhook.routing.reactions`` (see config schema)."""

    enabled: bool = False
    started: str = "eyes"
    completed: str = "hooray"
    error: str = "confused"
    gh_binary: str = "gh"

    @classmethod
    def from_mapping(cls, data: dict) -> "ReactionConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", False)),
            started=str(data.get("started", "eyes")),
            completed=str(data.get("completed", "hooray")),
            error=str(data.get("error", "confused")),
            gh_binary=str(data.get("ghBinary", "gh")),
        )

    def content_for(self, state: str) -> str:
        """The configured reaction name for ``state`` ('' = skip that state)."""
        return {
            STATE_STARTED: self.started,
            STATE_COMPLETED: self.completed,
            STATE_ERROR: self.error,
        }.get(state, "")


@dataclass(frozen=True)
class ReactionTarget:
    """Where a reaction lands: a REST reactions endpoint or a GraphQL subject."""

    owner: str
    repo: str
    rest_path: str = ""  # relative REST path, when the target has a numeric id
    node_id: str = ""  # GraphQL subject id, when that's what the payload has
    description: str = ""  # human-readable, for logs/eventlog only


def target_from_event(routed: RoutedEvent) -> Optional[ReactionTarget]:
    """Resolve the reactable entity a routed event concerns, or ``None``.

    ``None`` means "no-op": a non-GitHub provider, a payload without a
    repository, a CI event with neither comment nor issue/PR, or coordinates
    that fail defensive validation. A comment (webhook numeric id, webhook
    node_id, or poll-path GraphQL node id in ``id``) wins over the issue/PR;
    reviews and presence events fall back to the issue/PR itself (GitHub
    treats PRs as issues for reactions).
    """
    if not any(item.provider == "github" for item in routed.work_items):
        return None
    payload = routed.payload or {}
    full_name = str((payload.get("repository") or {}).get("full_name") or "")
    owner, sep, repo = full_name.partition("/")
    if not sep or not _NAME_RE.match(owner) or not _NAME_RE.match(repo):
        return None

    comment = payload.get("comment") or {}
    node_id = str(comment.get("node_id") or "")
    if node_id and _NODE_ID_RE.match(node_id):
        return ReactionTarget(owner, repo, node_id=node_id, description="comment")
    raw_id = comment.get("id")
    if raw_id is not None:
        comment_id = str(raw_id)
        if comment_id.isdigit():
            # Review comments live under /pulls, conversation comments /issues.
            base = (
                "pulls" if routed.event == "pull_request_review_comment" else "issues"
            )
            path = f"repos/{owner}/{repo}/{base}/comments/{comment_id}/reactions"
            return ReactionTarget(owner, repo, rest_path=path, description="comment")
        if _NODE_ID_RE.match(comment_id):
            # Poll-path comments carry the GraphQL node id in `id`
            # (GhClient._comment_from_json).
            return ReactionTarget(
                owner, repo, node_id=comment_id, description="comment"
            )
        return None

    entity = payload.get("issue") or payload.get("pull_request") or {}
    number = str(entity.get("number") or "")
    if number.isdigit():
        path = f"repos/{owner}/{repo}/issues/{number}/reactions"
        kind = "issue" if payload.get("issue") else "pull-request"
        return ReactionTarget(owner, repo, rest_path=path, description=kind)
    return None


class GitHubReactor:
    """Posts dispatch-lifecycle reactions through the operator's ``gh`` CLI.

    Never raises: every failure path is a logged no-op returning ``False`` —
    the dispatch outcome must not depend on a decoration. ``runner`` is
    injectable so tests drive it without a real ``gh`` (mirrors ``GhClient``).
    """

    def __init__(
        self,
        config: Optional[ReactionConfig] = None,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout: Optional[float] = 30.0,
    ):
        self.config = config or ReactionConfig()
        self._runner = runner
        self.timeout = timeout
        self._warned_missing_gh = False

    def react(self, routed: RoutedEvent, state: str) -> bool:
        """Add the configured reaction for ``state`` to the event's entity."""
        config = self.config
        if not config.enabled:
            return False
        content = config.content_for(state)
        if not content:
            return False  # state explicitly skipped ("")
        if content not in REACTION_CONTENTS:
            logger.warning(
                "unknown reaction %r configured for %s (supported: %s); skipping",
                content,
                state,
                " ".join(REACTION_CONTENTS),
            )
            return False
        target = target_from_event(routed)
        if target is None:
            logger.debug(
                "event %s carries no reactable GitHub target; skipping %s reaction",
                routed.event,
                state,
            )
            return False
        if shutil.which(config.gh_binary) is None:
            if not self._warned_missing_gh:
                self._warned_missing_gh = True
                logger.warning(
                    "gh CLI %r not found on PATH — dispatch reactions are a "
                    "no-op (install gh or set routing.reactions.enabled: false)",
                    config.gh_binary,
                )
            return False

        work_item = routed.work_items[0].ref if routed.work_items else ""
        cmd = [config.gh_binary] + self._argv(target, content)
        try:
            proc = self._runner(
                cmd, capture_output=True, text=True, timeout=self.timeout
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._failed(work_item, state, content, str(exc))
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            return self._failed(
                work_item, state, content, f"gh exited {proc.returncode}: {detail}"
            )
        logger.debug(
            "reacted %s (%s) on %s for %s",
            content,
            state,
            target.description,
            work_item,
        )
        eventlog.emit(
            "reaction.added",
            level="debug",
            work_item=work_item or None,
            state=state,
            content=content,
            target=target.description,
        )
        return True

    @staticmethod
    def _argv(target: ReactionTarget, content: str) -> list:
        if target.rest_path:
            return [
                "api",
                "--method",
                "POST",
                target.rest_path,
                "-f",
                f"content={content}",
            ]
        return [
            "api",
            "graphql",
            "-f",
            f"query={_ADD_REACTION_MUTATION}",
            "-f",
            f"subjectId={target.node_id}",
            "-f",
            f"content={REACTION_CONTENTS[content]}",
        ]

    def _failed(self, work_item: str, state: str, content: str, error: str) -> bool:
        logger.warning(
            "could not add %s (%s) reaction for %s: %s",
            content,
            state,
            work_item,
            error,
        )
        eventlog.emit(
            "reaction.failed",
            level="warning",
            work_item=work_item or None,
            state=state,
            content=content,
            error=error,
        )
        return False
