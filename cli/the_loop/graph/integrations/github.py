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


def _linked_pull_refs(data: Dict[str, Any]) -> list[str]:
    """``github:owner/repo#n`` refs out of the GraphQL response — or empty."""
    nodes = (((data.get("data") or {}).get("repository") or {}).get("issue") or {}).get(
        "closedByPullRequestsReferences"
    ) or {}
    refs: list[str] = []
    for node in nodes.get("nodes") or []:
        if not isinstance(node, dict):
            continue
        number = node.get("number")
        slug = (node.get("repository") or {}).get("nameWithOwner") or ""
        if isinstance(number, int) and slug:
            refs.append(f"github:{slug}#{number}")
    return refs


def _split_ref(ref: str) -> tuple[str, str, str]:
    """``github:owner/repo#123`` → ``(owner, repo, "123")``."""
    body = ref.split(":", 1)[1] if ":" in ref else ref
    repo_part, _, number = body.partition("#")
    owner, _, repo = repo_part.partition("/")
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

    def _request(self, method: str, path: str, payload: Dict[str, Any] | None = None):
        url = f"{self.base_url}{path}"
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
        owner, repo, number = _split_ref(str(params["ref"]))
        if op == "add-comment":
            return {
                "result": self._request(
                    "POST",
                    f"/repos/{owner}/{repo}/issues/{number}/comments",
                    {"body": str(params["body"])},
                )
            }
        if op == "set-labels":
            return {
                "result": self._request(
                    "PUT",
                    f"/repos/{owner}/{repo}/issues/{number}/labels",
                    {"labels": list(params["labels"])},
                )
            }
        if op == "get-labels":
            data = self._request("GET", f"/repos/{owner}/{repo}/issues/{number}/labels")
            return {"labels": [d.get("name") for d in data if isinstance(d, dict)]}
        if op == "get-thread":
            data = self._request("GET", f"/repos/{owner}/{repo}/issues/{number}")
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
            )
            return {"pulls": _linked_pull_refs(data)}
        data = self._request("GET", f"/repos/{owner}/{repo}/issues/{number}/comments")
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
        owner, repo, number = _split_ref(str(params["ref"]))
        slug = f"{owner}/{repo}"
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
            out = self._run(["api", f"repos/{owner}/{repo}/issues/{number}"])
            data = json.loads(out or "{}")
            kind = "pull-request" if "pull_request" in data else "issue"
            return {"kind": kind}
        if op == "linked-pulls":
            out = self._run(
                [
                    "api",
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
            return {"pulls": _linked_pull_refs(json.loads(out or "{}"))}
        out = self._run(["issue", "view", number, "--repo", slug, "--json", "comments"])
        return {"comments": json.loads(out or "{}").get("comments", [])}
