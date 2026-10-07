"""Jira poll provider: the Jira :class:`PollProvider` (issue-475, design §C8, R5).

The poller core is provider-agnostic (issue-34); this is its second provider,
selected by a ``polling.sources`` entry ``{provider: jira, projects: [KEY, …]}``.

* **Scopes are project keys.** Each must be listed under
  ``integrations.jira.projects`` **with** a ``repository``: a mirror-only project
  is a ``jira@`` room, never a work-item source, so polling one is a config error.
* **Listing** is one JQL query per project — every arming label in its Jira-safe
  form (``jiralabels.jira_label``, issue-381: *every* label), and not Done::

      project = "PROJ" AND labels = "the-loop:auto-execute" AND statusCategory != Done ORDER BY updated DESC

  Every value goes through :func:`jql_string`; keys and labels are also checked
  at config load, so the quoting is the second line of defence (abuse case 6).
  No ticket-supplied value ever reaches JQL.
* **Comments** are listed whole every cycle, as on GitHub: the poll ledger's
  ``seenComments`` is the cursor, so a rate-limited cycle (a 429 or a 5xx is a
  degraded scope, never a lost cursor) neither drops nor repeats one (R5.6).
* **Whose comment** (:meth:`comment_origin`): the-loop's own (a self-marker, or
  the service account's), a relay (the service account's, carrying the relay
  marker), or a person's — :func:`~the_loop.authz.jira_comment_origin`.
* **Events** are the shapes the dispatcher already reads — ``issue_comment`` and
  ``issues`` — with a top-level ``x-the-loop-provider: jira``, the Jira ref as the
  work item (the router never runs GitHub's extraction on them), the comment
  author's ``accountId`` as ``comment.user.login``, and the delivery id
  ``jira-comment-<site>-<id>``: the one the webhook doorbell uses too, so a
  comment seen by both is delivered once (R6.4).
* **Closure**: status category ``done`` is a closed work item (R5.4).

Every Jira read goes through :class:`~the_loop.jiraapi.JiraClient`, which holds
the credential and scrubs every error; a client failure is a :class:`ProviderError`
here, which is what the core's per-scope isolation reads.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, TypeVar

from ..authz import ORIGIN_RELAY, jira_comment_origin
from ..jiraapi import (
    JiraApiConfig,
    JiraApiError,
    JiraClient,
    JiraComment,
    JiraIssue,
    MissingCredential,
)
from ..jiralabels import JiraLabelError, jira_label
from ..sessions import WorkItemRef
from ..sessions.refs import JIRA_KEY_PATTERN
from ..webhook.router import (
    JIRA_COMMENT_DELIVERY_PREFIX,
    POLL_CLOSURE_DELIVERY_PREFIX,
    PROVIDER_KEY,
    RELAY_KEY,
    RoutedEvent,
    normalize_labels,
)
from .base import (
    Closure,
    Comment,
    Listing,
    PollProvider,
    ProviderError,
    ScopeFailure,
    WorkItem,
    register_provider,
)

logger = logging.getLogger("the-loop.poll")

__all__ = [
    "JiraPollProvider",
    "build_jql",
    "jira_comment_delivery_id",
    "jql_string",
]

_T = TypeVar("_T")

#: How long one poll read may take (seconds), as for GitHub.
READ_TIMEOUT = 60.0

_KIND_ISSUE = "issue"
_PROJECT_KEY_RE = re.compile(rf"^{JIRA_KEY_PATTERN}$")
_ISSUE_KEY_RE = re.compile(rf"^({JIRA_KEY_PATTERN})-([1-9][0-9]{{0,9}})$")
#: The fields one listing asks for: what a work item and the arming check need.
_FIELDS = ("summary", "labels", "status")


def jql_string(value: str) -> str:
    """``value`` as one JQL string literal: wrapped in ``"``, ``\\`` and ``"`` escaped."""
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def build_jql(project: str, labels: Sequence[str]) -> str:
    """The armed tickets of ``project``: every label in ``labels``, not Done.

    ``project`` must be a project key (``ValueError`` otherwise); each label is
    quoted by :func:`jql_string`, one ``labels = …`` clause per label.
    """
    if not _PROJECT_KEY_RE.match(project or ""):
        raise ValueError(f"not a Jira project key: {project!r}")
    clauses = [f"project = {jql_string(project)}"]
    clauses += [f"labels = {jql_string(label)}" for label in labels]
    clauses.append("statusCategory != Done")
    return " AND ".join(clauses) + " ORDER BY updated DESC"


def jira_comment_delivery_id(site: str, comment_id: str) -> str:
    """``jira-comment-<site>-<id>`` — the same from the poller and the doorbell (R6.4)."""
    return f"{JIRA_COMMENT_DELIVERY_PREFIX}{site}-{comment_id}"


def _read(what: str, fn: Callable[[], _T]) -> _T:
    """One client call; its failure re-raised as the core's :class:`ProviderError`."""
    try:
        return fn()
    except JiraApiError as exc:
        raise ProviderError(f"{what}: {exc}") from None


def _origin_projects(config: Optional[Mapping[str, Any]]) -> Dict[str, str]:
    from ..channels.jira import origin_projects

    return origin_projects(config)


@register_provider
class JiraPollProvider(PollProvider):
    """Jira implementation of the poll-provider contract (issue-475)."""

    name = "jira"

    def __init__(
        self,
        projects: Sequence[str],
        labels: Sequence[str],
        site: str,
        client: JiraClient,
    ):
        self.projects = list(projects)
        #: The configured spelling — what the dispatcher's arming check reads.
        self.labels = normalize_labels(labels)
        self.site = str(site).strip().lower()
        self.client = client
        self._me: Optional[str] = None

    # -- construction -------------------------------------------------------------

    @classmethod
    def from_source(
        cls,
        source: dict,
        *,
        default_labels: Sequence[str],
        default_host: str = "",
        repositories: Sequence[str] = (),
        api: Optional[Any] = None,
        config: Optional[Mapping[str, Any]] = None,
    ) -> "JiraPollProvider":
        """A source ``{provider: jira, projects: [KEY…], labels?: […]}`` over the
        CLI ``config``'s ``integrations.jira``. Every project must be configured
        there with a ``repository``; anything else is a :class:`ProviderError`
        naming it, so a bad source stops the poller at its pre-flight."""
        source = source or {}
        jira_api = JiraApiConfig.from_cli_config(config)
        if not jira_api.configured:
            raise ProviderError(
                "a jira polling source needs integrations.jira (site, deployment, "
                "api, projects) in the CLI config"
            )
        raw = source.get("projects")
        projects = [str(p).strip() for p in raw] if isinstance(raw, list) else []
        if not projects:
            raise ProviderError(
                "a jira polling source must list its projects (`projects: [KEY]`)"
            )
        sources = _origin_projects(config)
        for project in projects:
            if not _PROJECT_KEY_RE.match(project):
                raise ProviderError(f"jira polling source: {project!r} is not a key")
            if project not in jira_api.projects:
                raise ProviderError(
                    f"jira polling source: project {project} is not configured "
                    "under integrations.jira.projects"
                )
            if project not in sources:
                raise ProviderError(
                    f"jira polling source: project {project} is mirror-only (no "
                    "repository under integrations.jira.projects), so it is not a "
                    "work-item source and cannot be polled"
                )
        labels = normalize_labels(source.get("labels")) or list(default_labels)
        try:
            for label in labels:
                jira_label(label)
        except JiraLabelError as exc:
            raise ProviderError(f"jira polling source: {exc}") from None
        return cls(
            projects=projects,
            labels=labels,
            site=jira_api.site,
            client=JiraClient.shared(jira_api, timeout=READ_TIMEOUT),
        )

    def describe(self) -> str:
        return f"jira {self.site} {', '.join(self.projects) or '(no projects)'}"

    def check_dependencies(self) -> List[str]:
        if not self.client.has_credentials():
            missing = self.client.config.missing_credentials()
            return [
                "missing Jira credential: set "
                + " and ".join(missing or ["the integrations.jira.api variables"])
                + " — a dedicated service account (read:jira-work, write:jira-work, "
                "read:jira-user on a scoped token)"
            ]
        return []

    # -- discovery ------------------------------------------------------------------

    @property
    def jira_labels(self) -> List[str]:
        return [jira_label(label) for label in self.labels]

    def list_work_items(self) -> List[WorkItem]:
        listing = self.listing()
        unlisted = listing.failures + listing.skipped
        if unlisted:
            raise ProviderError(f"{unlisted[0].scope}: {unlisted[0].error}")
        return listing.items

    def listing(self) -> Listing:
        """One JQL query per project; a project that fails fails alone."""
        if not self.projects:
            raise ProviderError("this jira polling source lists no projects")
        if not self.labels:
            raise ProviderError(
                "no arming labels: a jira source lists nothing without "
                "routing.autoExecuteLabels (or the source's own labels)"
            )
        wanted = self.jira_labels
        out = Listing()
        for project in self.projects:
            jql = build_jql(project, wanted)
            try:
                issues = list(self.client.search(jql, fields=_FIELDS))
            except MissingCredential as exc:
                raise ProviderError(str(exc)) from None
            except JiraApiError as exc:
                out.failures.append(ScopeFailure(project, str(exc)))
                continue
            out.polled.append(project)
            out.items.extend(
                self._work_item(issue)
                for issue in issues
                if self._armed(issue, wanted) and issue.status_category != "done"
            )
        return out

    @staticmethod
    def _armed(issue: JiraIssue, wanted: Sequence[str]) -> bool:
        """Every arming label on the ticket — the provider's own decision, taken on
        what the listing returned rather than on the query's semantics."""
        return bool(wanted) and set(wanted) <= set(issue.labels)

    def scope_of(self, ref: WorkItemRef) -> str:
        if ref.provider != self.name or ref.host != self.site:
            return ""
        return ref.owner

    def list_comments(self, item: WorkItem) -> List[Comment]:
        key = self._key(item)
        found = _read(f"comments of {item.ref}", lambda: self.client.comments(key))
        me = self._service_account()
        return [self._comment(c, me) for c in found]

    def _service_account(self) -> str:
        """The service account's id (``myself``), cached; ``""`` when unreadable —
        then nothing is a relay, and the marker is the only self test."""
        if self._me is None:
            try:
                self._me = self.client.myself()
            except JiraApiError as exc:
                logger.debug("could not read the Jira service account's id: %s", exc)
                return ""
        return self._me

    @staticmethod
    def _comment(comment: JiraComment, me: str) -> Comment:
        return Comment(
            id=comment.id,
            body=comment.body_md,
            author=comment.author_id,
            created_at=comment.created,
            url=comment.url,
            raw={"origin": jira_comment_origin(comment.body_md, comment.author_id, me)},
        )

    def comment_origin(self, comment: Comment) -> str:
        origin = (comment.raw or {}).get("origin")
        if origin:
            return str(origin)
        return super().comment_origin(comment)

    # -- events ---------------------------------------------------------------------

    def refs(self, item: WorkItem) -> List[WorkItemRef]:
        return [WorkItemRef.parse(item.ref)]

    def presence_event(self, item: WorkItem, refs: List[WorkItemRef]) -> RoutedEvent:
        payload = self._item_payload(item)
        return RoutedEvent(
            event="issues",
            action="labeled",
            delivery_id=f"jira-presence-{item.ref}-{uuid.uuid4()}",
            work_items=list(refs),
            payload=payload,
            labeled=set(self.jira_labels) <= set(item.labels),
        )

    def comment_event(
        self, item: WorkItem, comment: Comment, refs: List[WorkItemRef]
    ) -> RoutedEvent:
        """The ``issue_comment`` event for a Jira comment, as the doorbell builds it."""
        payload = self._item_payload(item)
        payload["action"] = "created"
        payload["comment"] = {
            "id": comment.id,
            "body": comment.body,
            "html_url": comment.url,
            "created_at": comment.created_at,
            "user": {"login": comment.author},
        }
        if self.comment_origin(comment) == ORIGIN_RELAY:
            payload[RELAY_KEY] = True
        return RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id=jira_comment_delivery_id(self.site, comment.id),
            work_items=list(refs),
            payload=payload,
            labeled=False,
        )

    # -- closure (R5.4) -------------------------------------------------------------

    def owns(self, ref: WorkItemRef) -> bool:
        return (
            ref.provider == self.name
            and ref.host == self.site
            and ref.owner in self.projects
        )

    def closure(self, ref: WorkItemRef) -> Optional[Closure]:
        key = f"{ref.owner}-{ref.number}"
        issue = _read(f"state of {ref.ref}", lambda: self.client.get_issue(key))
        if issue.status_category != "done":
            return None
        return Closure(
            state="closed",
            kind=_KIND_ISSUE,
            title=issue.summary,
            url=issue.url or ref.url,
            reason="completed",
        )

    def closure_event(self, ref: WorkItemRef, closure: Closure) -> RoutedEvent:
        return jira_closure_event(ref, closure, POLL_CLOSURE_DELIVERY_PREFIX)

    # -- mapping --------------------------------------------------------------------

    def work_item(self, issue: JiraIssue) -> WorkItem:
        """``issue`` as the core's neutral work item (public for the doorbell)."""
        return self._work_item(issue)

    def _work_item(self, issue: JiraIssue) -> WorkItem:
        match = _ISSUE_KEY_RE.match(issue.key)
        if not match:  # the client validated it; never reached on a real answer
            raise ProviderError(f"Jira answered an unusable key {issue.key!r}")
        return WorkItem(
            provider=self.name,
            owner=match.group(1),
            repo="",
            number=int(match.group(2)),
            kind=_KIND_ISSUE,
            title=issue.summary,
            url=f"https://{self.site}/browse/{issue.key}",
            author="",  # a listing carries no reporter: the start command arms it
            labels=list(issue.labels),
            raw={"key": issue.key, "statusCategory": issue.status_category},
        )

    @staticmethod
    def _key(item: WorkItem) -> str:
        return f"{item.owner}-{item.number}"

    def _item_payload(self, item: WorkItem) -> dict:
        """An ``issues``-shaped payload. Its labels carry both spellings: Jira's,
        and the configured one for each arming label the ticket carries, which
        is what the dispatcher's arming check compares against (issue-381)."""
        names = list(item.labels)
        for label in self.labels:
            if jira_label(label) in item.labels and label not in names:
                names.append(label)
        return {
            PROVIDER_KEY: "jira",
            "action": "labeled",
            "issue": {
                "number": item.number,
                "key": self._key(item),
                "title": item.title,
                "html_url": item.url,
                "labels": [{"name": name} for name in names],
            },
        }


def jira_closure_event(ref: WorkItemRef, closure: Closure, prefix: str) -> RoutedEvent:
    """The ``issues``/``closed`` event for a Jira work item — no ``sender``: Jira's
    close names nobody the-loop authorizes on, so cleanup defers to a named
    authorized ``the-loop cleanup`` (issue-329's rule)."""
    return RoutedEvent(
        event="issues",
        action="closed",
        delivery_id=f"{prefix}{ref.ref}-{closure.state}",
        work_items=[ref],
        payload={
            PROVIDER_KEY: "jira",
            "action": "closed",
            "issue": {
                "number": ref.number,
                "key": f"{ref.owner}-{ref.number}",
                "title": closure.title,
                "html_url": closure.url,
                "labels": [],
                "state_reason": closure.reason or "completed",
            },
        },
        labeled=False,
    )
