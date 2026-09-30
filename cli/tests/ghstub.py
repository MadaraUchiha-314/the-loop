"""A loopback GitHub for the daemon integration tests (issue-442).

The daemon tests start real ``the-loop`` processes. Those processes reach
GitHub through PyGithub now, not through a stub ``gh`` on ``PATH``, so the seam
that keeps them off the network is the API base: the CLI config points
``integrations.github.api.baseUrl`` at this server, and ``GH_TOKEN`` is set in
the child's environment. It answers every listing empty — a cycle runs to
completion with nothing discovered and nothing spawned — and anything else
with an empty document, exactly as the stub ``gh`` used to.

``requests`` (under PyGithub) honours ``HTTP_PROXY``/``HTTPS_PROXY`` for
non-loopback hosts only, so a ``127.0.0.1`` base is reached directly.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Tuple

__all__ = ["FakeGitHubServer"]

_EMPTY_PAGE = {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": []}


class _Handler(BaseHTTPRequestHandler):
    server: "FakeGitHubServer"  # type: ignore[assignment]

    def log_message(self, format: str, *args: Any) -> None:  # quiet
        pass

    def _send(self, status: int, body: Any) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802 — http.server's name
        self.server.requests.append(("GET", self.path, None))
        if self.path.startswith("/user"):
            self._send(200, {"login": "the-loop-bot"})
            return
        self._send(
            200,
            []
            if self.path.rstrip("/")
            .split("?")[0]
            .endswith(("/reviews", "/comments", "/labels"))
            else {},
        )

    def do_POST(self) -> None:  # noqa: N802 — http.server's name
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            document = json.loads(raw.decode() or "null")
        except ValueError:
            document = None
        self.server.requests.append(("POST", self.path, document))
        if self.path.rstrip("/").endswith("/graphql"):
            self._send(
                200,
                {
                    "data": {
                        "repository": {
                            "hasIssuesEnabled": True,
                            "issues": dict(_EMPTY_PAGE),
                            "pullRequests": dict(_EMPTY_PAGE),
                            "issueOrPullRequest": {"comments": dict(_EMPTY_PAGE)},
                        },
                        "addReaction": {"clientMutationId": None},
                    }
                },
            )
            return
        self._send(201, {"id": 1, "number": 1, "html_url": "http://fake/1"})


class FakeGitHubServer(ThreadingHTTPServer):
    """``with FakeGitHubServer() as github: … github.base_url …``"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.requests: List[Tuple[str, str, Any]] = []
        self._thread = threading.Thread(target=self.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def config_block(self) -> Dict[str, Any]:
        """The ``integrations`` block that points a CLI config here.

        ``host: github.com`` keeps the scopes named as they are on github.com
        (`octo/repo`, not `127.0.0.1:<port>/octo/repo`): the base is where the
        API is reached, the host is which GitHub the work items are on.
        """
        return {
            "integrations": {
                "github": {"host": "github.com", "api": {"baseUrl": self.base_url}}
            }
        }

    def config_yaml(self) -> str:
        return (
            "integrations:\n  github:\n    host: github.com\n    api:\n"
            f"      baseUrl: {self.base_url}\n"
        )

    def __enter__(self) -> "FakeGitHubServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.shutdown()
        self.server_close()
