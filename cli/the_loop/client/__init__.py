"""The CLI's HTTP client for the control-plane service (issue-161, R2.2).

Stdlib only (``urllib``) for the transport itself — nothing here needs a
third-party HTTP client. The service is the CLI's only execution path for core
capabilities (owner decision, PR #162): when none is reachable this module
auto-starts a local one if the config allows, and otherwise **fails closed**
naming the lifecycle command — it never quietly falls back to executing core
logic in-process (R2.3). Everything needed to host a service ships with the
package (no extras), so an unreachable service is a lifecycle problem, never a
missing-install one.
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

from ..api.config import base_url, service_config

#: How long auto-start waits for /health before giving up.
_AUTOSTART_TIMEOUT = 15.0

UNAVAILABLE_HINT = (
    "the control-plane service is not running and could not be started. "
    "Start it with `the-loop start`, or check "
    "`the-loop events --source service` for why it exited."
)

DISABLED_HINT = (
    "the control-plane service is disabled (service.enabled: false in the CLI "
    "config) and will not be auto-started. Set service.enabled: true, then run "
    "`the-loop start`."
)


class ServiceUnavailable(RuntimeError):
    """No reachable service, and none could be (auto-)started."""


def _resolved(config: Optional[dict]) -> dict:
    """``config``, or the operator's CLI config loaded from its default path.

    Without this, a caller that passes ``None`` would silently talk to the
    built-in host/port even where the operator configured others — the exact
    "ignored a value the operator set" failure the config loader refuses.
    """
    if config is not None:
        return config
    from ..cli_config import default_cli_config_path, load_cli_config

    try:
        return load_cli_config(default_cli_config_path())
    except Exception:
        return {}


class ApiError(RuntimeError):
    """The service answered with an error status."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail or f"HTTP {status}")
        self.status = status
        self.detail = detail


def _request(
    method: str,
    url: str,
    body: Optional[dict] = None,
    timeout: float = 120.0,
) -> Any:
    # No auth header: the service carries no in-app auth (the gateway owns it,
    # owner decision PR #162), and locally it is loopback-only.
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
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
    config = _resolved(config)
    try:
        request = urllib.request.Request(f"{base_url(config)}/api/v1/health")
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310
            return True
    except Exception:
        return False


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
    config = _resolved(config)
    if healthy(config):
        return
    conf = service_config(config)
    # Fail closed on disablement (issue-228, R5.2): an operator who set
    # service.enabled: false must not have the service resurrected because an
    # unrelated CLI command wanted it. The explicit lifecycle verbs still work.
    if not conf["enabled"]:
        raise ServiceUnavailable(DISABLED_HINT)
    if conf["autoStart"]:
        _spawn_service()
        deadline = time.monotonic() + _AUTOSTART_TIMEOUT
        while time.monotonic() < deadline:
            if healthy(config):
                return
            time.sleep(0.25)
    raise ServiceUnavailable(UNAVAILABLE_HINT)


class Client:
    """One configured connection to the service's base URL."""

    def __init__(self, config: Optional[dict] = None):
        self._config = _resolved(config)
        self._base = base_url(self._config)

    def get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        query = ""
        if params:
            filtered = {k: v for k, v in params.items() if v not in (None, "", [])}
            if filtered:
                query = "?" + urllib.parse.urlencode(filtered, doseq=True)
        return _request("GET", f"{self._base}/api/v1{path}{query}")

    def post(self, path: str, body: dict) -> Any:
        return _request("POST", f"{self._base}/api/v1{path}", body=body)


def connect(config: Optional[dict] = None) -> Client:
    """Ensure a service is reachable (auto-starting if permitted), then a client."""
    config = _resolved(config)
    ensure_service(config)
    return Client(config)
