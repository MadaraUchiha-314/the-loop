"""Jira as a ledger (issue-475, design §C7, R4.1).

:class:`JiraLedger` records an event on a Jira work item's own ticket, as the
GitHub ledger records it on an issue. It writes the **same body** —
:func:`~the_loop.channels.bodies.ledger_body` picks the shape by event type for
both trackers — and then does the two things only Jira needs: the body carries
the visible Jira self-marker (:func:`~the_loop.authz.mark_self_authored_on_jira`;
the GitHub HTML marker does not survive ADF), and it is converted to ADF or wiki
markup by :class:`~the_loop.jiraapi.JiraClient` (``jiraformat``).

``work-item.create`` with ``channels.ledger: jira`` opens a ticket in the
project the event names (``detail["project"]``), which must be one with a
``repository`` — a mirror-only project is never a work-item source.

Every write goes through the one client, after :func:`~the_loop.jiraapi.
issue_key_for` has placed the ref on the configured site and a configured
project: nothing is sent for a ref that is not.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

from ..authz import mark_self_authored_on_jira
from ..jiraapi import JiraApiConfig, JiraApiError, JiraClient, issue_key_for
from ..jiralabels import JiraLabelError, jira_label
from .base import Event, PostResult
from .bodies import issue_body, issue_title, ledger_body

logger = logging.getLogger("the-loop.channels")

__all__ = ["JiraLedger", "origin_projects"]


def origin_projects(cli_config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    """``{project key: repository}`` for the projects that are work-item sources.

    A project listed under ``integrations.jira.projects`` without a
    ``repository`` is mirror-only (design §C7): a room, never a source.
    """
    integrations = dict(cli_config or {}).get("integrations") or {}
    jira = integrations.get("jira") if isinstance(integrations, Mapping) else None
    projects = jira.get("projects") if isinstance(jira, Mapping) else None
    out: Dict[str, str] = {}
    for key, entry in (projects if isinstance(projects, Mapping) else {}).items():
        repository = entry.get("repository") if isinstance(entry, Mapping) else None
        if isinstance(repository, str) and repository.strip():
            out[str(key)] = repository.strip()
    return out


class JiraLedger:
    """The ledger on Jira: comments on the work item's ticket, tickets too."""

    name = "jira"

    def __init__(
        self,
        cli_config: Optional[Mapping[str, Any]] = None,
        *,
        client: Optional[JiraClient] = None,
    ):
        self.cli_config: Dict[str, Any] = dict(cli_config or {})
        self.api = (
            client.config
            if client is not None
            else (JiraApiConfig.from_cli_config(self.cli_config))
        )
        self._client = client

    @property
    def client(self) -> JiraClient:
        return self._client or JiraClient.shared(self.api)

    def subscribes(self, event_type: str) -> bool:
        return False  # the ledger is written to, not subscribed

    def may_publish(self, event_type: str) -> bool:
        return False

    def post(self, event: Event) -> PostResult:
        return self.record(event)

    def _failed(self, error: str) -> PostResult:
        return PostResult(channel=self.name, ok=False, error=error)

    def record(self, event: Event) -> PostResult:
        if event.event_type == "work-item.create":
            return self._create(event)
        try:
            key = issue_key_for(event.work_item, self.api)
        except JiraApiError as exc:
            return self._failed(str(exc))
        body = mark_self_authored_on_jira(ledger_body(event, self.cli_config))
        try:
            comment = self.client.add_comment(key, body)
        except JiraApiError as exc:  # best-effort, like every ledger write
            return self._failed(str(exc))
        return PostResult(channel=self.name, ok=True, url=comment.url)

    def _create(self, event: Event) -> PostResult:
        project = str(event.detail.get("project") or "")
        if not project:
            return self._failed("kickoff-disabled: no Jira project")
        if project not in origin_projects(self.cli_config):
            return self._failed(
                f"Jira project {project} has no repository under "
                "integrations.jira.projects, so a ticket there cannot be a work item"
            )
        try:
            labels = [
                jira_label(label)
                for label in str(event.detail.get("labels") or "").split(",")
                if label.strip()
            ]
        except JiraLabelError as exc:
            return self._failed(str(exc))
        try:
            issue = self.client.create_issue(
                project, issue_title(event.text), issue_body(event), labels
            )
        except JiraApiError as exc:
            return self._failed(str(exc))
        return PostResult(
            channel=self.name,
            ok=True,
            url=issue.url,
            ref=f"jira:{self.api.site}/{issue.key}" if issue.key else "",
        )
