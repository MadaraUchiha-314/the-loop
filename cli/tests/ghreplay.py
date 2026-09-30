"""A replaying HTTP connection for PyGithub — no network, real PyGithub (issue-442).

PyGithub tests itself by injecting a connection class
(``Requester.injectConnectionClasses``); this module does the same for the-loop's
suite. :class:`ReplayConnection` mimics the ``httplib``-shaped interface
PyGithub's ``HTTPSRequestsConnectionClass`` presents — ``request(verb, url,
input, headers)``, ``getresponse()`` → ``status``/``getheaders()``/``read()``,
``close()`` — and answers from **routes** the test declares, recording every
exchange (host, verb, path, decoded JSON body, headers) so a test asserts the
request PyGithub really sent, not a fake of it.

Routes are matched in declaration order by ``(verb, path)``; a path may be a
predicate. A route's answer is ``(status, body)`` or ``(status, body, headers)``
— ``Link`` headers included, so pagination is exercised for real. A request with
no route answers ``404`` with GitHub's ``Not Found`` document, which is what an
unmocked call would look like against the real API.

GraphQL requests are ``POST /graphql`` with ``{"query", "variables"}``; a route
may match on the operation by inspecting ``exchange.json["query"]`` through the
predicate form, or a test uses :meth:`Replay.graphql` to answer by a substring
of the query.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import pytest
from github.Requester import Requester

__all__ = ["Exchange", "Replay", "ReplayConnection", "github_replay"]

NOT_FOUND = {
    "message": "Not Found",
    "documentation_url": "https://docs.github.com/rest",
}


@dataclass
class Exchange:
    """One request PyGithub made, as the connection saw it."""

    host: str
    verb: str
    url: str  # path plus query string, as sent
    headers: Dict[str, str]
    body: str

    @property
    def path(self) -> str:
        return self.url.split("?", 1)[0]

    @property
    def query(self) -> str:
        return self.url.split("?", 1)[1] if "?" in self.url else ""

    @property
    def json(self) -> Any:
        try:
            return json.loads(self.body) if self.body else None
        except ValueError:
            return None

    @property
    def authorization(self) -> str:
        return str(self.headers.get("Authorization") or "")


Matcher = Union[str, Callable[[Exchange], bool]]
Answer = Union[Tuple[int, Any], Tuple[int, Any, Dict[str, str]]]


@dataclass
class Replay:
    """The route table and the exchange log, shared by every connection built
    while the fixture is active."""

    routes: List[Tuple[str, Matcher, Callable[[Exchange], Answer]]] = field(
        default_factory=list
    )
    exchanges: List[Exchange] = field(default_factory=list)
    connections: int = 0

    # -- declaring answers ---------------------------------------------------------

    def on(
        self,
        verb: str,
        path: Matcher,
        status: int = 200,
        body: Any = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> "Replay":
        """Answer ``verb path`` with a fixed document."""
        answer = (status, body, headers or {})
        self.routes.append((verb.upper(), path, lambda _exchange: answer))
        return self

    def reply(
        self, verb: str, path: Matcher, fn: Callable[[Exchange], Answer]
    ) -> "Replay":
        """Answer ``verb path`` from a function of the exchange."""
        self.routes.append((verb.upper(), path, fn))
        return self

    def graphql(
        self, contains: str, data: Any = None, errors: Any = None, status: int = 200
    ) -> "Replay":
        """Answer a GraphQL POST whose query text contains ``contains``.

        ``data`` may be a document or a function of the exchange (for cursor
        walks); ``errors`` puts an ``errors`` array on the response.
        """

        def match(exchange: Exchange) -> bool:
            doc = exchange.json
            return (
                exchange.path.endswith("/graphql")
                and isinstance(doc, dict)
                and contains in str(doc.get("query") or "")
            )

        def answer(exchange: Exchange) -> Answer:
            payload: Dict[str, Any] = {}
            value = data(exchange) if callable(data) else data
            if value is not None:
                payload["data"] = value
            if errors is not None:
                payload["errors"] = errors
            return status, payload, {}

        self.routes.append(("POST", match, answer))
        return self

    # -- reading the log --------------------------------------------------------

    def sent(self, verb: Optional[str] = None) -> List[Exchange]:
        return [e for e in self.exchanges if verb is None or e.verb == verb.upper()]

    def graphql_calls(self) -> List[Exchange]:
        return [e for e in self.exchanges if e.path.endswith("/graphql")]

    def rest_calls(self) -> List[Exchange]:
        return [e for e in self.exchanges if not e.path.endswith("/graphql")]

    # -- answering --------------------------------------------------------------

    def answer(self, exchange: Exchange) -> Tuple[int, Any, Dict[str, str]]:
        for verb, matcher, fn in self.routes:
            if verb != exchange.verb:
                continue
            if callable(matcher):
                if not matcher(exchange):
                    continue
            elif matcher != exchange.path:
                continue
            result = fn(exchange)
            if len(result) == 2:
                return result[0], result[1], {}
            return result[0], result[1], dict(result[2] or {})  # type: ignore[misc]
        return 404, NOT_FOUND, {}


class _Response:
    def __init__(self, status: int, body: Any, headers: Dict[str, str]):
        self.status = status
        self._body = body
        self._headers = {"content-type": "application/json; charset=utf-8"}
        self._headers.update(headers)

    def getheaders(self):
        return self._headers.items()

    def read(self) -> str:
        if self._body is None:
            return ""
        if isinstance(self._body, str):
            return self._body
        return json.dumps(self._body)

    def close(self) -> None:  # pragma: no cover - interface parity
        pass


class ReplayConnection:
    """The connection class PyGithub instantiates per request while injected."""

    replay: Optional[Replay] = None

    def __init__(
        self, host: str, port: Optional[int] = None, *args: Any, **kwargs: Any
    ):
        self.host = host
        self.port = port
        replay = type(self).replay
        assert replay is not None, (
            "ReplayConnection used outside the github_replay fixture"
        )
        replay.connections += 1
        self._pending: Optional[Exchange] = None

    def request(
        self, verb: str, url: str, input: Any, headers: Dict[str, str], *a: Any
    ) -> None:
        body = (
            input
            if isinstance(input, str)
            else (input.read() if hasattr(input, "read") else "")
        )
        self._pending = Exchange(
            host=self.host,
            verb=verb.upper(),
            url=url,
            headers=dict(headers),
            body=body or "",
        )

    def getresponse(self) -> _Response:
        replay = type(self).replay
        assert replay is not None and self._pending is not None
        replay.exchanges.append(self._pending)
        status, body, headers = replay.answer(self._pending)
        return _Response(status, body, headers)

    def close(self) -> None:
        pass


@pytest.fixture
def github_replay():
    """Route PyGithub's HTTP through :class:`ReplayConnection` for one test."""
    replay = Replay()
    ReplayConnection.replay = replay
    Requester.injectConnectionClasses(ReplayConnection, ReplayConnection)  # type: ignore[arg-type]
    try:
        yield replay
    finally:
        Requester.resetConnectionClasses()
        ReplayConnection.replay = None
