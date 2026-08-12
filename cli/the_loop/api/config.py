"""The `service` block of the CLI config, with fail-closed defaults (issue-161).

Loopback-only unless the operator explicitly says ``exposed: true`` — the API
can spawn harness sessions with the operator's credentials, so the default
posture is "not a network service" (requirements §Security).

The ``cors`` sub-block (issue-211) answers a different question, and the two are
never substitutes: ``host``/``exposed`` decide **who may connect**, CORS decides
**which browser page may read the response**. It ships allowing exactly one
origin — the one the-loop publishes its own dashboard to — because a page served
from GitHub Pages cannot read a loopback service that sends no
``Access-Control-Allow-Origin``, and asking an operator to run a proxy in front
of their own loopback port to fix that is not a default worth defending
(decision-077). No CORS value can widen the bind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..state import layout_from_config

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4114

_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")

#: The origin the-loop's own dashboard is published to — an **origin** (scheme,
#: host, port), not a URL: the browser sends no path, so `/the-loop/ui/` here
#: would match nothing. Exact-string compared by Starlette, never a suffix.
DEFAULT_ALLOWED_ORIGINS = ("https://madarauchiha-314.github.io",)
#: Everything the dashboard sends, and nothing else.
DEFAULT_ALLOWED_METHODS = ("GET", "POST", "OPTIONS")
DEFAULT_ALLOWED_HEADERS = ("Accept", "Content-Type")


def service_config(cli_config: Optional[dict] = None) -> Dict[str, Any]:
    raw = ((cli_config or {}).get("service")) or {}
    return {
        "host": str(raw.get("host") or DEFAULT_HOST),
        "port": int(raw.get("port") or DEFAULT_PORT),
        "exposed": bool(raw.get("exposed", False)),
        "autoStart": bool(raw.get("autoStart", True)),
    }


def _as_list(value: Any, default: Sequence[str]) -> List[str]:
    """A list of strings, tolerating the hand-edit shapes YAML produces.

    An absent key takes the default; anything that is not a sequence becomes a
    one-entry list, because iterating a string would turn
    ``allowOrigins: https://x`` into one origin per character — permissive in
    exactly the direction that must not be guessed — and a bare number would
    raise where the caller expects a :class:`ValueError` it can report.
    """
    if value is None:
        return list(default)
    if not isinstance(value, (list, tuple, set)):
        return [str(value)]
    return [str(entry) for entry in value]


def cors_config(cli_config: Optional[dict] = None) -> Dict[str, Any]:
    """Resolve ``service.cors``, refusing the one combination that leaks.

    ``"*"`` with ``allowCredentials: true`` is not a permissive configuration,
    it is a broken one: browsers reject the pair outright, and any deployment
    that *did* honour it would hand every site on the internet an authenticated
    read of a service that spawns harness sessions. Raising here is what makes
    :func:`the_loop.api.serve.main` refuse to start (R3.1/R3.2) rather than
    quietly repair the operator's intent.
    """
    raw = (((cli_config or {}).get("service")) or {}).get("cors") or {}
    origins = _as_list(raw.get("allowOrigins"), DEFAULT_ALLOWED_ORIGINS)
    credentials = bool(raw.get("allowCredentials", False))
    if "*" in origins and credentials:
        raise ValueError(
            "service.cors: allowOrigins may not contain '*' while "
            "allowCredentials is true — name the origins that may read this "
            "service, or set allowCredentials: false"
        )
    return {
        "allowOrigins": origins,
        "allowMethods": _as_list(raw.get("allowMethods"), DEFAULT_ALLOWED_METHODS),
        "allowHeaders": _as_list(raw.get("allowHeaders"), DEFAULT_ALLOWED_HEADERS),
        "allowCredentials": credentials,
        "allowPrivateNetwork": bool(raw.get("allowPrivateNetwork", True)),
    }


def is_loopback(host: str) -> bool:
    return host in _LOOPBACK_HOSTS


def service_pidfile(cli_config: Optional[dict] = None) -> Path:
    return Path(layout_from_config(cli_config or {}).local_dir) / "service.pid"


def base_url(cli_config: Optional[dict] = None) -> str:
    conf = service_config(cli_config)
    return f"http://{conf['host']}:{conf['port']}"
