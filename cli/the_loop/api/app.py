"""The standalone control-plane FastAPI app: /api/v1 over :mod:`the_loop.core` (issue-161).

This module is the **application**; the surface it serves lives in :mod:`.routes` and its
process-lifetime concerns in :mod:`.lifespan`, because :class:`the_loop.sdk.TheLoop`
serves the same surface inside somebody else's application (issue-212). What is left here
is what only an application can have: a title and doc URLs, the CORS middleware, the MCP
mount and the lifespan wiring.

Cross-origin reads are a configured allowlist (``service.cors``, issue-211): a browser
page on a listed origin gets ``Access-Control-Allow-Origin``, everything else gets nothing
and is discarded by the browser. The list ships with one entry, the origin the-loop's own
dashboard is published to; an empty list installs no middleware at all and restores the
same-origin-only behaviour that predates it. CORS is deliberately **not** part of the
router: it is an application-wide policy, and applying one the-loop config key to every
route of an app the-loop does not own is precisely what issue-212 R3.5 forbids.

The app also **watches its own CLI config** (issue-222): ``/api/v1/config`` reads and
writes it, and :class:`~the_loop.api.routes.ConfigHolder` re-reads it whenever the file
changes, so a saved change is live on the next request instead of at the next restart —
the property the daemons have had since issue-63.
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from ..cli_config import default_cli_config_path
from .config import cors_config
from .lifespan import build_lifespan
from .routes import API_PREFIX, ConfigHolder, build_router

__all__ = ["API_PREFIX", "create_app"]

logger = logging.getLogger("the-loop.service")


def _install_cors(app: FastAPI, cli_config: Optional[dict]) -> None:
    """Add the CORS middleware, if any origin is allowed to read this service.

    ``allow_private_network`` is newer than the package's ``fastapi>=0.110`` floor, and it
    is what lets a public HTTPS page reach a loopback address in Chromium at all. Passing
    it only when the installed Starlette accepts it keeps that floor honest; writing the
    header ourselves instead would duplicate a security-relevant response header on every
    modern install.
    """
    conf = cors_config(cli_config)
    if not conf["allowOrigins"]:
        return
    # An origin is scheme + host + port. A pasted URL — trailing slash, path —
    # is not wrong enough to refuse, and matches nothing at all; say so once,
    # here, rather than let it read as "CORS is broken".
    pathful = [o for o in conf["allowOrigins"] if o != "*" and o.count("/") != 2]
    if pathful:
        logger.warning(
            "service.cors.allowOrigins entries are origins, not URLs — %s "
            "carry a path or trailing slash and will match no browser request",
            ", ".join(pathful),
        )
    kwargs: Dict[str, Any] = {
        "allow_origins": conf["allowOrigins"],
        "allow_methods": conf["allowMethods"],
        "allow_headers": conf["allowHeaders"],
        "allow_credentials": conf["allowCredentials"],
    }
    parameters = inspect.signature(CORSMiddleware.__init__).parameters
    if "allow_private_network" in parameters:
        kwargs["allow_private_network"] = conf["allowPrivateNetwork"]
    elif conf["allowPrivateNetwork"]:
        logger.warning(
            "installed starlette has no allow_private_network; a public-origin "
            "page reaching this loopback service may be blocked by the browser "
            "— upgrade starlette, or set service.cors.allowPrivateNetwork: false "
            "to silence this"
        )
    app.add_middleware(CORSMiddleware, **kwargs)


def create_app(cli_config: Optional[dict] = None, *, config_path=None) -> FastAPI:
    """Build the standalone app over the core facade.

    The service carries **no in-app authentication** (owner decision, PR #162): it is
    deployed behind a gateway that handles auth, and locally it binds loopback-only by
    default (the exposure guard in ``serve.py`` is the network boundary). Adding a token
    layer here would duplicate what the gateway owns.

    The official MCP SDK's streamable-HTTP app is mounted at ``/mcp``; its session manager
    needs its own lifespan running, so this app adopts it.

    ``config_path`` names the CLI config this app reads, writes and watches; it defaults
    to the same resolution every other the-loop process uses. Boot-time consumers — the
    CORS middleware here, the bind in ``serve.py``, the MCP transport guard — keep the
    config they were built with, which is what ``core.config``'s ``restartRequired``
    reports back to whoever saved a change to one of them."""
    from .config import service_config

    # The MCP layer is mounted only when `service.mcp.enabled` says so
    # (issue-228, decision-084): a REST-only deployment gets no /mcp route at
    # all (404), no SDK session manager, and a no-op lifespan. Resolved at
    # boot, like the bind and CORS — `restartRequired` covers a change to it.
    mcp_app = None
    if service_config(cli_config)["mcpEnabled"]:
        from .mcp import build_app as build_mcp_app

        mcp_app = build_mcp_app(cli_config)
    holder = ConfigHolder(cli_config, config_path or default_cli_config_path())

    # issue-231 (`service.hostIngresses`, default true): the one process this
    # app runs in also hosts the enabled ingresses — the poller and the webhook
    # receiver — as background threads for the lifespan's duration. The run
    # loops are the daemons' own; each still holds its per-ingress pidfile
    # lock (now under this pid), so `the-loop status`/`stop` and the daemons
    # API keep answering from the same truth. A hosted ingress that cannot
    # start degrades to a logged warning; the API keeps serving.
    host_ingresses = service_config(cli_config)["hostIngresses"]

    app = FastAPI(
        title="the-loop control plane",
        version="1",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=build_lifespan(
            cli_config, mcp_app=mcp_app, host_ingresses=host_ingresses
        ),
    )

    # Error mapping, the config refresh and the `api.request` audit ride on the router's
    # route class (issue-212 D2), so they apply here and equally to an embedded mount.
    app.include_router(build_router(holder))

    _install_cors(app, cli_config)

    # The live config, reachable without closing over this function: it is what the
    # routes read, so a test (or a future route) can ask the app what it is running on.
    app.state.config_holder = holder

    # Mounted last, at the root, so the MCP app owns exactly ``/mcp`` and every
    # /api/v1 route above still wins. Mounting it *at* ``/mcp`` instead would
    # make the SDK's own path ``/mcp/`` and leave ``/mcp`` a 307 — a redirect
    # some MCP clients will not follow on a POST, so the URL an operator pastes
    # into Claude or Cursor would work in one client and not the next.
    if mcp_app is not None:
        app.mount("/", mcp_app)

    return app
