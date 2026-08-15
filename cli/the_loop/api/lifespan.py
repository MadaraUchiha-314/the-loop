"""What the control plane needs *running*, not merely importable (issue-212 D3).

Two things need a live process rather than an imported module: the MCP SDK's session
manager (it runs a task group for the process's duration — without it, the first POST to
``/mcp`` fails) and the hosted ingresses (issue-231: the poller and the webhook receiver
as threads inside this process).

:func:`create_app` used to compose both inline. They live here instead because Starlette
does **not** run a mounted sub-application's lifespan, so an embedder mounting the-loop
into their own app has to compose this themselves — and composing it means having a name
for it. The standalone service and :class:`the_loop.sdk.TheLoop` call the same function.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Optional


def build_lifespan(
    cli_config: Optional[dict],
    *,
    mcp_app: Any = None,
    host_ingresses: bool = False,
):
    """An async context manager holding the process-lifetime concerns open.

    ``mcp_app`` is the streamable-HTTP app whose session manager must run (``None`` when
    MCP is disabled); ``host_ingresses`` decides whether the enabled ingresses run in
    *this* process. Both are resolved by the caller, because both are boot-time choices
    the caller already had to make in order to build the app at all.

    The returned callable takes the application as its single argument, matching
    FastAPI's ``lifespan=`` contract, and ignores it — nothing here is per-app.
    """

    @asynccontextmanager
    async def lifespan(_app: Any = None):
        from . import ingress as ingress_mod

        hosted = (
            ingress_mod.start_hosted_ingresses(cli_config) if host_ingresses else []
        )
        try:
            if mcp_app is None:
                yield
            else:
                async with mcp_app.router.lifespan_context(mcp_app):
                    yield
        finally:
            ingress_mod.stop_hosted_ingresses(hosted)

    return lifespan
