"""GitHub providers — `api` (stdlib HTTP) and `cli` (the existing `gh` path).

GitHub publishes **no official Python SDK** — its own docs list every Python
library as third-party and unmaintained by GitHub, while official Octokit covers
JS/Ruby/.NET only. The community options cost five or six transitive packages
(PyGithub even a compiled one) to wrap roughly ten endpoints, against a runtime
footprint of `pyyaml`. So: thin REST, or the `gh` binary the operator already
authenticated.

The `cli` transport is not a fallback — it is genuinely better in some
environments, because it inherits the operator's `gh auth`, including enterprise
and SSO configuration.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any, Dict, FrozenSet, Sequence

from ...comments import gh_host_args
from ...ghhost import PUBLIC_API_BASE, api_base_for
from ...sessions import DEFAULT_GITHUB_HOST, WorkItemRef, is_github_host
from .base import IntegrationError, OperationUnsupported

logger = logging.getLogger("the-loop.graph.integrations")

__all__ = ["GitHubApi", "GitHubCli", "OPERATIONS"]

#: Everything the-loop's own hooks need from GitHub. Small on purpose.
#: `get-thread` and `linked-pulls` joined for the review loop (issue-279, the
#: work-item-level review): the brief gate must tell a pull request from a
#: work item, and may suggest the pull requests a work item is linked to.
OPERATIONS: FrozenSet[str] = frozenset(
    {
        "add-comment",
        "set-labels",
        "get-labels",
        "list-comments",
        "get-thread",
        "linked-pulls",
    }
)

#: GraphQL for the one association REST does not expose: the pull requests
#: that close a work item (the "Development" panel's links). First 50 — a
#: work item with more linked PRs than that has bigger problems than a
#: truncated suggestion list, and the reviewer can always state the rest.
_LINKED_PULLS_QUERY = """
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    issue(number: $number) {
      closedByPullRequestsReferences(first: 50, includeClosedPrs: true) {
        nodes { number repository { nameWithOwner } }
      }
    }
  }
}
"""


def _linked_pull_refs(data: Dict[str, Any], host: str = "") -> list[str]:
    """``github:[host/]owner/repo#n`` refs out of the GraphQL response — or empty.

    ``host`` is the GitHub the question was asked on (issue-311, R4.4): the
    answer names repositories by ``nameWithOwner`` alone, so the refs composed
    from it carry the host the-loop already knew, spelled by ``WorkItemRef`` so
    github.com stays unwritten.
    """
    nodes = (((data.get("data") or {}).get("repository") or {}).get("issue") or {}).get(
        "closedByPullRequestsReferences"
    ) or {}
    refs: list[str] = []
    for node in nodes.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        number = node.get("number")
        slug = (node.get("repository") or {}).get("nameWithOwner") or ""
        owner, _, repo = str(slug).partition("/")
        if isinstance(number, int) and owner and repo:
            refs.append(
                WorkItemRef(
                    provider="github", owner=owner, repo=repo, number=number, host=host
                ).ref
            )
    return refs


def _ref_parts(ref: str) -> tuple[str, str, str, str]:
    """``github:[host/]owner/repo#123`` → ``(host, owner, repo, "123")``.

    ``host`` is ``""`` for github.com — the unwritten default — so a caller
    spelling a ``--repo`` or a ``--hostname`` writes it exactly when it is not
    the default (issue-311).
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
    if not (owner and repo and number):
        # Name both remedies (issue-194). The value that lands here is almost
        # always a bare work-item id, because no `--ref` was passed and none
        # could be derived — and an error that says only "malformed" leaves the
        # operator to find that out from the source.
        raise IntegrationError(
            f"malformed work item ref: {ref!r} — expected "
            "'[<provider>:]<owner>/<repo>#<number>'. Pass --ref, or declare "
            "ticketing.github in .the-loop/harness-config.yaml so the-loop can "
            "derive it."
        )
    return host, owner, repo, number


def _split_ref(ref: str) -> tuple[str, str, str]:
    """``github:owner/repo#123`` → ``(owner, repo, "123")`` — the host dropped."""
    _, owner, repo, number = _ref_parts(ref)
    return owner, repo, number


class GitHubApi:
    """REST over the standard library. No dependency, works in a bare container."""

    name = "github"
    transport = "api"
    operations = OPERATIONS

    def __init__(
        self, token_envs: Sequence[str], base_url: str = "https://api.github.com"
    ):
        self.token_envs = list(token_envs)
        self.base_url = base_url.rstrip("/")

    def _token(self) -> str:
        for env in self.token_envs:
            value = os.environ.get(env)
            if value:
                return value
        # `gh` auth ergonomics without depending on `gh` at call time.
        if shutil.which("gh"):
            try:
                proc = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, timeout=15
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
        raise IntegrationError(
            f"github api transport has no credentials — set one of "
            f"{', '.join(self.token_envs)}, or run `gh auth login`"
        )

    def _base_for(self, host: str) -> str:
        """The REST base a hosted ref is addressed at (issue-311, R4.3).

        A ref on GitHub Enterprise against the **public** default derives
        ``https://<host>/api/v3`` — the case nobody configured. An explicit
        ``baseUrl`` is the operator's and is honoured verbatim (decision-042).
        """
        if host and self.base_url == PUBLIC_API_BASE:
            return api_base_for(host)
        return self.base_url

    def _request(
        self,
        method: str,
        path: str,
        payload: Dict[str, Any] | None = None,
        host: str = "",
    ):
        url = f"{self._base_for(host)}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token()}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode() or "{}"
        except urllib.error.HTTPError as exc:
            raise IntegrationError(
                f"github api {method} {path} failed: {exc.code} {exc.reason}"
            ) from None
        except urllib.error.URLError as exc:
            raise IntegrationError(
                f"github api {method} {path} failed: {exc.reason}"
            ) from None
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"github/api does not implement {op!r}")
        host, owner, repo, number = _ref_parts(str(params["ref"]))
        if op == "add-comment":
            return {
                "result": self._request(
                    "POST",
                    f"/repos/{owner}/{repo}/issues/{number}/comments",
                    {"body": str(params["body"])},
                    host=host,
                )
            }
        if op == "set-labels":
            return {
                "result": self._request(
                    "PUT",
                    f"/repos/{owner}/{repo}/issues/{number}/labels",
                    {"labels": list(params["labels"])},
                    host=host,
                )
            }
        if op == "get-labels":
            data = self._request(
                "GET", f"/repos/{owner}/{repo}/issues/{number}/labels", host=host
            )
            return {"labels": [d.get("name") for d in data if isinstance(d, dict)]}
        if op == "get-thread":
            data = self._request(
                "GET", f"/repos/{owner}/{repo}/issues/{number}", host=host
            )
            kind = "pull-request" if "pull_request" in data else "issue"
            return {"kind": kind}
        if op == "linked-pulls":
            data = self._request(
                "POST",
                "/graphql",
                {
                    "query": _LINKED_PULLS_QUERY,
                    "variables": {
                        "owner": owner,
                        "repo": repo,
                        "number": int(number),
                    },
                },
                host=host,
            )
            return {"pulls": _linked_pull_refs(data, host)}
        data = self._request(
            "GET", f"/repos/{owner}/{repo}/issues/{number}/comments", host=host
        )
        return {"comments": data}


class GitHubCli:
    """The existing `gh` path, wrapped as a provider rather than replaced.

    Configurable transport is what turned this migration from a big-bang rewrite
    into an addition: `announce`, `comments`, `control`, `reactions` and the
    poller keep working, and the API transport lands beside them.
    """

    name = "github"
    transport = "cli"
    operations = OPERATIONS

    def __init__(self, binary: str = "gh"):
        self.binary = binary

    def _run(self, args: list[str]) -> str:
        if not shutil.which(self.binary):
            raise IntegrationError(
                f"github cli transport needs {self.binary!r} on PATH — install it, "
                "or set integrations.github.transport: api with a token"
            )
        proc = subprocess.run(
            [self.binary, *args], capture_output=True, text=True, timeout=60
        )
        if proc.returncode != 0:
            raise IntegrationError(
                f"{self.binary} {' '.join(args[:3])} failed: "
                f"{(proc.stderr or proc.stdout).strip()}"
            )
        return proc.stdout

    def call(self, op: str, **params: Any) -> Dict[str, Any]:
        if op not in self.operations:
            raise OperationUnsupported(f"github/cli does not implement {op!r}")
        host, owner, repo, number = _ref_parts(str(params["ref"]))
        # gh's own grammars (issue-311): `--repo [HOST/]OWNER/REPO` for the
        # issue verbs, `--hostname` for `api`; both written only off github.com.
        slug = f"{host}/{owner}/{repo}" if host else f"{owner}/{repo}"
        api = ["api", *gh_host_args(host)]
        if op == "add-comment":
            self._run(
                [
                    "issue",
                    "comment",
                    number,
                    "--repo",
                    slug,
                    "--body",
                    str(params["body"]),
                ]
            )
            return {"result": "ok"}
        if op == "set-labels":
            args = ["issue", "edit", number, "--repo", slug]
            for label in params["labels"]:
                args += ["--add-label", str(label)]
            self._run(args)
            return {"result": "ok"}
        if op == "get-labels":
            out = self._run(
                ["issue", "view", number, "--repo", slug, "--json", "labels"]
            )
            data = json.loads(out or "{}")
            return {"labels": [d.get("name") for d in data.get("labels", [])]}
        if op == "get-thread":
            out = self._run([*api, f"repos/{owner}/{repo}/issues/{number}"])
            data = json.loads(out or "{}")
            kind = "pull-request" if "pull_request" in data else "issue"
            return {"kind": kind}
        if op == "linked-pulls":
            out = self._run(
                [
                    *api,
                    "graphql",
                    "-f",
                    f"query={_LINKED_PULLS_QUERY}",
                    "-F",
                    f"owner={owner}",
                    "-F",
                    f"repo={repo}",
                    "-F",
                    f"number={number}",
                ]
            )
            return {"pulls": _linked_pull_refs(json.loads(out or "{}"), host)}
        out = self._run(["issue", "view", number, "--repo", slug, "--json", "comments"])
        return {"comments": json.loads(out or "{}").get("comments", [])}
