"""The GitHub ledger — the channel of record (issue-309, decision-103).

GitHub was always where the-loop's conversation *lived*; issue-309 makes that a role
with a name. The ledger does one thing no other channel does: it **records** every
event that originated elsewhere, before any other channel receives it, so the work
item stays the single source of truth whatever surface the human actually used.

Four record shapes, chosen by event type — and the choice is the security design:

======================  =======================================  ======  ========
event                   body                                     marker  envelope
======================  =======================================  ======  ========
session.awaiting_input  the question (the record IS the ask)     yes     yes
work-item.reply,        quoted, scrubbed, keywords defanged      yes     yes
context.added,          (issue-389: the act named on the line)
decision.recorded
gate.feedback,          quoted, scrubbed, keywords **kept**      **no**  yes
control.command
work-item.create        a new issue: title + body                no      yes
======================  =======================================  ======  ========

The unmarked rows are the point. the-loop writes with the operator's own credentials
(decision-023), so a comment it posts *without* the self-authored marker is, to both
ingresses, a comment by an authorized user — and every guard that exists for such a
comment runs on it unchanged: the marker check, ``authorizedUsers``, the control
seam's named-actor re-check, ``classify-feedback``'s authorized-author filter. That
is how a channel advances the loop: **through the ledger, never around it.**
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

from ..ghapi import GitHubApiConfig
from ..sessions import WorkItemRef
from .base import Event, PostResult
from .bodies import (  # noqa: F401 — re-exported: the GitHub module's public names
    TITLE_MAX_CHARS,
    ask_body,
    control_keywords,
    issue_body,
    issue_title,
    ledger_body,
    mirror_body,
    relay_body,
)

logger = logging.getLogger("the-loop.channels")

__all__ = [
    "GitHubLedger",
    "TITLE_MAX_CHARS",
    "control_keywords",
    "github_api",
    "mirror_body",
    "relay_body",
]


def github_api(cli_config: Optional[Mapping]) -> GitHubApiConfig:
    """Where the daemon's GitHub token is — `integrations.github.api` (issue-442)."""
    return GitHubApiConfig.from_cli_config(dict(cli_config or {}))


class GitHubLedger:
    """The ledger: comments through the daemon's GitHub client (best-effort), issues too."""

    name = "github"

    def __init__(
        self,
        cli_config: Optional[Mapping[str, Any]] = None,
        *,
        post_comment: Optional[Callable] = None,
        create_issue: Optional[Callable] = None,
    ):
        self.cli_config: Dict[str, Any] = dict(cli_config or {})
        self._post_comment = post_comment
        self._create_issue = create_issue

    def subscribes(self, event_type: str) -> bool:
        return False  # the ledger is written to, not subscribed

    def may_publish(self, event_type: str) -> bool:
        return False  # its ingress publishes comment.*; a grant is a channel's

    def post(self, event: Event) -> PostResult:
        return self.record(event)

    # -- recording -----------------------------------------------------------

    def record(self, event: Event) -> PostResult:
        if event.event_type == "work-item.create":
            return self._create(event)
        try:
            item = WorkItemRef.parse(event.work_item)
        except ValueError as exc:
            return PostResult(channel=self.name, ok=False, error=str(exc))
        if item.provider != "github":
            return PostResult(
                channel=self.name,
                ok=False,
                error=f"{item.ref} is not a GitHub work item",
            )
        body = ledger_body(event, self.cli_config)
        post = self._post_comment
        if post is None:
            from .. import comments

            post = comments.post_issue_comment_with_url
        try:
            outcome = tuple(post(item, body, api=github_api(self.cli_config)))
        except Exception as exc:  # the writer is best-effort by contract
            outcome = (False, str(exc), "")
        # Both writer shapes are honoured: `(ok, error)` and `(ok, error, url)`.
        ok, error = bool(outcome[0]), str(outcome[1] or "") if len(outcome) > 1 else ""
        url = str(outcome[2] or "") if len(outcome) > 2 else ""
        return PostResult(
            channel=self.name, ok=bool(ok), error=error or "", url=url or ""
        )

    def _create(self, event: Event) -> PostResult:
        repo = str(event.detail.get("repo") or "")
        if not repo:
            return PostResult(
                channel=self.name, ok=False, error="kickoff-disabled: no repo"
            )
        labels = [
            lbl.strip()
            for lbl in str(event.detail.get("labels") or "").split(",")
            if lbl.strip()
        ]
        create = self._create_issue
        if create is None:
            from .. import comments

            create = comments.create_issue
        try:
            ok, error, ref, url = create(
                repo,
                issue_title(event.text),
                issue_body(event),
                labels,
                api=github_api(self.cli_config),
            )
        except Exception as exc:  # best-effort, like every ledger write
            ok, error, ref, url = False, str(exc), "", ""
        return PostResult(
            channel=self.name,
            ok=bool(ok),
            error=error or "",
            url=url or "",
            ref=ref or "",
        )
