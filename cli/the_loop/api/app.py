"""The control-plane FastAPI app: /api/v1 over :mod:`the_loop.core` (issue-161).

Routes add transport and serialization only (R1.2) — no in-app auth (the
deploying gateway owns it, decision-059). Cross-origin reads are a configured
allowlist (``service.cors``, issue-211): a browser page on a listed origin gets
``Access-Control-Allow-Origin``, everything else gets nothing and is discarded
by the browser. The list ships with one entry, the origin the-loop's own
dashboard is published to; an empty list installs no middleware at all and
restores the same-origin-only behaviour that predates it. Work-item refs
travel as query/body parameters, never path segments — a ref contains ``/``
and ``#``, and URL-encoding those into paths trades one escaping bug for
another. Error mapping is uniform: ``ValueError`` → 400 (caller mistake),
``LookupError`` → 404, ``SpliceError`` → 500 (a config edit that could not be
proven, and so was not written). Every /api/v1 operation lands in the event log
as ``api.request``; /health is exempt (it is the liveness probe the CLI's
auto-start loop hammers).

The app also **watches its own CLI config** (issue-222): ``/api/v1/config`` reads
and writes it, and :class:`_ConfigHolder` re-reads it whenever the file changes,
so a saved change is live on the next request instead of at the next restart —
the property the daemons have had since issue-63.
"""

from __future__ import annotations

import inspect
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from .. import eventlog
from ..cli_config import default_cli_config_path, load_cli_config
from ..core import attention as core_attention
from ..core import config as core_config
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import lifecycle as core_lifecycle
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import workitems as core_workitems
from ..reload import Reloader
from ..yamlpatch import SpliceError
from .config import cors_config

API_PREFIX = "/api/v1"

logger = logging.getLogger("the-loop.service")


def _install_cors(app: FastAPI, cli_config: Optional[dict]) -> None:
    """Add the CORS middleware, if any origin is allowed to read this service.

    Added **after** the audit middleware, which puts it outermost: Starlette
    wraps the most recently added middleware around everything before it. That
    ordering is the point — a preflight is answered by the middleware and never
    reaches a route, so it runs no operation and emits no ``api.request`` event.

    ``allow_private_network`` is newer than the package's ``fastapi>=0.110``
    floor, and it is what lets a public HTTPS page reach a loopback address in
    Chromium at all. Passing it only when the installed Starlette accepts it
    keeps that floor honest; writing the header ourselves instead would
    duplicate a security-relevant response header on every modern install.
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


class _ConfigHolder:
    """The CLI config the app serves *now*, kept level with the file (issue-222).

    The daemons have had this since issue-63: :class:`~the_loop.reload.Reloader`
    content-hashes the config path and rebuilds on change. The service did not — it closed
    over whatever ``create_app`` was handed — so a config edited through this very API
    left the service answering from the old one until somebody restarted it.

    Refresh is driven from the audit middleware, i.e. **once per request** rather than per
    read: one ``sha256`` of a ~10 KB file per API call, and no watcher thread. The rebuilt
    value replaces an attribute rather than mutating the dict in place, so a route already
    running in Starlette's threadpool keeps reading a consistent document. A file that
    becomes unparseable keeps the previous value — that is ``Reloader``'s documented
    behaviour, and it is the right one: somebody is mid-edit, not asking for defaults.
    """

    def __init__(self, initial: Optional[dict], path) -> None:
        self.path = path
        self.current: Dict[str, Any] = dict(initial or {})
        # Baselined to the file as it is now, so an unchanged file never rebuilds and an
        # app built from an explicit dict keeps serving that dict.
        self._reloader = Reloader(path, self._build)

    def _build(self) -> Dict[str, Any]:
        return load_cli_config(self.path, strict=True)

    def refresh(self) -> None:
        fresh = self._reloader.poll_for_change()
        if fresh is not None:
            self.current = fresh


class ConfigUpdateBody(BaseModel):
    # A **sparse** patch: only the keys that change. There is deliberately no `path`
    # field — the file this route may write is the one the process already reads
    # (requirements R1.4), so no request can name another.
    patch: Dict[str, Any]


class GraphCheckBody(BaseModel):
    repo: str
    workItem: str
    recompute: bool = False
    # A PR number selects that pull request's INNER loop (pdlc-pr-loop,
    # issue-172); None is the work item's outer pdlc-work-item-loop. prRepo
    # qualifies it by repository when the work item spans several (issue-183).
    pr: Optional[int] = None
    prRepo: str = ""


class GraphCompleteBody(BaseModel):
    repo: str
    workItem: str
    node: str = ""
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""


class GraphAdvanceBody(BaseModel):
    repo: str
    workItem: str
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""


class GraphForceBody(BaseModel):
    repo: str
    workItem: str
    toNode: str
    reason: str
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""


class GraphSkipBody(BaseModel):
    repo: str
    workItem: str
    nodes: List[str]
    reason: str
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""


class SessionControlBody(BaseModel):
    ref: str
    verb: str
    comment: bool = True


class SessionReplyBody(BaseModel):
    ref: str
    text: str
    # Recorded on the event and the ticket for the audit trail; never trusted
    # as authentication (decision-059: the gateway owns auth).
    actor: str = ""
    comment: bool = True


class SessionRegisterBody(BaseModel):
    ref: str
    harness: str
    harnessSessionId: str
    cwd: str = "."
    force: bool = False


class SessionCloseBody(BaseModel):
    ref: str
    keepTmux: Optional[bool] = None


class DaemonControlBody(BaseModel):
    daemon: str
    verb: str


class RestartBody(BaseModel):
    # One boolean, nothing else on the wire (issue-228 §Security): the spawned
    # process is a fixed argv, and the config path it receives is the one this
    # process already reads — no request can name another.
    withUpgrade: bool = False


class CriticRunBody(BaseModel):
    repo: str
    name: str
    prompt: str = ""
    promptFile: str = ""
    workItem: str = ""
    specDir: str = ""
    timeout: Optional[float] = None
    cwd: str = ""


def create_app(cli_config: Optional[dict] = None, *, config_path=None) -> FastAPI:
    """Build the app over the core facade.

    The service carries **no in-app authentication** (owner decision, PR #162):
    it is deployed behind a gateway that handles auth, and locally it binds
    loopback-only by default (the exposure guard in ``serve.py`` is the network
    boundary). Adding a token layer here would duplicate what the gateway owns.

    The official MCP SDK's streamable-HTTP app is mounted at ``/mcp``; its
    session manager needs its own lifespan running, so this app adopts it.

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
    holder = _ConfigHolder(cli_config, config_path or default_cli_config_path())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        # The SDK's session manager runs a task group for the duration of the
        # process; without adopting its lifespan, /mcp 500s on first use.
        if mcp_app is None:
            yield
        else:
            async with mcp_app.router.lifespan_context(mcp_app):
                yield

    app = FastAPI(
        title="the-loop control plane",
        version="1",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(LookupError)
    async def _lookup_error(request: Request, exc: LookupError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(SpliceError)
    async def _splice_error(request: Request, exc: SpliceError):
        # Not the caller's mistake and not a missing resource: the edit could not be
        # proven, so nothing was written. 500 with the reason, rather than a traceback.
        logger.error("config edit refused: %s", exc)
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.middleware("http")
    async def _audit(request: Request, call_next):
        holder.refresh()
        response = await call_next(request)
        path = request.url.path
        if path.startswith(API_PREFIX) and path != f"{API_PREFIX}/health":
            eventlog.emit(
                "api.request",
                method=request.method,
                path=path,
                status=response.status_code,
            )
        return response

    # Last, so it wraps the audit middleware rather than sitting inside it.
    _install_cors(app, cli_config)

    # The live config, reachable without closing over this function: it is what the
    # routes read, so a test (or a future route) can ask the app what it is running on.
    app.state.config_holder = holder

    @app.get(f"{API_PREFIX}/health", operation_id="health")
    def health() -> Dict[str, str]:
        from importlib.metadata import PackageNotFoundError, version

        try:
            v = version("the-loopy-one")
        except PackageNotFoundError:  # pragma: no cover — source checkout
            v = "unknown"
        return {"status": "ok", "version": v}

    @app.get(
        f"{API_PREFIX}/work-items",
        operation_id="listWorkItems",
    )
    def list_work_items() -> List[Dict[str, Any]]:
        return core_workitems.list_work_items(holder.current)

    @app.get(
        f"{API_PREFIX}/work-items/one",
        operation_id="getWorkItem",
    )
    def get_work_item(ref: str = Query(...)) -> Dict[str, Any]:
        return core_workitems.get_work_item(ref, holder.current)

    @app.get(f"{API_PREFIX}/config", operation_id="getConfig")
    def get_config() -> Dict[str, Any]:
        return core_config.get_config(holder.path)

    @app.get(f"{API_PREFIX}/config/schema", operation_id="getConfigSchema")
    def get_config_schema() -> Dict[str, Any]:
        return core_config.get_schema()

    @app.post(f"{API_PREFIX}/config", operation_id="updateConfig")
    def update_config(body: ConfigUpdateBody) -> Dict[str, Any]:
        # The holder picks the new file up on the *next* request through the middleware,
        # which is what makes a saved change live without a restart. The response's
        # `config` is the document just written, so this response never lags the file.
        return core_config.update_config(body.patch, holder.path)

    @app.get(f"{API_PREFIX}/graph", operation_id="graphShow")
    def graph_show(
        repo: str = Query(...),
        pr: Optional[int] = Query(None),
        prRepo: str = Query(""),
    ) -> Dict[str, Any]:
        return core_graphs.show(repo, pr=pr, pr_repo=prRepo)

    @app.post(
        f"{API_PREFIX}/graph/check",
        operation_id="graphCheck",
    )
    def graph_check(body: GraphCheckBody) -> Dict[str, Any]:
        return core_graphs.check(
            body.repo,
            body.workItem,
            recompute=body.recompute,
            pr=body.pr,
            pr_repo=body.prRepo,
        )

    @app.post(
        f"{API_PREFIX}/graph/complete",
        operation_id="graphComplete",
    )
    def graph_complete(body: GraphCompleteBody) -> Dict[str, Any]:
        return core_graphs.complete(
            body.repo,
            body.workItem,
            node=body.node,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
        )

    @app.post(
        f"{API_PREFIX}/graph/advance",
        operation_id="graphAdvance",
    )
    def graph_advance(body: GraphAdvanceBody) -> Dict[str, Any]:
        return core_graphs.advance(
            body.repo, body.workItem, ref=body.ref, pr=body.pr, pr_repo=body.prRepo
        )

    @app.post(
        f"{API_PREFIX}/graph/force",
        operation_id="graphForce",
    )
    def graph_force(body: GraphForceBody) -> Dict[str, Any]:
        return core_graphs.force(
            body.repo,
            body.workItem,
            body.toNode,
            body.reason,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
        )

    @app.post(
        f"{API_PREFIX}/graph/skip",
        operation_id="graphSkip",
    )
    def graph_skip(body: GraphSkipBody) -> Dict[str, Any]:
        return core_graphs.skip(
            body.repo,
            body.workItem,
            body.nodes,
            body.reason,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
        )

    @app.get(f"{API_PREFIX}/sessions", operation_id="listSessions")
    def list_sessions(status: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return core_sessions.list_sessions(status=status, config=holder.current)

    @app.get(
        f"{API_PREFIX}/sessions/one",
        operation_id="getSession",
    )
    def get_session(ref: str = Query(...)) -> Dict[str, Any]:
        return core_sessions.get_session(ref, config=holder.current)

    @app.get(
        f"{API_PREFIX}/sessions/transcript",
        operation_id="sessionTranscript",
    )
    def session_transcript(
        ref: str = Query(...), tail: int = Query(200, ge=0)
    ) -> Dict[str, Any]:
        return core_sessions.get_transcript(ref, tail=tail, config=holder.current)

    @app.post(
        f"{API_PREFIX}/sessions/control",
        operation_id="controlSession",
    )
    def control_session(body: SessionControlBody) -> Dict[str, Any]:
        return core_sessions.control_session(
            body.ref, body.verb, comment=body.comment, config=holder.current
        )

    @app.post(
        f"{API_PREFIX}/sessions/reply",
        operation_id="replySession",
    )
    def reply_session(body: SessionReplyBody) -> Dict[str, Any]:
        return core_sessions.reply_session(
            body.ref,
            body.text,
            actor=body.actor,
            comment=body.comment,
            config=holder.current,
        )

    @app.post(
        f"{API_PREFIX}/sessions/register",
        operation_id="registerSession",
    )
    def register_session(body: SessionRegisterBody) -> Dict[str, Any]:
        return core_sessions.register_session(
            body.ref,
            body.harness,
            body.harnessSessionId,
            cwd=body.cwd,
            force=body.force,
            config=holder.current,
        )

    @app.post(
        f"{API_PREFIX}/sessions/close",
        operation_id="closeSession",
    )
    def close_session(body: SessionCloseBody) -> Dict[str, Any]:
        return core_sessions.close_session(
            body.ref, keep_tmux=body.keepTmux, config=holder.current
        )

    @app.get(f"{API_PREFIX}/events", operation_id="queryEvents")
    def query_events(
        type: List[str] = Query(default=[]),
        workItem: Optional[str] = Query(None),
        deliveryId: Optional[str] = Query(None),
        source: Optional[str] = Query(None),
        level: Optional[str] = Query(None),
        since: Optional[str] = Query(None),
        limit: int = Query(50, ge=0),
    ) -> List[Dict[str, Any]]:
        return core_events.query_events(
            None,
            types=type,
            work_item=workItem,
            delivery_id=deliveryId,
            source=source,
            min_level=level,
            since=since,
            limit=limit,
        )

    @app.get(
        f"{API_PREFIX}/events/types",
        operation_id="eventTypes",
    )
    def event_types() -> Dict[str, str]:
        return core_events.event_types()

    @app.get(f"{API_PREFIX}/daemons", operation_id="listDaemons")
    def list_daemons() -> List[Dict[str, Any]]:
        return [
            core_daemons.daemon_status(name, holder.current)
            for name in core_daemons.DAEMONS
        ]

    @app.post(
        f"{API_PREFIX}/daemons/control",
        operation_id="controlDaemon",
    )
    def control_daemon(body: DaemonControlBody) -> Dict[str, Any]:
        return core_daemons.control_daemon(body.daemon, body.verb, holder.current)

    @app.post(f"{API_PREFIX}/restart", operation_id="restart")
    def restart(body: RestartBody) -> Dict[str, Any]:
        # Scheduling, not doing (issue-228, R4.4): this process is among what a
        # restart stops, so the work happens in a detached `the-loop restart`
        # that outlives it, and the response only promises the spawn.
        return core_lifecycle.schedule_restart(
            holder.current, with_upgrade=body.withUpgrade, config_path=holder.path
        )

    @app.get(
        f"{API_PREFIX}/attention",
        operation_id="listAttention",
    )
    def list_attention() -> List[Dict[str, Any]]:
        return core_attention.list_attention(holder.current)

    @app.get(
        f"{API_PREFIX}/repo/scenarios",
        operation_id="repoScenarios",
    )
    def repo_scenarios(
        repo: str = Query(...), glob: List[str] = Query(default=[])
    ) -> Dict[str, Any]:
        return core_repo.scenarios(repo, globs=glob)

    @app.get(
        f"{API_PREFIX}/repo/instructions",
        operation_id="repoInstructions",
    )
    def repo_instructions(repo: str = Query(...)) -> Dict[str, Any]:
        return core_repo.instructions(repo)

    @app.get(
        f"{API_PREFIX}/repo/critics",
        operation_id="repoCritics",
    )
    def repo_critics(repo: str = Query(...)) -> List[Dict[str, Any]]:
        return core_repo.critics(repo)

    @app.post(
        f"{API_PREFIX}/repo/critics/run",
        operation_id="repoCriticRun",
    )
    def repo_critic_run(body: CriticRunBody) -> Dict[str, Any]:
        return core_repo.critic_run(
            body.repo,
            body.name,
            body.prompt,
            body.promptFile,
            work_item=body.workItem,
            spec_dir=body.specDir,
            timeout=body.timeout,
            cwd=body.cwd,
        )

    # Mounted last, at the root, so the MCP app owns exactly ``/mcp`` and every
    # /api/v1 route above still wins. Mounting it *at* ``/mcp`` instead would
    # make the SDK's own path ``/mcp/`` and leave ``/mcp`` a 307 — a redirect
    # some MCP clients will not follow on a POST, so the URL an operator pastes
    # into Claude or Cursor would work in one client and not the next.
    if mcp_app is not None:
        app.mount("/", mcp_app)

    return app
