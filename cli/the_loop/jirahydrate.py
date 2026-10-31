"""Pull a Jira ticket into the GitHub issue that is named after it.

An issue whose title *starts with* a configured Jira key (``PROJ-123`` or
``PROJ-123: fix login``) gets that ticket's details written into its body, once,
between two hidden markers. The poller then dispatches the issue with the content
already there, so a session never has to go and fetch it.

Opt-in (``integrations.jira.hydrate``), read-only towards Jira, and best-effort:
every failure is logged and skipped, never raised, because an issue that cannot be
hydrated must still be worked. The block is written only while the body carries no
block for any key, so a poll, a restart or a second poller finds it already there.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, Optional

from .ghapi import GitHubClient
from .jiraapi import JiraApiConfig, JiraClient, JiraIssue, scrub
from .jiraformat import defang_markers

logger = logging.getLogger("the-loop.jirahydrate")

__all__ = ["JiraHydrator", "has_block", "leading_key", "render_block", "with_block"]

_LEADING_KEY = re.compile(r"^\s*([A-Z][A-Z0-9_]{1,9}-\d+)(?![\w-])")
_BLOCK_BEGIN = re.compile(r"<!--\s*the-loop:jira-context:begin\b")


def leading_key(title: str, projects: Any) -> Optional[str]:
    """The Jira key ``title`` starts with, when its project is one of ``projects``."""
    found = _LEADING_KEY.match(title or "")
    if not found:
        return None
    key = found.group(1)
    return key if key.rsplit("-", 1)[0] in set(projects) else None


def has_block(body: str) -> bool:
    """Whether ``body`` already carries a Jira context block, for any key."""
    return bool(_BLOCK_BEGIN.search(body or ""))


def _line(text: str) -> str:
    return defang_markers(" ".join(str(text or "").split()))


def render_block(issue: JiraIssue) -> str:
    """The block for ``issue``. Jira's words are defanged: a ticket must not be able
    to plant a marker the-loop's gates would read."""
    heading = f"**[{issue.key}]({issue.url})**" if issue.url else f"**{issue.key}**"
    rows = [f"{heading} — {_line(issue.summary)}"]
    facts = [
        ("Status", issue.status),
        ("Type", issue.issue_type),
        ("Priority", issue.priority),
        ("Assignee", issue.assignee),
        ("Labels", ", ".join(issue.labels)),
    ]
    rows += [f"- **{name}:** {_line(value)}" for name, value in facts if value]
    description = defang_markers((issue.description_md or "").strip())
    parts = ["\n".join(rows)]
    if description:
        parts.append(f"### Description\n\n{description}")
    return (
        f"<!-- the-loop:jira-context:begin {issue.key} -->\n"
        + "\n\n".join(parts)
        + "\n<!-- the-loop:jira-context:end -->"
    )


def with_block(body: str, block: str) -> str:
    """``body`` with ``block`` above it; what the author wrote stays untouched."""
    rest = (body or "").lstrip("\n")
    return f"{block}\n\n{rest}" if rest else f"{block}\n"


class JiraHydrator:
    """Hydrates one polled issue. Built from the CLI config; ``None`` when Jira is
    unconfigured or ``integrations.jira.hydrate`` is not true."""

    def __init__(self, config: JiraApiConfig, jira: JiraClient, github: GitHubClient):
        self.config = config
        self.jira = jira
        self.github = github

    @classmethod
    def from_config(
        cls,
        config: Optional[Mapping[str, Any]],
        github: Optional[GitHubClient] = None,
    ) -> Optional["JiraHydrator"]:
        integrations = (dict(config or {}).get("integrations")) or {}
        block = integrations.get("jira") if isinstance(integrations, Mapping) else None
        if not isinstance(block, Mapping) or block.get("hydrate") is not True:
            return None
        api = JiraApiConfig.from_cli_config(config)
        if not api.configured or not api.projects:
            return None
        return cls(api, JiraClient.shared(api), github or GitHubClient())

    def hydrate(
        self, owner: str, repo: str, number: int, title: str, body: str, host: str = ""
    ) -> Optional[str]:
        """The new body when this call wrote one, else ``None``. Never raises."""
        key = leading_key(title, self.config.projects)
        if key is None or has_block(body):
            return None
        where = f"{owner}/{repo}#{number}"
        try:
            if not self.jira.has_credentials():
                logger.warning(
                    "jira hydrate: %s names %s but the Jira credential is not set",
                    where,
                    key,
                )
                return None
            issue = self.jira.get_issue(key)
            # Re-read just before writing: the listing may be a cycle old, and an
            # author's edit (or another poller's block) must not be overwritten.
            current = self.github.get_issue(owner, repo, number, host)
            fresh = str(current.get("body") or "")
            if has_block(fresh):
                return None
            updated = with_block(fresh, render_block(issue))
            self.github.edit_issue_body(owner, repo, number, updated, host)
        except Exception as exc:  # noqa: BLE001 — hydration must never stop a poll
            logger.warning(
                "jira hydrate: %s (%s) skipped: %s", where, key, scrub(str(exc))
            )
            return None
        logger.info("jira hydrate: %s took %s into its body", where, key)
        return updated
