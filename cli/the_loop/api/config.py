"""The `service` block of the CLI config, with fail-closed defaults (issue-161).

Loopback-only unless the operator explicitly says ``exposed: true`` — the API
can spawn harness sessions with the operator's credentials, so the default
posture is "not a network service" (requirements §Security).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from ..state import layout_from_config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4114

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def service_config(cli_config: Optional[dict] = None) -> Dict[str, Any]:
    raw = ((cli_config or {}).get("service")) or {}
    return {
        "host": str(raw.get("host") or DEFAULT_HOST),
        "port": int(raw.get("port") or DEFAULT_PORT),
        "exposed": bool(raw.get("exposed", False)),
        "autoStart": bool(raw.get("autoStart", True)),
    }


def is_loopback(host: str) -> bool:
    return host in _LOOPBACK_HOSTS


def service_pidfile(cli_config: Optional[dict] = None) -> Path:
    return Path(layout_from_config(cli_config or {}).local_dir) / "service.pid"


def base_url(cli_config: Optional[dict] = None) -> str:
    conf = service_config(cli_config)
    return f"http://{conf['host']}:{conf['port']}"
