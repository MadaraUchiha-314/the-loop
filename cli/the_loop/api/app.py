"""The control-plane FastAPI app: /api/v1 over :mod:`the_loop.core` (issue-161).

Routes add transport and serialization only (R1.2) — no in-app auth (the
deploying gateway owns it, decision-059) and no CORS headers (no browser client
ships; the same-origin default denies cross-origin access). Work-item refs
travel as query/body parameters, never path segments — a ref contains ``/``
and ``#``, and URL-encoding those into paths trades one escaping bug for
another. Error mapping is uniform: ``ValueError`` → 400 (caller mistake),
``LookupError`` → 404. Every /api/v1 operation lands in the event log as
``api.request``; /health is exempt (it is the liveness probe the CLI's
auto-start loop hammers).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .. import eventlog
from ..core import attention as core_attention
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import workitems as core_workitems

API_PREFIX = "/api/v1"


class GraphCheckBody(BaseModel):
    repo: str
    workItem: str
    recompute: bool = False


class GraphCompleteBody(BaseModel):
    repo: str
    workItem: str
    node: str = ""
    actor: str = ""


class GraphAdvanceBody(BaseModel):
    repo: str
    workItem: str


class GraphForceBody(BaseModel):
    repo: str
    workItem: str
    toNode: str
    reason: str
    actor: str = ""


class SessionControlBody(BaseModel):
    ref: str
    verb: str
    comment: bool = True


class DaemonControlBody(BaseModel):
    daemon: str
    verb: str


class CriticRunBody(BaseModel):
    repo: str
    name: str
    prompt: str = ""
    promptFile: str = ""
    workItem: str = ""
    specDir: str = ""
    timeout: Optional[float] = None


def create_app(cli_config: Optional[dict] = None) -> FastAPI:
    """Build the app over the core facade.

    The service carries **no in-app authentication** (owner decision, PR #162):
    it is deployed behind a gateway that handles auth, and locally it binds
    loopback-only by default (the exposure guard in ``serve.py`` is the network
    boundary). Adding a token layer here would duplicate what the gateway owns."""
    app = FastAPI(
        title="the-loop control plane",
        version="1",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(LookupError)
    async def _lookup_error(request: Request, exc: LookupError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.middleware("http")
    async def _audit(request: Request, call_next):
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
        return core_workitems.list_work_items(cli_config)

    @app.get(
        f"{API_PREFIX}/work-items/one",
        operation_id="getWorkItem",
    )
    def get_work_item(ref: str = Query(...)) -> Dict[str, Any]:
        return core_workitems.get_work_item(ref, cli_config)

    @app.post(
        f"{API_PREFIX}/graph/check",
        operation_id="graphCheck",
    )
    def graph_check(body: GraphCheckBody) -> Dict[str, Any]:
        return core_graphs.check(body.repo, body.workItem, recompute=body.recompute)

    @app.post(
        f"{API_PREFIX}/graph/complete",
        operation_id="graphComplete",
    )
    def graph_complete(body: GraphCompleteBody) -> Dict[str, Any]:
        return core_graphs.complete(
            body.repo, body.workItem, node=body.node, actor=body.actor
        )

    @app.post(
        f"{API_PREFIX}/graph/advance",
        operation_id="graphAdvance",
    )
    def graph_advance(body: GraphAdvanceBody) -> Dict[str, Any]:
        return core_graphs.advance(body.repo, body.workItem)

    @app.post(
        f"{API_PREFIX}/graph/force",
        operation_id="graphForce",
    )
    def graph_force(body: GraphForceBody) -> Dict[str, Any]:
        return core_graphs.force(
            body.repo, body.workItem, body.toNode, body.reason, actor=body.actor
        )

    @app.get(f"{API_PREFIX}/sessions", operation_id="listSessions")
    def list_sessions(status: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return core_sessions.list_sessions(status=status, config=cli_config)

    @app.get(
        f"{API_PREFIX}/sessions/one",
        operation_id="getSession",
    )
    def get_session(ref: str = Query(...)) -> Dict[str, Any]:
        return core_sessions.get_session(ref, config=cli_config)

    @app.post(
        f"{API_PREFIX}/sessions/control",
        operation_id="controlSession",
    )
    def control_session(body: SessionControlBody) -> Dict[str, Any]:
        return core_sessions.control_session(
            body.ref, body.verb, comment=body.comment, config=cli_config
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
            core_daemons.daemon_status(name, cli_config)
            for name in core_daemons.DAEMONS
        ]

    @app.post(
        f"{API_PREFIX}/daemons/control",
        operation_id="controlDaemon",
    )
    def control_daemon(body: DaemonControlBody) -> Dict[str, Any]:
        return core_daemons.control_daemon(body.daemon, body.verb, cli_config)

    @app.get(
        f"{API_PREFIX}/attention",
        operation_id="listAttention",
    )
    def list_attention() -> List[Dict[str, Any]]:
        return core_attention.list_attention(cli_config)

    @app.get(
        f"{API_PREFIX}/repo/scenarios",
        operation_id="repoScenarios",
    )
    def repo_scenarios(repo: str = Query(...)) -> List[Dict[str, Any]]:
        return core_repo.scenarios(repo)

    @app.get(
        f"{API_PREFIX}/repo/instructions",
        operation_id="repoInstructions",
    )
    def repo_instructions(repo: str = Query(...)) -> List[Dict[str, Any]]:
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
        )

    from .mcp import add_mcp

    add_mcp(app, cli_config)

    return app
