"""The Jira webhook doorbell (issue-475, design §C8, R6).

A Jira Cloud webhook is registered by a Jira admin against ``/jira-webhook`` with
a secret; the receiver serves that route only when
``integrations.jira.webhook.secretEnv`` names a variable that is set
(:func:`jira_webhook_secret`), and verifies each delivery's ``X-Hub-Signature``
before parsing it (``server.py``). What reaches this module is a **doorbell**:

* only ``webhookEvent``, ``issue.key`` and ``comment.id`` are read from the body
  (:func:`read_doorbell`); every other field — the comment's text, its author,
  the issue's labels — is ignored and **re-fetched** through the daemon's own
  :class:`~the_loop.jiraapi.JiraClient`, so a forged-but-signed body can inject
  neither content nor identity (trust boundary 1);
* the events it emits are the poller's own (:class:`~the_loop.poller.jira.
  JiraPollProvider` builds them), so a comment seen by the webhook and by the
  poll carries one delivery id, ``jira-comment-<site>-<id>``, and is delivered
  once (R6.4).

==========================  ============================================================
``webhookEvent``            what the doorbell does
==========================  ============================================================
``comment_created``         fetch the issue and the comment; an armed ticket's comment
                            goes through the router (self, allow-list) to the dispatcher
``jira:issue_updated``      fetch the issue: status category ``done`` → the close event;
                            armed and started by an authorized ``the-loop start`` →
                            presence; anything else is ignored
anything else               ignored (202), logged at debug
==========================  ============================================================

A ticket outside the polled-or-sourced projects, or a key that is not a key, is
ignored before anything is fetched.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, Mapping, Optional

from .. import eventlog
from ..authz import ORIGIN_SELF
from ..jiraapi import JiraApiError, is_issue_key
from ..sessions import WorkItemRef
from .router import RoutedEvent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..poller.jira import JiraPollProvider

logger = logging.getLogger("the-loop.gh-webhook")

__all__ = [
    "COMMENT_CREATED",
    "ISSUE_UPDATED",
    "JIRA_CLOSURE_DELIVERY_PREFIX",
    "Doorbell",
    "JiraDoorbell",
    "jira_webhook_secret",
    "read_doorbell",
]

COMMENT_CREATED = "comment_created"
ISSUE_UPDATED = "jira:issue_updated"
#: A webhook-seen closure's delivery-id prefix — not the poller's, so the
#: dispatcher's closure stamp says ``source: webhook``.
JIRA_CLOSURE_DELIVERY_PREFIX = "jira-close-"


@dataclass(frozen=True)
class Doorbell:
    """The three fields a verified Jira delivery is read for — and nothing else."""

    event: str = ""
    issue_key: str = ""
    comment_id: str = ""

    def as_dict(self) -> Dict[str, str]:
        return {
            "webhookEvent": self.event,
            "issueKey": self.issue_key,
            "commentId": self.comment_id,
        }


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else str(value or "").strip()


def read_doorbell(doc: Mapping[str, Any]) -> Doorbell:
    """``webhookEvent``, ``issue.key`` and ``comment.id`` of a delivery body."""
    issue = doc.get("issue") if isinstance(doc.get("issue"), Mapping) else {}
    comment = doc.get("comment") if isinstance(doc.get("comment"), Mapping) else {}
    raw_id = comment.get("id") if isinstance(comment, Mapping) else None
    return Doorbell(
        event=_text(doc.get("webhookEvent"))[:64],
        issue_key=_text(issue.get("key") if isinstance(issue, Mapping) else "")[:32],
        comment_id=_text(raw_id)[:32] if isinstance(raw_id, (str, int)) else "",
    )


def jira_webhook_secret(
    config: Optional[Mapping[str, Any]], env: Optional[Mapping[str, str]] = None
) -> str:
    """The Jira webhook secret: the value of ``integrations.jira.webhook.secretEnv``.

    ``""`` when Jira is not configured, no variable is named, or the named one is
    unset or empty — and then the route is not served at all (abuse case 2).
    """
    from ..sessions.refs import jira_section

    webhook = jira_section(config).get("webhook")
    name = _text(webhook.get("secretEnv")) if isinstance(webhook, Mapping) else ""
    if not name:
        return ""
    environ: Mapping[str, str] = os.environ if env is None else env
    return str(environ.get(name) or "").strip()


class JiraDoorbell:
    """Turns a verified doorbell into the poller's events, through one provider.

    ``route`` is the router's judgement (self-marker, allow-list) for a comment;
    ``dispatch`` hands an event to the dispatcher; ``start_requested`` answers
    whether an authorized user started a work item — the only thing that lets a
    label change become a presence event, since Jira names no actor for it.
    """

    def __init__(
        self,
        provider: "JiraPollProvider",
        *,
        route: Callable[[RoutedEvent], Optional[RoutedEvent]],
        dispatch: Callable[[RoutedEvent], None],
        start_requested: Callable[[str], bool],
    ):
        self.provider = provider
        self.route = route
        self.dispatch = dispatch
        self.start_requested = start_requested

    @classmethod
    def from_config(
        cls,
        cli_config: Mapping[str, Any],
        labels: Any,
        *,
        route: Callable[[RoutedEvent], Optional[RoutedEvent]],
        dispatch: Callable[[RoutedEvent], None],
        start_requested: Callable[[str], bool],
    ) -> "JiraDoorbell":
        """Over every project with a ``repository`` — the work-item sources."""
        from ..channels.jira import origin_projects
        from ..jiraapi import JiraApiConfig, JiraClient
        from ..poller.jira import READ_TIMEOUT, JiraPollProvider

        api = JiraApiConfig.from_cli_config(cli_config)
        provider = JiraPollProvider(
            projects=sorted(origin_projects(cli_config)),
            labels=list(labels or []),
            site=api.site,
            client=JiraClient.shared(api, timeout=READ_TIMEOUT),
        )
        return cls(
            provider, route=route, dispatch=dispatch, start_requested=start_requested
        )

    # -- the one entry point -------------------------------------------------------------

    def ring(self, bell: Doorbell) -> str:
        """Act on ``bell``; the outcome, for the log. Never raises."""
        if bell.event not in (COMMENT_CREATED, ISSUE_UPDATED):
            logger.debug("ignoring Jira %r: not an event the-loop acts on", bell.event)
            return "ignored:event"
        key = bell.issue_key
        project = key.rpartition("-")[0]
        if not is_issue_key(key) or project not in self.provider.projects:
            logger.warning(
                "ignoring Jira %s for %r: not a ticket in a configured source project",
                bell.event,
                key,
            )
            eventlog.emit(
                "routing.dropped",
                level="warning",
                reason="unknown-jira-project",
                gh_event=bell.event,
                provider="jira",
            )
            return "ignored:project"
        try:
            if bell.event == COMMENT_CREATED:
                return self._comment(key, bell.comment_id)
            return self._issue_updated(key)
        except JiraApiError as exc:
            logger.warning("Jira doorbell for %s could not read Jira: %s", key, exc)
            return "error"
        except Exception as exc:  # noqa: BLE001 — a ProviderError, or worse
            logger.warning("Jira doorbell for %s failed: %s", key, exc)
            return "error"

    # -- the two events --------------------------------------------------------------------

    def _armed_item(self, key: str):
        issue = self.provider.client.get_issue(key)
        item = self.provider.work_item(issue)
        armed = self.provider._armed(issue, self.provider.jira_labels)
        return issue, item, armed

    def _comment(self, key: str, comment_id: str) -> str:
        if not comment_id:
            return "ignored:no-such-comment"
        issue, item, armed = self._armed_item(key)
        if not armed or issue.status_category == "done":
            logger.debug("ignoring a comment on %s: the ticket is not armed", key)
            return "ignored:unarmed"
        comment = next(
            (c for c in self.provider.list_comments(item) if c.id == comment_id), None
        )
        if comment is None:
            return "ignored:no-such-comment"
        if self.provider.comment_origin(comment) == ORIGIN_SELF:
            logger.debug("ignoring the-loop's own comment %s on %s", comment_id, key)
            return "ignored:self"
        refs = self.provider.refs(item)
        event = self.provider.comment_event(item, comment, refs)
        routed = self.route(event)
        if routed is None:
            return "dropped"
        self.dispatch(routed)
        return "routed"

    def _issue_updated(self, key: str) -> str:
        issue, item, armed = self._armed_item(key)
        ref = WorkItemRef.parse(item.ref)
        if issue.status_category == "done":
            from ..poller.base import Closure
            from ..poller.jira import jira_closure_event

            closure = Closure(
                state="closed",
                kind="issue",
                title=issue.summary,
                url=item.url,
                reason="completed",
            )
            self.dispatch(
                jira_closure_event(ref, closure, JIRA_CLOSURE_DELIVERY_PREFIX)
            )
            return "closed"
        if not armed:
            return "ignored:unarmed"
        if not self.start_requested(ref.ref):
            # Arming is a label; starting is a person (abuse case 5). Jira names
            # nobody for a label change, so only a recorded authorized start —
            # written by the dispatcher for a named, listed actor — spawns.
            logger.debug("%s is armed but not started; no presence", ref.ref)
            return "ignored:not-started"
        self.dispatch(self.provider.presence_event(item, [ref]))
        return "presence"
