"""What the control plane needs *running*, not merely importable (issue-212 D3).

Three things need a live process rather than an imported module: the MCP SDK's session
manager (it runs a task group for the process's duration — without it, the first POST to
``/mcp`` fails), the hosted ingresses (issue-231: the poller and the webhook receiver
as threads inside this process) and the watcher (one thread that notices an
idle session, whichever ingresses are hosted).

:func:`create_app` used to compose both inline. They live here instead because Starlette
does **not** run a mounted sub-application's lifespan, so an embedder mounting the-loop
into their own app has to compose this themselves — and composing it means having a name
for it. The standalone service and :class:`the_loop.sdk.TheLoop` call the same function.
"""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional, Union

#: How long shutdown waits for a watcher's cycle in flight. The thread is a
#: daemon thread: one that is still pasting does not hold the process up.
_WATCHER_JOIN_SECONDS = 5.0


def build_lifespan(
    cli_config: Optional[dict],
    *,
    mcp_app: Any = None,
    host_ingresses: bool = False,
    config_path: Optional[Union[str, Path]] = None,
):
    """An async context manager holding the process-lifetime concerns open.

    ``mcp_app`` is the streamable-HTTP app whose session manager must run (``None`` when
    MCP is disabled); ``host_ingresses`` decides whether the enabled ingresses run in
    *this* process. Both are resolved by the caller, because both are boot-time choices
    the caller already had to make in order to build the app at all. ``config_path`` is
    the file the hosted set follows (issue-395): edited so that an ingress is no longer
    enabled, that ingress is stopped without a restart; newly enabled, it is started.
    It defaults to the path every other the-loop process resolves.

    The returned callable takes the application as its single argument, matching
    FastAPI's ``lifespan=`` contract, and ignores it — nothing here is per-app.
    """

    @asynccontextmanager
    async def lifespan(_app: Any = None):
        from ..cli_config import ConfigHolder, default_cli_config_path
        from ..core import watchdog
        from . import ingress as ingress_mod

        # The watcher runs with the service, not with an
        # ingress: every deployment has this process, whichever ingresses it
        # hosts, and an instance that only runs the gateway client hosts none.
        # `None` when this process already runs one; then it is not ours to stop.
        watching = threading.Event()
        # A holder of the watcher's own, refreshed on its thread once a tick:
        # the routes refresh theirs per request, on other threads.
        holder = ConfigHolder(
            cli_config,
            config_path if config_path is not None else default_cli_config_path(),
        )

        def config_now() -> dict:
            holder.refresh()
            return holder.current

        watcher = watchdog.start_watcher(config_now, watching)
        hosted: Optional[ingress_mod.HostedIngresses] = None
        if host_ingresses:
            hosted = ingress_mod.HostedIngresses(
                cli_config,
                config_path if config_path is not None else default_cli_config_path(),
            )
            hosted.start()
        try:
            if mcp_app is None:
                yield
            else:
                async with mcp_app.router.lifespan_context(mcp_app):
                    yield
        finally:
            watching.set()
            if watcher is not None:
                watcher.join(_WATCHER_JOIN_SECONDS)
            if hosted is not None:
                hosted.stop()

    return lifespan
