"""The CLI's HTTP client for the control-plane service (issue-161, R2.2).

Stdlib only (``urllib``) so the base install stays one-dependency: a plain
install can *talk to* a service even where the ``[service]`` extra that *hosts*
one is absent. The service is the CLI's only execution path for core
capabilities (owner decision, PR #162): when none is reachable this module
auto-starts a local one if the config allows and the extra is importable, and
otherwise **fails closed** naming the lifecycle command and the install line —
it never quietly falls back to executing core logic in-process (R2.3).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from ..api.config import base_url, service_config, token_path
from ..api.auth import read_token

#: How long auto-start waits for /health before giving up.
_AUTOSTART_TIMEOUT = 15.0

INSTALL_HINT = (
    "the control-plane service is not running and could not be started. "
    "Start it with `the-loop service start` (requires `pip install "
    "'the-loopy-one[service]'`)."
)


class ServiceUnavailable(RuntimeError):
    """No reachable service, and none could be (auto-)started."""


class ApiError(RuntimeError):
    """The service answered with an error status."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail or f"HTTP {status}")
        self.status = status
        self.detail = detail


def _request(
    method: str,
    url: str,
    token: str,
    body: Optional[dict] = None,
    timeout: float = 120.0,
) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — http(s) URL built from config
            return json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("detail", "")
        except Exception:
            detail = ""
        raise ApiError(exc.code, detail) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise ServiceUnavailable(str(exc)) from exc


def healthy(config: Optional[dict] = None, timeout: float = 2.0) -> bool:
    try:
        request = urllib.request.Request(f"{base_url(config)}/api/v1/health")
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
            return True
    except Exception:
        return False


def _service_extra_available() -> bool:
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError:
        return False
    return True


def _spawn_service() -> None:
    subprocess.Popen(  # noqa: S603 — fixed argv, no shell
        [sys.executable, "-m", "the_loop.api.serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def ensure_service(config: Optional[dict] = None) -> None:
    """A reachable service, or :class:`ServiceUnavailable` — never a fallback."""
    if healthy(config):
        return
    conf = service_config(config)
    if conf["autoStart"] and _service_extra_available():
        _spawn_service()
        deadline = time.monotonic() + _AUTOSTART_TIMEOUT
        while time.monotonic() < deadline:
            if healthy(config):
                return
            time.sleep(0.25)
    raise ServiceUnavailable(INSTALL_HINT)


class Client:
    """One configured connection: base URL + bearer token."""

    def __init__(self, config: Optional[dict] = None):
        self._config = config
        self._base = base_url(config)
        self._token = read_token(token_path(config))

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = ""
        if params:
            filtered = {k: v for k, v in params.items() if v not in (None, "", [])}
            if filtered:
                query = "?" + urllib.parse.urlencode(filtered, doseq=True)
        return _request("GET", f"{self._base}/api/v1{path}{query}", self._token)

    def post(self, path: str, body: dict) -> Any:
        return _request("POST", f"{self._base}/api/v1{path}", self._token, body=body)


def connect(config: Optional[dict] = None) -> Client:
    """Ensure a service is reachable (auto-starting if permitted), then a client."""
    ensure_service(config)
    return Client(config)
