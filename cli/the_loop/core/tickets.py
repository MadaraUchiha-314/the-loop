"""The ticket verbs, dispatched by tracker (issue-475, design §C9, R8.2).

``the-loop ticket show|create|close``, ``comment`` and ``pr create`` act on a work
item's **own** tracker. :func:`tracker_for` reads the ref's provider and returns
the implementation:

* :class:`GitHubTickets` — :mod:`the_loop.core.github_ops`' functions, unchanged.
  A GitHub ref takes exactly the path it took before this module existed.
* :class:`JiraTickets` — the same verbs on a Jira ticket, through the one
  :class:`~the_loop.jiraapi.JiraClient`, with the same result shapes.

Every caller — the CLI, the control-plane routes and the MCP tools, through the
facade — calls the module-level functions here, so a Jira ref works on every
surface with no route of its own.

:func:`post_on_ticket` is the plain "write this on the work item's ticket" the
announcements use (a control command, a channel declaration, a refusal): GitHub
through :func:`~the_loop.comments.post_issue_comment_with_url`, Jira through the
client with the Jira marker.

Properties kept from :mod:`~the_loop.core.github_ops`: data out (``exitCode`` and
``messages`` beside the fields), a caller mistake is a :class:`ValueError` raised
before any request, the tracker's refusal is a result with ``exitCode: 1``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union

from .. import eventlog
from ..authz import (
    is_self_authored,
    mark_relayed_on_jira,
    mark_self_authored_on_jira,
)
from ..jiraapi import JiraApiConfig, JiraApiError, JiraClient, issue_key_for
from ..workitem import WorkItemRef
from . import github_ops
from . import sessions as core_sessions

logger = logging.getLogger("the-loop.tickets")

__all__ = [
    "GitHubTickets",
    "JiraTickets",
    "close_ticket",
    "comment",
    "create_pull_request",
    "create_ticket",
    "post_on_ticket",
    "show_ticket",
    "tracker_for",
]

Tracker = Union["GitHubTickets", "JiraTickets"]


def tracker_for(
    ref: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    jira_client: Optional[JiraClient] = None,
) -> Tracker:
    """The ticket implementation for ``ref``'s provider; :class:`ValueError` for a
    malformed ref or a provider with none."""
    item = WorkItemRef.parse(ref)  # ValueError on a malformed ref
    if item.provider == "jira":
        return JiraTickets(config, client=jira_client)
    if item.provider == "github":
        return GitHubTickets(config)
    raise ValueError(f"{item.ref}: no ticket verbs for provider {item.provider!r}")


# ------------------------------------------------------------------ GitHub


class GitHubTickets:
    """GitHub's ticket verbs: :mod:`~the_loop.core.github_ops`, unchanged."""

    name = "github"

    def __init__(self, config: Optional[Mapping[str, Any]] = None):
        self.config = dict(config or {})

    def show(self, ref: str) -> Dict[str, Any]:
        return github_ops.show_ticket(ref, self.config)

    def comment(self, ref: str, body: str) -> Dict[str, Any]:
        return github_ops.comment(ref, body, self.config)

    def close(
        self, ref: str, reason: str, work_item: str, registry_dir: str = ""
    ) -> Dict[str, Any]:
        return github_ops.close_ticket(
            ref, reason, work_item, self.config, registry_dir=registry_dir
        )


# ------------------------------------------------------------------ Jira


def _jira_api(config: Optional[Mapping[str, Any]]) -> JiraApiConfig:
    return JiraApiConfig.from_cli_config(dict(config or {}))


def _jira_client(
    config: Optional[Mapping[str, Any]], client: Optional[JiraClient]
) -> JiraClient:
    return client if client is not None else JiraClient.shared(_jira_api(config))


def _jira_ref(ref: str, api: JiraApiConfig) -> Tuple[WorkItemRef, str]:
    """``(ref, KEY-n)`` for a Jira ref this deployment can place; else a
    :class:`ValueError` before anything is sent (abuse case 8)."""
    item = WorkItemRef.parse(ref)
    if not api.configured:
        raise ValueError(
            f"{item.ref} is a Jira work item, and integrations.jira is not "
            "configured on this instance"
        )
    try:
        return item, issue_key_for(item.ref, api)
    except JiraApiError as exc:
        raise ValueError(str(exc)) from None


class JiraTickets:
    """The ticket verbs on a Jira ticket (issue-475, design §C9)."""

    name = "jira"

    def __init__(
        self,
        config: Optional[Mapping[str, Any]] = None,
        *,
        client: Optional[JiraClient] = None,
    ):
        self.config = dict(config or {})
        self.api = client.config if client is not None else _jira_api(self.config)
        self._client = client

    @property
    def client(self) -> JiraClient:
        return _jira_client(self.config, self._client)

    # -- show ------------------------------------------------------------------

    def show(self, ref: str) -> Dict[str, Any]:
        """The ticket in ``ticket show``'s GitHub shape: fields, then comments as
        Markdown (converted from ADF / wiki markup by the client)."""
        item, key = _jira_ref(ref, self.api)
        data: Dict[str, Any] = {"ref": item.ref}
        try:
            issue = self.client.get_issue(key)
            if issue.moved_to:
                return github_ops._failed(
                    data,
                    f"{key} has moved to {issue.moved_to}; register the work item "
                    "under its new key",
                )
            comments = self.client.comments(key)
        except JiraApiError as exc:
            return github_ops._failed(data, f"could not read {item.ref}: {exc}")
        data.update(
            number=item.number,
            title=issue.summary,
            body=issue.description_md,
            state="closed" if issue.status_category == "done" else "open",
            isPullRequest=False,
            labels=list(issue.labels),
            author="",
            url=issue.url or item.url,
            comments=[
                {
                    "id": c.id,
                    "kind": "comment",
                    "author": c.author_id,
                    "body": c.body_md,
                    "createdAt": c.created,
                    "url": c.url,
                }
                for c in comments
            ],
            attachments=[],
        )
        return github_ops._done(data)

    # -- create ----------------------------------------------------------------

    def create(
        self, project: str, title: str, body: str, labels: Sequence[str] = ()
    ) -> Dict[str, Any]:
        """Open an issue in ``project`` — one listed under
        ``integrations.jira.projects``. Labels are written in their Jira-safe form."""
        from ..jiralabels import JiraLabelError, jira_label

        title = github_ops._text(title, "title")
        project = str(project or "").strip()
        if not self.api.configured:
            raise ValueError(
                "--project opens a Jira ticket, and integrations.jira is not "
                "configured on this instance"
            )
        if project not in self.api.projects:
            raise ValueError(
                f"Jira project {project!r} is not configured under "
                "integrations.jira.projects"
            )
        try:
            safe = [jira_label(str(label)) for label in labels]
        except JiraLabelError as exc:
            raise ValueError(str(exc)) from None
        data: Dict[str, Any] = {"ref": "", "url": ""}
        try:
            issue = self.client.create_issue(project, title, str(body or ""), safe)
        except JiraApiError as exc:
            return github_ops._failed(data, f"could not open the ticket: {exc}")
        ref = f"jira:{self.api.site}/{issue.key}" if issue.key else ""
        data.update(ref=ref, url=issue.url)
        return github_ops._done(
            data, f"opened {ref}" + (f" — {issue.url}" if issue.url else "")
        )

    # -- close -----------------------------------------------------------------

    def close(
        self, ref: str, reason: str, work_item: str, registry_dir: str = ""
    ) -> Dict[str, Any]:
        """Transition the ticket into *Done* (R3.7) — for a registered work item
        only, like every lifecycle act. Zero or several candidate transitions is
        a failure listing what is available, and nothing is transitioned."""
        from ..ghapi import CLOSE_REASONS
        from ..graph.integrations.base import IntegrationError
        from ..graph.integrations.jira import JiraProvider

        target, key = _jira_ref(ref, self.api)
        if reason not in CLOSE_REASONS:
            raise ValueError(
                f"unknown close reason {reason!r}; expected one of "
                + ", ".join(CLOSE_REASONS)
            )
        data: Dict[str, Any] = {"ref": target.ref, "closed": False}
        refusal = github_ops._authority(target, work_item, self.config, registry_dir)
        if refusal:
            return github_ops._failed(data, f"not closing: {refusal}")
        provider = JiraProvider(config=self.api, client=self.client)
        try:
            moved = provider._transition(key, "done")
        except IntegrationError as exc:
            return github_ops._failed(data, str(exc))
        data.update(closed=True, transition=moved.get("transition", ""))
        eventlog.emit("work_item.ticket_closed", work_item=target.ref, reason=reason)
        lines = [f"closed {target.ref} ({moved.get('transition') or 'done'})"]
        cancelled, note = github_ops._cancel_pending_start(
            target, self.config, registry_dir
        )
        data["startCancelled"] = cancelled
        if cancelled:
            lines.append(f"cancelled the pending start for {target.ref}")
        result = github_ops._done(data, *lines)
        if note:
            result["messages"].append({"stream": "err", "text": note})
        return result

    # -- comment ---------------------------------------------------------------

    def comment(self, ref: str, body: str) -> Dict[str, Any]:
        """The agent's comment on the Jira ticket, through the bus: the Jira
        ledger records it (the visible self-marker stamped centrally), then
        every subscribed channel gets it — as on GitHub."""
        from ..channels.base import Event
        from ..channels.bus import publish as bus_publish
        from ..channels.jira import JiraLedger

        item, key = _jira_ref(ref, self.api)
        text = github_ops._text(body, "comment")
        ledger = JiraLedger(self.config, client=self.client)
        ok, error, url, channels_posted = False, "", "", 0
        try:
            published = bus_publish(
                Event(
                    event_type="comment.agent",
                    work_item=item.ref,
                    text=text,
                    detail={"actor": core_sessions._local_actor()},
                    source="cli",
                ),
                self.config,
                ledger=ledger,
                record=True,
            )
            record = published.record
            ok = bool(record and record.ok)
            error = (record.error if record else "") or ""
            url = (record.url if record else "") or ""
            channels_posted = sum(1 for posted in published.posts if posted.ok)
        except Exception as exc:  # noqa: BLE001 — a channel bug never loses it
            logger.warning("channel broadcast failed: %s", exc)
            try:
                url = self.client.add_comment(key, mark_self_authored_on_jira(text)).url
                ok = True
            except JiraApiError as api_exc:
                ok, error = False, str(api_exc)
        eventlog.emit(
            "work_item.commented",
            level="info" if ok else "warning",
            work_item=item.ref,
            comment_url=url or None,
            comment_posted=ok,
            channels_posted=channels_posted,
        )
        data: Dict[str, Any] = {
            "workItem": item.ref,
            "url": url,
            "posted": ok,
            "channelsPosted": channels_posted,
        }
        if not ok:
            return github_ops._failed(data, f"could not comment on {item.ref}: {error}")
        return github_ops._done(
            data, f"commented on {item.ref}" + (f" — {url}" if url else "")
        )


# ------------------------------------------------------------------ the verbs


def show_ticket(
    ref: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    jira_client: Optional[JiraClient] = None,
) -> Dict[str, Any]:
    """``ticket show`` on either tracker."""
    return tracker_for(ref, config, jira_client=jira_client).show(ref)


def comment(
    ref: str,
    body: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    jira_client: Optional[JiraClient] = None,
) -> Dict[str, Any]:
    """``comment --work-item`` on either tracker."""
    return tracker_for(ref, config, jira_client=jira_client).comment(ref, body)


def close_ticket(
    ref: str,
    reason: str = "completed",
    work_item: str = "",
    config: Optional[Mapping[str, Any]] = None,
    *,
    registry_dir: str = "",
    jira_client: Optional[JiraClient] = None,
) -> Dict[str, Any]:
    """``ticket close``: GitHub closes the issue, Jira transitions into Done."""
    return tracker_for(ref, config, jira_client=jira_client).close(
        ref, reason, work_item, registry_dir
    )


def create_ticket(
    repository: str,
    title: str,
    body: str,
    labels: Sequence[str] = (),
    config: Optional[Mapping[str, Any]] = None,
    *,
    project: str = "",
    jira_client: Optional[JiraClient] = None,
) -> Dict[str, Any]:
    """``ticket create``: ``repository`` opens a GitHub issue, ``project`` a Jira
    ticket. Exactly one of the two (R8.2)."""
    if bool(str(repository or "").strip()) == bool(str(project or "").strip()):
        raise ValueError(
            "name exactly one of --repository (a GitHub issue) and --project "
            "(a Jira ticket)"
        )
    if project:
        return JiraTickets(config, client=jira_client).create(
            project, title, body, labels
        )
    return github_ops.create_ticket(repository, title, body, labels, config)


def create_pull_request(
    ref: str,
    title: str,
    body: str,
    head: str,
    base: str = "",
    repository: str = "",
    draft: bool = False,
    config: Optional[Mapping[str, Any]] = None,
    *,
    registry_dir: str = "",
    client: Any = None,
) -> Dict[str, Any]:
    """``pr create`` on either tracker. A pull request is always a GitHub one; a
    Jira work item's is opened in its origin repository and recorded against the
    Jira work item (:func:`~the_loop.core.github_ops.create_pull_request`)."""
    return github_ops.create_pull_request(
        ref,
        title,
        body,
        head,
        base=base,
        repository=repository,
        draft=draft,
        config=config,
        registry_dir=registry_dir,
        client=client,
    )


def post_on_ticket(
    item: WorkItemRef,
    body: str,
    config: Optional[Mapping[str, Any]] = None,
    *,
    relay: bool = False,
    github_api: Any = None,
    jira_client: Optional[JiraClient] = None,
) -> Tuple[bool, str, str]:
    """Write ``body`` on ``item``'s own ticket: ``(ok, error, url)``; never raises.

    GitHub: posted as given (:func:`~the_loop.comments.post_issue_comment_with_url`).
    Jira: with the visible Jira self-marker — or, for ``relay``, the relay marker,
    which the Jira ingress reads as the operator's words, as GitHub's ingress
    reads an unmarked comment under the operator's credentials.
    """
    if item.provider != "jira":
        from ..comments import post_issue_comment_with_url

        return post_issue_comment_with_url(item, body, api=github_api)
    try:
        api = jira_client.config if jira_client is not None else _jira_api(config)
        _, key = _jira_ref(item.ref, api)
        text = (
            mark_relayed_on_jira(body)
            if relay and not is_self_authored(body, "jira")
            else mark_self_authored_on_jira(body)
        )
        made = _jira_client(config, jira_client).add_comment(key, text)
        return True, "", made.url
    except (ValueError, JiraApiError) as exc:
        return False, str(exc), ""
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.debug("could not post on %s: %s", item.ref, exc)
        return False, str(exc), ""
