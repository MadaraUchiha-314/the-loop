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
(``routing.reactions`` in the CLI config). Enabled by
default (owner decision on PR #85 — visibility out of the box is the point);
set ``enabled: false`` to opt out of the daemon's one write surface to GitHub.

Everything is best-effort by design: a reaction must never fail, delay or drop
the dispatch itself, so every failure inside this module degrades to a logged
no-op. Reactions post through the daemon's GitHub client (issue-442: the token
``integrations.github.api.tokenEnv`` names); a missing token no-ops with a
single warning. Events from a non-GitHub provider, or with no reactable target
in their payload, no-op too.

Spec: docs/specs/issue-84/design.md.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from . import eventlog
from .comments import resolve_client
from .ghapi import REACTION_CONTENTS, GitHubApiConfig, GitHubApiError, GitHubClient
from .sessions import DEFAULT_GITHUB_HOST
from .webhook.router import RoutedEvent

logger = logging.getLogger("the-loop.reactions")

STATE_STARTED = "started"
STATE_COMPLETED = "completed"
STATE_ERROR = "error"

# GitHub's fixed reaction palette lives in `ghapi.REACTION_CONTENTS` (REST
# `content` value -> GraphQL ReactionContent member); the config accepts exactly
# those names (or "").

# Defensive validation of payload-derived API coordinates (the payloads are
# HMAC-verified / poll-sourced and authz-gated already, but they are still
# external data placed into a URL path or a GraphQL variable).
_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")  # owner / repo path segments
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9_=+/-]+$")  # GraphQL node ids


@dataclass
class ReactionConfig:
    """Mirror of ``routing.reactions`` (see config schema)."""

    enabled: bool = True
    started: str = "eyes"
    completed: str = "hooray"
    error: str = "confused"
    #: Where the token is (issue-442) — fanned in under the private `_github`
    #: key by `cli_config.apply_integrations`, the way `_ghBinary` once was.
    github: GitHubApiConfig = GitHubApiConfig()

    @classmethod
    def from_mapping(cls, data: dict) -> "ReactionConfig":
        data = data or {}
        return cls(
            enabled=bool(data.get("enabled", True)),
            started=str(data.get("started", "eyes")),
            completed=str(data.get("completed", "hooray")),
            error=str(data.get("error", "confused")),
            github=GitHubApiConfig.from_mapping(data.get("_github")),
        )

    def content_for(self, state: str) -> str:
        """The configured reaction name for ``state`` ('' = skip that state)."""
        return {
            STATE_STARTED: self.started,
            STATE_COMPLETED: self.completed,
            STATE_ERROR: self.error,
        }.get(state, "")


#: The REST targets, by the endpoint each reaches (`ghapi.REACTION_KINDS`).
KIND_ISSUE = "issue"  # POST repos/o/r/issues/{n}/reactions — an issue or a PR
KIND_ISSUE_COMMENT = "issue-comment"  # POST repos/o/r/issues/comments/{id}/reactions
KIND_REVIEW_COMMENT = "review-comment"  # POST repos/o/r/pulls/comments/{id}/reactions


@dataclass(frozen=True)
class ReactionTarget:
    """Where a reaction lands: a REST target by kind and numeric id, or a
    GraphQL subject by node id."""

    owner: str
    repo: str
    kind: str = ""  # one of the three REST kinds, when the target has a numeric id
    id: int = 0  # that numeric id
    node_id: str = ""  # GraphQL subject id, when that's what the payload has
    description: str = ""  # human-readable, for logs/eventlog only
    host: str = ""  # the work item's GitHub when not github.com (issue-311)


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

    # The host is the work item's (issue-311): every work item on one event
    # came off one payload, so the first GitHub one answers for the call.
    host = next(
        (item.host for item in routed.work_items if item.provider == "github"), ""
    )
    if host == DEFAULT_GITHUB_HOST:
        host = ""

    comment = payload.get("comment") or {}
    node_id = str(comment.get("node_id") or "")
    if node_id and _NODE_ID_RE.match(node_id):
        return ReactionTarget(
            owner, repo, node_id=node_id, description="comment", host=host
        )
    raw_id = comment.get("id")
    if raw_id is not None:
        comment_id = str(raw_id)
        if comment_id.isdigit():
            # Review comments live under /pulls, conversation comments /issues.
            kind = (
                KIND_REVIEW_COMMENT
                if routed.event == "pull_request_review_comment"
                else KIND_ISSUE_COMMENT
            )
            return ReactionTarget(
                owner,
                repo,
                kind=kind,
                id=int(comment_id),
                description="comment",
                host=host,
            )
        if _NODE_ID_RE.match(comment_id):
            # Poll-path comments carry the GraphQL node id in `id`
            # (the client's conversation read keeps node ids, issue-246).
            return ReactionTarget(
                owner, repo, node_id=comment_id, description="comment", host=host
            )
        return None

    entity = payload.get("issue") or payload.get("pull_request") or {}
    number = str(entity.get("number") or "")
    if number.isdigit():
        kind = "issue" if payload.get("issue") else "pull-request"
        return ReactionTarget(
            owner, repo, kind=KIND_ISSUE, id=int(number), description=kind, host=host
        )
    return None


class GitHubReactor:
    """Posts dispatch-lifecycle reactions through the daemon's GitHub client.

    Never raises: every failure path is a logged no-op returning ``False`` —
    the dispatch outcome must not depend on a decoration. ``client`` is
    injectable so tests drive it without a network.
    """

    def __init__(
        self,
        config: Optional[ReactionConfig] = None,
        client: Optional[GitHubClient] = None,
        timeout: Optional[float] = 30.0,
    ):
        self.config = config or ReactionConfig()
        self.timeout = timeout
        self._client = resolve_client(self.config.github, client, timeout)
        self._warned_missing_token = False

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
        work_item = routed.work_items[0].ref if routed.work_items else ""
        try:
            if target.node_id:
                self._client.add_reaction_by_node(
                    target.node_id, content, host=target.host
                )
            else:
                self._client.add_reaction(
                    target.owner,
                    target.repo,
                    target.kind,
                    target.id,
                    content,
                    host=target.host,
                )
        except GitHubApiError as exc:
            if exc.missing_token:
                if not self._warned_missing_token:
                    self._warned_missing_token = True
                    logger.warning(
                        "%s — dispatch reactions are a no-op (set the token or "
                        "routing.reactions.enabled: false)",
                        exc,
                    )
                return False
            return self._failed(work_item, state, content, str(exc))
        except Exception as exc:  # noqa: BLE001 — a decoration never raises
            return self._failed(work_item, state, content, str(exc))
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
