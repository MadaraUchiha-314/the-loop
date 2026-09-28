"""The remote executor protocol — JSON-RPC 2.0 over HTTP, both halves (issue-344, R4).

The client (:class:`RemoteExecutor`) is what the daemon runs for a ``url`` entry; the
server (:func:`handle_request`, :class:`HookServer`) is what the SDK hands an operator
so the class they wrote for ``path:`` can be hosted unchanged. Wire format (sherma's):

    → {"jsonrpc": "2.0", "id": 1, "method": "work_item_start", "params": {…context…}}
    ← {"jsonrpc": "2.0", "id": 1, "result": null}                    pass through
    ← {"jsonrpc": "2.0", "id": 1, "result": {"proceed": false, …}}   decisions
    ← {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "…"}}

Everything is stdlib: ``urllib`` to send, ``http.server`` to host, ``json`` for the
envelope. A bearer token travels only from the variable ``tokenEnv`` names, read at
call time — never from the config, never into a log.
"""

from __future__ import annotations

import http.server
import json
import logging
import os
import socket
import threading
from typing import Any, Dict, Mapping, Optional, Tuple, Union
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .contract import POINTS, Context, LifecycleHooks
from .executors import Executor

logger = logging.getLogger("the-loop.lifecycle")

__all__ = ["HookFailure", "HookServer", "RemoteExecutor", "handle_request"]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HOOK_ERROR = -32000


class HookFailure(RuntimeError):
    """A remote invocation did not produce a usable answer — recorded, never raised
    into the-loop by the runner."""


# -- client ------------------------------------------------------------------------------


class RemoteExecutor(Executor):
    """One ``POST`` per point invocation to the operator's server."""

    def __init__(
        self,
        name: str,
        url: str,
        on: Tuple[str, ...] = (),
        required: bool = False,
        token_env: str = "",
        headers: Optional[Mapping[str, str]] = None,
        timeout: float = 10.0,
    ):
        super().__init__(name, on, required)
        self.url = url
        self.token_env = token_env
        self.headers = dict(headers or {})
        self.timeout = float(timeout)
        self._next_id = 0
        self._lock = threading.Lock()

    def handles(self, point: str) -> bool:
        return point in POINTS and (not self.on or point in self.on)

    def describe(self) -> Dict[str, Any]:
        row = super().describe()
        row.update(
            {
                "url": self.url,
                "tokenEnv": self.token_env or None,
                "timeoutSeconds": self.timeout,
            }
        )
        return row

    def call(self, point: str, ctx: Context) -> Optional[Mapping[str, Any]]:
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        headers.update(self.headers)
        if self.token_env:
            token = os.environ.get(self.token_env, "")
            if not token:
                raise HookFailure(
                    f"the bearer token variable {self.token_env} is unset or empty; "
                    "nothing was sent"
                )
            headers["Authorization"] = f"Bearer {token}"
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": point,
                "params": ctx.to_params(),
            }
        ).encode("utf-8")
        request = Request(self.url, data=body, headers=headers, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            raise HookFailure(f"HTTP {exc.code} from {self.url}") from None
        except (socket.timeout, TimeoutError):
            raise HookFailure(
                f"timed out after {self.timeout:g}s waiting for {self.url}"
            ) from None
        except URLError as exc:
            reason = exc.reason
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise HookFailure(
                    f"timed out after {self.timeout:g}s waiting for {self.url}"
                ) from None
            raise HookFailure(f"could not reach {self.url}: {reason}") from None
        except OSError as exc:
            raise HookFailure(f"could not reach {self.url}: {exc}") from None
        return self._read(raw, request_id)

    def _read(self, raw: bytes, request_id: int) -> Optional[Mapping[str, Any]]:
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise HookFailure(
                f"{self.url} answered with a body that is not JSON"
            ) from None
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            raise HookFailure(
                f"{self.url} answered with something other than JSON-RPC 2.0"
            )
        if message.get("id") != request_id:
            raise HookFailure(
                f"{self.url} answered request {message.get('id')!r}, not {request_id}"
            )
        if "error" in message:
            error = message["error"] or {}
            detail = error.get("message") if isinstance(error, dict) else error
            raise HookFailure(f"the hook server reported an error: {detail}")
        if "result" not in message:
            raise HookFailure(f"{self.url} answered with neither a result nor an error")
        result = message["result"]
        if result is None:
            return None
        if not isinstance(result, dict):
            raise HookFailure(
                f"{self.url} answered with a {type(result).__name__} result; expected an "
                "object of decisions or null"
            )
        return result


# -- server ------------------------------------------------------------------------------


def _error(request_id: Any, code: int, message: str) -> bytes:
    return json.dumps(
        {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": code, "message": message},
        }
    ).encode("utf-8")


def handle_request(executor: LifecycleHooks, body: Union[bytes, str]) -> bytes:
    """Answer one JSON-RPC request with ``executor``: the server half, for any HTTP
    framework. Returns the response body (always a JSON-RPC 2.0 message)."""
    try:
        message = json.loads(body if isinstance(body, str) else body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _error(None, PARSE_ERROR, "the request body is not JSON")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "expected a JSON-RPC 2.0 request object")
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params")
    if not isinstance(method, str) or not isinstance(params, dict):
        return _error(
            request_id,
            INVALID_REQUEST,
            "a request carries a `method` and a `params` object",
        )
    cls = POINTS.get(method)
    if cls is None:
        return _error(
            request_id, METHOD_NOT_FOUND, f"{method!r} is not a lifecycle point"
        )
    try:
        ctx = cls.from_params(params)
    except TypeError as exc:
        return _error(request_id, INVALID_PARAMS, str(exc))
    try:
        returned = getattr(executor, method)(ctx)
    except Exception as exc:  # noqa: BLE001 — the hook's error is the answer
        logger.exception("the %s hook raised", method)
        return _error(request_id, HOOK_ERROR, f"{exc.__class__.__name__}: {exc}")
    if returned is None:
        result: Any = None
    else:
        if not isinstance(returned, cls):
            return _error(
                request_id,
                HOOK_ERROR,
                f"the {method} hook returned a {type(returned).__name__}, not a {cls.__name__}",
            )
        result = {name: getattr(returned, name) for name in cls.decisions()}
    return json.dumps({"jsonrpc": "2.0", "id": request_id, "result": result}).encode(
        "utf-8"
    )


class HookServer:
    """A stdlib HTTP server hosting one executor.

    ``POST`` anywhere answers JSON-RPC through :func:`handle_request`; ``GET /health``
    answers ``{"ok": true, "points": [...]}`` without a token. With ``token_env`` set,
    every ``POST`` must carry ``Authorization: Bearer <value of that variable>`` or is
    refused ``401`` — the same variable name the daemon's ``tokenEnv`` names, read from
    this process's environment at request time.
    """

    def __init__(
        self,
        executor: LifecycleHooks,
        host: str = "127.0.0.1",
        port: int = 8000,
        token_env: str = "",
    ):
        self.executor = executor
        self.token_env = token_env
        self.points = tuple(p for p in POINTS if executor.handles(p))
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):  # noqa: A002 — http.server's name
                logger.debug("hook server: " + format, *args)

            def _send(self, status: int, body: bytes) -> None:
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802 — http.server's contract
                if self.path.rstrip("/").endswith("/health") or self.path in (
                    "/health",
                    "/health/",
                ):
                    self._send(
                        200,
                        json.dumps(
                            {"ok": True, "points": list(server.points)}
                        ).encode(),
                    )
                else:
                    self._send(
                        404, _error(None, METHOD_NOT_FOUND, "POST a JSON-RPC request")
                    )

            def do_POST(self):  # noqa: N802
                if server.token_env:
                    expected = os.environ.get(server.token_env, "")
                    given = self.headers.get("Authorization", "")
                    if not expected or given != f"Bearer {expected}":
                        self._send(401, _error(None, INVALID_REQUEST, "unauthorized"))
                        return
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                self._send(200, handle_request(server.executor, body))

        self._server = http.server.ThreadingHTTPServer((host, port), Handler)
        self._server.daemon_threads = True

    @property
    def address(self) -> Tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def url(self) -> str:
        host, port = self.address
        return f"http://{host}:{port}/"

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def serve_in_thread(self) -> threading.Thread:
        thread = threading.Thread(
            target=self.serve_forever, name="the-loop-hook-server", daemon=True
        )
        thread.start()
        return thread

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()
