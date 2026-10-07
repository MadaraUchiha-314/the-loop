"""The Jira provider — the process graph's hooks over the daemon's Jira client (issue-475).

It implements the :class:`~the_loop.graph.integrations.base.Integration`
contract over :class:`~the_loop.jiraapi.JiraClient` (decision-142), answering
every operation the GitHub provider answers with the same result shapes, plus
``transition``. Every failure is an :class:`IntegrationError`.

A ref is placed before anything is sent: it must be a ``jira:`` ref on the one
configured site, for a project listed under ``integrations.jira.projects``.
Anything else is refused with the client untouched, so a ref naming another
site never carries this deployment's credential there (abuse case 8).

Every comment it writes carries the visible Jira self-marker
(:func:`~the_loop.authz.mark_self_authored_on_jira`), and a comment the
service account wrote reads back marked even if its text lost the marker.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, FrozenSet, List, Optional, TypeVar

from ...authz import is_self_authored, mark_self_authored_on_jira
from ...jiraapi import (
    JiraApiConfig,
    JiraApiError,
    JiraClient,
    JiraComment,
    JiraTransition,
)
from ...jiralabels import JiraLabelError, jira_label
from ...sessions import WorkItemRef
from .base import IntegrationError, OperationUnsupported
from .github import OPERATIONS as GITHUB_OPERATIONS

logger = logging.getLogger("the-loop.graph.integrations")

__all__ = ["JiraProvider", "OPERATIONS"]

#: GitHub's operations (R3.1) plus `transition`, which closes a ticket (R3.7).
OPERATIONS: FrozenSet[str] = GITHUB_OPERATIONS | frozenset({"transition"})

#: The status category a closing transition lands in.
_DONE = "done"

_T = TypeVar("_T")


class JiraProvider:
    """The one Jira provider: the pycontribs SDK through :class:`JiraClient`."""

    name = "jira"
    transport = "api"
    operations = OPERATIONS

    def __init__(
        self,
        config: Optional[JiraApiConfig] = None,
        client: Optional[JiraClient] = None,
    ):
        if client is None:
            self.config = config or JiraApiConfig()
            self.client = JiraClient.shared(self.config)
        else:
            self.config = config or client.config
            self.client = client

    def _run(self, fn: Callable[[], _T]) -> _T:
        try:
            return fn()
        except JiraApiError as exc:
            raise IntegrationError(f"jira: {exc}") from None

    def _key(self, ref: str) -> str:
        """``jira:<site>/<KEY>-<n>`` → ``KEY-n``, or refuse before any request."""
        try:
            parsed = WorkItemRef.parse(str(ref))
        except ValueError as exc:
            raise IntegrationError(f"jira: malformed work item ref {ref!r}: {exc}")
        if parsed.provider != "jira":
            raise IntegrationError(
                f"jira: {ref!r} is not a Jira ref — expected 'jira:<site>/<KEY>-<n>'"
            )
        site = self.config.site
        if not site or parsed.host.lower() != site:
            raise IntegrationError(
                f"jira: {parsed.ref} is on {parsed.host}, not the configured Jira "
                f"site ({site or 'none'}); nothing was sent"
            )
        if parsed.owner not in self.config.projects:
            raise IntegrationError(
                f"jira: project {parsed.owner} is not configured under "
                "integrations.jira.projects; nothing was sent"
            )
        return f"{parsed.owner}-{parsed.number}"

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"jira does not implement {op!r}")
        if op == "create-label":
            # R3.1: Jira creates a label the first time an issue carries it.
            return {"result": "exists", "note": "jira creates labels on use"}
        key = self._key(str(params.get("ref", "")))
        jira = self.client
        if op == "add-comment":
            # R4.6: the visible Jira self-marker replaces GitHub's hidden one.
            body = mark_self_authored_on_jira(str(params["body"]))
            comment = self._run(lambda: jira.add_comment(key, body))
            return {"result": {"html_url": comment.url}}
        if op == "set-labels":
            # Adds, leaving every other label in place — GitHub's semantics —
            # in the Jira-safe form (design §C5).
            labels = [_label(str(label)) for label in params["labels"]]
            self._run(lambda: jira.add_labels(key, labels))
            return {"result": "ok"}
        if op == "remove-label":
            label = _label(str(params["label"]))
            removed = self._run(lambda: jira.remove_label(key, label))
            return {"result": "ok" if removed else "absent"}
        if op == "get-labels":
            return {"labels": self._run(lambda: jira.labels(key))}
        if op == "get-thread":
            return {"kind": "issue"}
        if op == "transition":
            return self._transition(key, str(params.get("to", "")))
        comments = self._run(lambda: jira.comments(key))
        return {
            "comments": [
                {
                    "id": c.id,
                    "body": _as_read(c),
                    "author": {"login": c.author_id},
                    "user": {"login": c.author_id},
                    "created_at": c.created,
                    "createdAt": c.created,
                    "html_url": c.url,
                    "url": c.url,
                }
                for c in comments
            ]
        }

    def _transition(self, key: str, to: str) -> Dict[str, Any]:
        """Close ``key``: the configured transition, else the one into *Done*.

        Zero or several candidates is an error listing what is available, and no
        transition is made (R3.7) — a guess here closes a ticket the wrong way.
        """
        if to != _DONE:
            raise IntegrationError(
                f"jira: transition supports to={_DONE!r} only, got {to!r}"
            )
        available = self._run(lambda: self.client.transitions(key))
        wanted = self.config.close_transition
        if wanted:
            candidates = [t for t in available if t.name.lower() == wanted.lower()]
            why = f"the configured closeTransition {wanted!r} is not available"
        else:
            candidates = [t for t in available if t.to_category == _DONE]
            why = (
                "no transition into the Done status category is available"
                if not candidates
                else "several transitions lead into the Done status category"
            )
        if len(candidates) != 1:
            raise IntegrationError(
                f"jira: cannot close {key}: {why}; available: {_listing(available)}. "
                "Set integrations.jira.closeTransition to choose one."
            )
        [chosen] = candidates
        self._run(lambda: self.client.transition(key, chosen.id))
        logger.info(
            "jira transition",
            extra={"work_item": key, "provider": "jira", "transition": chosen.name},
        )
        return {"result": "ok", "transition": chosen.name}


def _label(name: str) -> str:
    try:
        return jira_label(name)
    except JiraLabelError as exc:
        raise IntegrationError(f"jira: {exc}") from None


def _as_read(comment: JiraComment) -> str:
    """A comment's body as every gate reads it.

    A comment the service account wrote is the-loop's own even when its text
    lost the marker (an edit in Jira, abuse case 4), so it is handed on carrying
    the marker: every reader that drops a self-authored comment by its body —
    the feedback gates, the goal and review hooks — then drops this one too.
    """
    if comment.is_self and not is_self_authored(comment.body_md):
        return mark_self_authored_on_jira(comment.body_md)
    return comment.body_md


def _listing(transitions: List[JiraTransition]) -> str:
    if not transitions:
        return "none"
    return ", ".join(
        f"{t.name!r} (→ {t.to_status or '?'}, {t.to_category or '?'})"
        for t in transitions
    )
