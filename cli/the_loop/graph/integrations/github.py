"""The GitHub provider — the process graph's hooks over the daemon's client.

Until issue-442 this module carried two transports: ``api`` (a stdlib ``urllib``
client that still shelled out to ``gh auth token`` when no token was set) and
``cli`` (the operator's ``gh``). Both are one provider now, over
:class:`~the_loop.ghapi.GitHubClient` — PyGithub under the token
``integrations.github.api.tokenEnv`` names (decision-139). The operations a hook
may ask for are unchanged (``OPERATIONS``), and so is the contract: every
failure is an :class:`IntegrationError`, a missing token names the variables.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, FrozenSet, Optional

from ...ghapi import GitHubApiConfig, GitHubApiError, GitHubClient
from ...sessions import DEFAULT_GITHUB_HOST, is_github_host
from .base import IntegrationError, OperationUnsupported

logger = logging.getLogger("the-loop.graph.integrations")

__all__ = ["GitHubProvider", "OPERATIONS"]

#: Everything the-loop's own hooks need from GitHub. Small on purpose.
#: `get-thread` joined for the review loop (issue-279, the work-item-level
#: review): the brief gate must tell a pull request from a work item.
#:
#: `linked-pulls` was here too, until issue-370. It asked GitHub which pull
#: requests an issue links (the "Development" panel), to pre-fill a work-item
#: review's scope. the-loop does not ask that question any more: the pull
#: requests delivering a work item are the ones it recorded opening, in
#: `work-item-state.json`, which is both authoritative and able to see a spec
#: pull request — the one a work-item review most needs in scope, and the one
#: GitHub's answer never contained, because it closes nothing.
OPERATIONS: FrozenSet[str] = frozenset(
    {
        "add-comment",
        "set-labels",
        "create-label",
        "remove-label",
        "get-labels",
        "list-comments",
        "get-thread",
    }
)


def _ref_parts(ref: str) -> tuple[str, str, str, str]:
    """``github:[host/]owner/repo#123`` → ``(host, owner, repo, "123")``.

    ``host`` is ``""`` for github.com — the unwritten default — so a caller
    addresses a host exactly when it is not the default (issue-311).
    """
    body = ref.split(":", 1)[1] if ":" in ref else ref
    repo_part, _, number = body.partition("#")
    parts = repo_part.split("/")
    host, owner, repo = "", "", ""
    if len(parts) == 3:
        host, owner, repo = parts
        if not is_github_host(host):
            host, owner, repo = "", "", ""  # a path fragment, not a host: malformed
    elif len(parts) == 2:
        owner, repo = parts
    if host == DEFAULT_GITHUB_HOST:
        host = ""
    if not (owner and repo and number.isdigit()):
        # Name both remedies (issue-194). The value that lands here is almost
        # always a bare work-item id, because no `--ref` was passed and none
        # could be derived — and an error that says only "malformed" leaves the
        # operator to find that out from the source.
        raise IntegrationError(
            f"malformed work item ref: {ref!r} — expected "
            "'[<provider>:]<owner>/<repo>#<number>'. Pass --ref, or run from a "
            "checkout whose `origin` remote names the repository so the-loop "
            "can derive it."
        )
    return host, owner, repo, number


def _split_ref(ref: str) -> tuple[str, str, str]:
    """``github:owner/repo#123`` → ``(owner, repo, "123")`` — the host dropped."""
    _, owner, repo, number = _ref_parts(ref)
    return owner, repo, number


class GitHubProvider:
    """The one GitHub provider: PyGithub through :class:`GitHubClient`.

    ``transport`` reads ``"api"`` for anything that still inspects it — there is
    one way to reach GitHub now, and it is the API.
    """

    name = "github"
    transport = "api"
    operations = OPERATIONS

    def __init__(
        self,
        config: Optional[GitHubApiConfig] = None,
        client: Optional[GitHubClient] = None,
    ):
        self.config = config or GitHubApiConfig()
        self.client = client or GitHubClient.shared(self.config)

    def _run(self, fn):
        try:
            return fn()
        except GitHubApiError as exc:
            raise IntegrationError(f"github: {exc}") from None

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"github does not implement {op!r}")
        host, owner, repo, number_text = _ref_parts(str(params["ref"]))
        number = int(number_text)
        gh = self.client
        if op == "add-comment":
            url = self._run(
                lambda: gh.post_comment(
                    owner, repo, number, str(params["body"]), host=host
                )
            )
            return {"result": {"html_url": url}}
        if op == "set-labels":
            # Adds the named labels, leaving every other one in place — the
            # semantics the shipped hooks rely on (they take the previous phase
            # label off themselves through `remove-label`).
            labels = [str(lbl) for lbl in params["labels"]]
            self._run(lambda: gh.add_labels(owner, repo, number, labels, host=host))
            return {"result": "ok"}
        if op == "create-label":
            # issue-393 F3/R13: create a label the repository does not have yet,
            # so the daemon can label a repo that was never `/the-loop:init`-ed.
            # A label that already exists is success (the label is there).
            created = self._run(
                lambda: gh.ensure_label(
                    owner,
                    repo,
                    str(params["name"]),
                    str(params.get("color") or "ededed"),
                    host=host,
                )
            )
            return {"result": "ok" if created else "exists"}
        if op == "remove-label":
            # issue-393 B10: take ONE label off, leaving the rest. A label the
            # issue does not carry is success (it is not there).
            removed = self._run(
                lambda: gh.remove_label(
                    owner, repo, number, str(params["label"]), host=host
                )
            )
            return {"result": "ok" if removed else "absent"}
        if op == "get-labels":
            return {
                "labels": self._run(
                    lambda: gh.labels_of(owner, repo, number, host=host)
                )
            }
        if op == "get-thread":
            data = self._run(lambda: gh.get_issue(owner, repo, number, host=host))
            kind = "pull-request" if "pull_request" in data else "issue"
            return {"kind": kind}
        comments = self._run(
            lambda: gh.list_issue_comments(owner, repo, number, host=host)
        )
        return {
            "comments": [
                {
                    "id": c.id,
                    "body": c.body,
                    "author": {"login": c.author},
                    "user": {"login": c.author},
                    "created_at": c.created_at,
                    "createdAt": c.created_at,
                    "html_url": c.url,
                    "url": c.url,
                }
                for c in comments
            ]
        }
