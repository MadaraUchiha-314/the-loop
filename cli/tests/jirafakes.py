"""In-memory doubles for the Jira client (issue-475), mirroring ``ghfakes.py``.

Two doubles, for two boundaries:

* :class:`FakeJiraClient` replaces :class:`the_loop.jiraapi.JiraClient` for its
  callers — the graph's :class:`~the_loop.graph.integrations.jira.JiraProvider`
  and, later, the ledger, channel and poller. Same method surface, canned
  answers, per-method failure knobs, a log of every call.
* :class:`FakeJiraSDK` replaces the pycontribs ``jira.JIRA`` object *under* the
  real client, so the client's own work — which SDK call it makes, how it reads
  the answer, how it translates and scrubs an error — is tested with no network.

Neither is a claim about what Jira's servers send; only about what the caller asked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence

from the_loop.jiraapi import (
    JiraApiConfig,
    JiraApiError,
    JiraClient,
    JiraComment,
    JiraIssue,
    JiraTransition,
)

__all__ = [
    "CLOUD",
    "DATA_CENTER",
    "FakeJiraClient",
    "FakeJiraSDK",
    "cloud_config",
    "http_error",
]

#: A Cloud deployment's ``integrations.jira`` block.
CLOUD: Dict[str, Any] = {
    "site": "acme.atlassian.net",
    "deployment": "cloud",
    "api": {"emailEnv": ["JIRA_EMAIL"], "tokenEnv": ["JIRA_API_TOKEN"]},
    "projects": {"PROJ": {"repository": "acme/web"}, "OPS": {}},
}

#: A Data Center deployment's block.
DATA_CENTER: Dict[str, Any] = {
    "site": "jira.corp.example",
    "deployment": "data-center",
    "api": {"tokenEnv": ["JIRA_PAT"]},
    "projects": {"PROJ": {"repository": "acme/web"}},
}


def cloud_config(**overrides: Any) -> Dict[str, Any]:
    """A CLI config document carrying :data:`CLOUD`, with ``overrides`` merged in."""
    return {"integrations": {"jira": {**CLOUD, **overrides}}}


def http_error(status: int, message: str = "boom") -> JiraApiError:
    return JiraApiError(message, status=status)


@dataclass
class FakeJiraClient(JiraClient):
    """Every operation of the client, answered from memory.

    ``fail`` raises from every call; ``fail_on`` from the named methods only.
    Reads answer from ``issues``/``label_table``/``comment_table``/
    ``transition_table``; writes append to ``posted``/``transitioned``/
    ``created`` and edit the tables in place.
    """

    config: JiraApiConfig = field(
        default_factory=lambda: JiraApiConfig.from_cli_config(cloud_config())
    )
    timeout: float = 30.0
    credentialed: bool = True
    fail: Optional[JiraApiError] = None
    fail_on: Dict[str, JiraApiError] = field(default_factory=dict)
    account_id: str = "5b10-the-loop-bot"
    next_comment_id: int = 10000
    next_issue_number: int = 100

    issues: Dict[str, JiraIssue] = field(default_factory=dict)
    label_table: Dict[str, List[str]] = field(default_factory=dict)
    comment_table: Dict[str, List[JiraComment]] = field(default_factory=dict)
    transition_table: Dict[str, List[JiraTransition]] = field(default_factory=dict)

    posted: List[Dict[str, Any]] = field(default_factory=list)
    transitioned: List[Dict[str, Any]] = field(default_factory=list)
    created: List[Dict[str, Any]] = field(default_factory=list)
    calls: List[Dict[str, Any]] = field(default_factory=list)

    def _enter(self, method: str, **kwargs: Any) -> None:
        self.calls.append({"method": method, **kwargs})
        if method in self.fail_on:
            raise self.fail_on[method]
        if self.fail is not None:
            raise self.fail

    def calls_to(self) -> List[str]:
        return [c["method"] for c in self.calls]

    def has_credentials(self) -> bool:
        return self.credentialed

    def sdk(self) -> Any:  # never reached: every method below is overridden
        raise AssertionError("FakeJiraClient never builds an SDK client")

    def get_issue(self, key: str) -> JiraIssue:
        self._enter("get_issue", key=key)
        issue = self.issues.get(key)
        if issue is None:
            return JiraIssue(key=key, labels=list(self.label_table.get(key, [])))
        return issue

    def labels(self, key: str) -> List[str]:
        self._enter("labels", key=key)
        return list(self.label_table.get(key, []))

    def add_labels(self, key: str, labels: Sequence[str]) -> None:
        self._enter("add_labels", key=key, labels=list(labels))
        current = self.label_table.setdefault(key, [])
        current.extend(label for label in labels if label not in current)

    def remove_label(self, key: str, label: str) -> bool:
        self._enter("remove_label", key=key, label=label)
        current = self.label_table.get(key, [])
        if label not in current:
            return False
        current.remove(label)
        return True

    def comments(self, key: str) -> List[JiraComment]:
        self._enter("comments", key=key)
        return list(self.comment_table.get(key, []))

    def add_comment(self, key: str, markdown: str) -> JiraComment:
        self._enter("add_comment", key=key, body=markdown)
        self.next_comment_id += 1
        comment = JiraComment(
            id=str(self.next_comment_id),
            author_id=self.account_id,
            body_md=markdown,
            created="2026-10-06T00:00:00.000+0000",
            url=self.config.comment_url(key, str(self.next_comment_id)),
            is_self=True,
        )
        self.posted.append({"key": key, "body": markdown, "url": comment.url})
        self.comment_table.setdefault(key, []).append(comment)
        return comment

    def transitions(self, key: str) -> List[JiraTransition]:
        self._enter("transitions", key=key)
        return list(self.transition_table.get(key, []))

    def transition(self, key: str, transition_id: str) -> None:
        self._enter("transition", key=key, transition_id=transition_id)
        self.transitioned.append({"key": key, "transition_id": transition_id})

    def search(
        self, jql: str, fields: Sequence[str] = (), limit: int = 200
    ) -> Iterator[JiraIssue]:
        self._enter("search", jql=jql, fields=list(fields))
        return iter(list(self.issues.values())[:limit])

    def create_issue(
        self,
        project: str,
        summary: str,
        description_md: str = "",
        labels: Sequence[str] = (),
        issue_type: str = "Task",
    ) -> JiraIssue:
        self._enter("create_issue", project=project, summary=summary)
        self.next_issue_number += 1
        key = f"{project}-{self.next_issue_number}"
        issue = JiraIssue(
            key=key,
            summary=summary,
            labels=list(labels),
            description_md=description_md,
            url=self.config.browse_url(key),
        )
        self.created.append({"key": key, "summary": summary, "labels": list(labels)})
        self.issues[key] = issue
        return issue

    def myself(self) -> str:
        self._enter("myself")
        return self.account_id


# ------------------------------------------------------------- the SDK double


class FakeSDKIssue:
    """The slice of ``jira.resources.Issue`` the client touches: ``raw``, ``key``
    and ``update``."""

    def __init__(self, sdk: "FakeJiraSDK", raw: Dict[str, Any]):
        self._sdk = sdk
        self.raw = raw
        self.key = raw.get("key", "")

    def update(self, fields: Any = None, update: Any = None, **kwargs: Any) -> None:
        self._sdk.calls.append(
            {"method": "issue.update", "key": self.key, "update": update, **kwargs}
        )
        labels = self.raw.setdefault("fields", {}).setdefault("labels", [])
        for op in (update or {}).get("labels", []):
            if "add" in op and op["add"] not in labels:
                labels.append(op["add"])
            if "remove" in op and op["remove"] in labels:
                labels.remove(op["remove"])


class FakeSDKComment:
    def __init__(self, raw: Dict[str, Any]):
        self.raw = raw
        self.id = raw.get("id", "")


@dataclass
class FakeJiraSDK:
    """Stands in for ``jira.JIRA``: canned raw documents, every call recorded.

    ``raise_on`` maps a method name to an exception it raises (a real
    ``JIRAError`` in the tests that check translation and scrubbing);
    ``on_call`` runs before each call, so a test can make the "SDK" log.
    """

    issues: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    comment_docs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    transition_docs: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    pages: List[Dict[str, Any]] = field(default_factory=list)
    me: Dict[str, Any] = field(default_factory=lambda: {"accountId": "5b10-bot"})
    raise_on: Dict[str, BaseException] = field(default_factory=dict)
    on_call: Optional[Any] = None
    calls: List[Dict[str, Any]] = field(default_factory=list)
    deploymentType: Optional[str] = None

    def _enter(self, method: str, **kwargs: Any) -> None:
        self.calls.append({"method": method, **kwargs})
        if self.on_call is not None:
            self.on_call(method)
        if method in self.raise_on:
            raise self.raise_on[method]

    def issue(self, id: str, fields: Any = None, expand: Any = None) -> FakeSDKIssue:
        self._enter("issue", key=id, fields=fields, expand=expand)
        raw = self.issues.get(id)
        if raw is None:
            from jira.exceptions import JIRAError

            raise JIRAError("Issue does not exist", status_code=404)
        return FakeSDKIssue(self, raw)

    def comments(self, issue: str, **kwargs: Any) -> List[FakeSDKComment]:
        self._enter("comments", key=issue, **kwargs)
        return [FakeSDKComment(doc) for doc in self.comment_docs.get(issue, [])]

    def add_comment(self, issue: str, body: Any, **kwargs: Any) -> FakeSDKComment:
        self._enter("add_comment", key=issue, body=body)
        doc = {
            "id": "10042",
            "author": {"accountId": self.me.get("accountId", "")},
            "body": body,
            "created": "2026-10-06T00:00:00.000+0000",
        }
        self.comment_docs.setdefault(issue, []).append(doc)
        return FakeSDKComment(doc)

    def transitions(self, issue: str, **kwargs: Any) -> List[Dict[str, Any]]:
        self._enter("transitions", key=issue)
        return list(self.transition_docs.get(issue, []))

    def transition_issue(self, issue: str, transition: str, **kwargs: Any) -> None:
        self._enter("transition_issue", key=issue, transition=transition)

    def myself(self) -> Dict[str, Any]:
        self._enter("myself")
        return dict(self.me)

    def create_issue(self, fields: Any = None, **kwargs: Any) -> FakeSDKIssue:
        self._enter("create_issue", fields=fields)
        project = (fields or {}).get("project", {}).get("key", "PROJ")
        raw = {"key": f"{project}-101", "fields": dict(fields or {})}
        self.issues[raw["key"]] = raw
        return FakeSDKIssue(self, raw)

    def enhanced_search_issues(self, jql_str: str, **kwargs: Any) -> Dict[str, Any]:
        self._enter("enhanced_search_issues", jql=jql_str, **kwargs)
        token = kwargs.get("nextPageToken")
        index = int(token) if token else 0
        return self.pages[index]

    def search_issues(self, jql_str: str, **kwargs: Any) -> Dict[str, Any]:
        self._enter("search_issues", jql=jql_str, **kwargs)
        start = int(kwargs.get("startAt") or 0)
        size = int(kwargs.get("maxResults") or 50)
        issues = [doc for page in self.pages for doc in page.get("issues", [])]
        return {"issues": issues[start : start + size], "total": len(issues)}
