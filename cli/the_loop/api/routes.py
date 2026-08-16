"""The `/api/v1` surface as an :class:`~fastapi.APIRouter` (issue-161, issue-212).

This module owns **one** definition of the control plane's HTTP surface, and it has two
consumers: :func:`the_loop.api.app.create_app`, which wraps it in a standalone FastAPI
application, and :class:`the_loop.sdk.TheLoop`, which hands it to somebody else's
application. They cannot drift, because they are the same router (issue-212 R2.7).

Routes add transport and serialization only (R1.2) — no in-app auth (the deploying
gateway owns it, decision-059). Work-item refs travel as query/body parameters, never
path segments — a ref contains ``/`` and ``#``, and URL-encoding those into paths trades
one escaping bug for another.

**Everything per-request travels on the route class**, not on an application object
(issue-212 D2). A router carried into a host application keeps its `route_class`; it does
not keep middleware or exception handlers, because those belong to whichever app it was
attached to — and the SDK is forbidden from installing either on somebody else's app. So
:func:`build_router` builds a route class that, around every operation:

* re-reads the CLI config if the file changed, which is what makes a saved config live on
  the next request rather than at the next restart (issue-222);
* maps ``ValueError`` → 400 (caller mistake), ``LookupError`` → 404 and ``SpliceError``
  → 500 (a config edit that could not be proven, and so was not written);
* records the operation in the event log as ``api.request``. ``health`` is exempt — it is
  the liveness probe the CLI's auto-start loop hammers — and the exemption is keyed on the
  *operation id* rather than the path, so it survives being mounted under a prefix.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from .. import eventlog
from ..cli_config import ConfigHolder
from ..core import attention as core_attention
from ..core import config as core_config
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import lifecycle as core_lifecycle
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import workitems as core_workitems
from ..workitem import WorkItemRef
from ..yamlpatch import SpliceError
from . import stream as api_stream
from .config import stream_config

API_PREFIX = "/api/v1"

#: Operations that are not worth an event each. The liveness probe is hammered by the
#: CLI's auto-start loop and by whatever an embedder points at it.
_UNAUDITED_OPERATIONS = frozenset({"health"})

logger = logging.getLogger("the-loop.service")


__all__ = ["API_PREFIX", "ConfigHolder", "build_router"]


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


def _core_route_class(holder: ConfigHolder):
    """An :class:`APIRoute` carrying refresh, error translation and the audit event.

    Built per router so it can close over ``holder``. A route class is the only one of
    FastAPI's extension points that travels with ``include_router`` into an application
    the-loop does not own, which is what issue-212 R3.3 requires.
    """

    class CoreRoute(APIRoute):
        def get_route_handler(self):
            original = super().get_route_handler()
            operation_id = self.operation_id or ""

            async def handler(request: Request) -> Response:
                holder.refresh()
                try:
                    response = await original(request)
                # SpliceError first: it is a RuntimeError today, but ordering
                # narrowest-first means a future re-parenting cannot silently
                # reclassify a refused config write as a caller mistake.
                except SpliceError as exc:
                    # Not the caller's mistake and not a missing resource: the edit could
                    # not be proven, so nothing was written. 500 with the reason, rather
                    # than a traceback.
                    logger.error("config edit refused: %s", exc)
                    response = JSONResponse(
                        status_code=500, content={"detail": str(exc)}
                    )
                except LookupError as exc:
                    response = JSONResponse(
                        status_code=404, content={"detail": str(exc)}
                    )
                except ValueError as exc:
                    response = JSONResponse(
                        status_code=400, content={"detail": str(exc)}
                    )
                if operation_id not in _UNAUDITED_OPERATIONS:
                    eventlog.emit(
                        "api.request",
                        method=request.method,
                        path=request.url.path,
                        status=response.status_code,
                    )
                return response

            return handler

    return CoreRoute


def _build_broker(holder: ConfigHolder):
    """The stream's broker, pointed at this config's event log.

    The transcript resolver is injected rather than imported by the broker, so
    the path derivation stays in one place — ``core.sessions.transcript_path``,
    which owns the fail-closed rules issue-209 wrote — and the broker stays
    testable without a session registry.
    """
    from ..state import layout_from_config
    from .config import stream_config
    from .stream import StreamBroker

    conf = stream_config(holder.current)

    def resolve(ref: str):
        # LookupError is the *normal* answer for a work item whose session has
        # not registered a conversation yet, so it is not logged or raised: the
        # broker retries, and the watch starts when the session does.
        try:
            return core_sessions.transcript_path(ref, config=holder.current)
        except (LookupError, ValueError):
            return None

    return StreamBroker(
        layout_from_config(holder.current or {}).event_log,
        max_subscribers=conf["maxSubscribers"],
        transcript_path=resolve,
    )


def build_router(holder: ConfigHolder, **router_kwargs: Any) -> APIRouter:
    """Every ``/api/v1`` operation, as a router any FastAPI app can include.

    ``router_kwargs`` are passed to :class:`~fastapi.APIRouter` — an embedder uses
    ``dependencies=[Depends(...)]`` to put their own authorization in front of every
    operation (issue-212 R3.2). The ``/api/v1`` prefix stays *inside* the router: the
    API's version is the API's, and any namespace an embedder wants is theirs to add at
    ``include_router`` time.
    """
    router = APIRouter(route_class=_core_route_class(holder), **router_kwargs)

    # The stream's broker is owned by the ROUTER, not by the lifespan (issue-239).
    # The router is the only thing that travels into an embedder's application
    # (issue-212 R3.3) — a lifespan-owned broker would simply not exist for SDK
    # consumers, and the stream would 500 for them and nobody would know why. It
    # costs nothing to own it here: the tailer task starts with the first
    # subscriber and stops with the last, so a service nobody is watching runs no
    # task at all.
    stream_broker = _build_broker(holder)

    @router.get(f"{API_PREFIX}/health", operation_id="health")
    def health() -> Dict[str, str]:
        from importlib.metadata import PackageNotFoundError, version

        try:
            v = version("the-loopy-one")
        except PackageNotFoundError:  # pragma: no cover — source checkout
            v = "unknown"
        return {"status": "ok", "version": v}

    @router.get(
        f"{API_PREFIX}/work-items",
        operation_id="listWorkItems",
    )
    def list_work_items() -> List[Dict[str, Any]]:
        return core_workitems.list_work_items(holder.current)

    @router.get(
        f"{API_PREFIX}/work-items/one",
        operation_id="getWorkItem",
    )
    def get_work_item(ref: str = Query(...)) -> Dict[str, Any]:
        return core_workitems.get_work_item(ref, holder.current)

    @router.get(f"{API_PREFIX}/config", operation_id="getConfig")
    def get_config() -> Dict[str, Any]:
        return core_config.get_config(holder.path)

    @router.get(f"{API_PREFIX}/config/schema", operation_id="getConfigSchema")
    def get_config_schema() -> Dict[str, Any]:
        return core_config.get_schema()

    @router.post(f"{API_PREFIX}/config", operation_id="updateConfig")
    def update_config(body: ConfigUpdateBody) -> Dict[str, Any]:
        # The holder picks the new file up on the *next* request through the route class,
        # which is what makes a saved change live without a restart. The response's
        # `config` is the document just written, so this response never lags the file.
        return core_config.update_config(body.patch, holder.path)

    @router.get(f"{API_PREFIX}/graph", operation_id="graphShow")
    def graph_show(
        repo: str = Query(...),
        pr: Optional[int] = Query(None),
        prRepo: str = Query(""),
    ) -> Dict[str, Any]:
        return core_graphs.show(repo, pr=pr, pr_repo=prRepo)

    @router.post(
        f"{API_PREFIX}/graph/check",
        operation_id="graphCheck",
    )
    def graph_check(body: GraphCheckBody) -> Dict[str, Any]:
        """Where a work item stands, as `the-loop check` computes it.

        A `repo` that does not resolve to a directory is answered `200` with
        `repoResolved: false`, an empty `nodes` list and no `currentNode` — a
        checkout that has been cleaned up is expected state on the machine that
        cleaned it up, not caller error (issue-238). The field is **absent** on
        every other response. `4xx` stays reserved for a malformed request; the
        mutating graph verbs still refuse a repository that is not there.
        """
        return core_graphs.check(
            body.repo,
            body.workItem,
            recompute=body.recompute,
            pr=body.pr,
            pr_repo=body.prRepo,
        )

    @router.post(
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

    @router.post(
        f"{API_PREFIX}/graph/advance",
        operation_id="graphAdvance",
    )
    def graph_advance(body: GraphAdvanceBody) -> Dict[str, Any]:
        return core_graphs.advance(
            body.repo, body.workItem, ref=body.ref, pr=body.pr, pr_repo=body.prRepo
        )

    @router.post(
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

    @router.post(
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

    @router.get(f"{API_PREFIX}/sessions", operation_id="listSessions")
    def list_sessions(status: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return core_sessions.list_sessions(status=status, config=holder.current)

    @router.get(
        f"{API_PREFIX}/sessions/one",
        operation_id="getSession",
    )
    def get_session(ref: str = Query(...)) -> Dict[str, Any]:
        return core_sessions.get_session(ref, config=holder.current)

    @router.get(
        f"{API_PREFIX}/sessions/transcript",
        operation_id="sessionTranscript",
    )
    def session_transcript(
        ref: str = Query(...), tail: int = Query(200, ge=0)
    ) -> Dict[str, Any]:
        return core_sessions.get_transcript(ref, tail=tail, config=holder.current)

    @router.post(
        f"{API_PREFIX}/sessions/control",
        operation_id="controlSession",
    )
    def control_session(body: SessionControlBody) -> Dict[str, Any]:
        return core_sessions.control_session(
            body.ref, body.verb, comment=body.comment, config=holder.current
        )

    @router.post(
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

    @router.post(
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

    @router.post(
        f"{API_PREFIX}/sessions/close",
        operation_id="closeSession",
    )
    def close_session(body: SessionCloseBody) -> Dict[str, Any]:
        return core_sessions.close_session(
            body.ref, keep_tmux=body.keepTmux, config=holder.current
        )

    # The response is declared rather than inferred: FastAPI would derive
    # `application/json` from the return annotation, and the contract this repo
    # publishes would then describe a media type this route never sends
    # (`apiSpecs`, contract-first). The frame shapes live here because they are
    # the wire contract — a client parses `event:` and this `data:`.
    @router.get(
        f"{API_PREFIX}/stream",
        operation_id="streamEvents",
        responses={
            200: {
                "description": (
                    "An open Server-Sent Events stream. Each frame is one of "
                    "`log` (an event-log record, with its byte offset as the SSE "
                    "`id` — quote it back as `Last-Event-ID` to resume), "
                    "`transcript` (a watched session's transcript grew), or "
                    "`desync` (the cursor could not be honoured; refetch "
                    "everything). Interleaved with `: keep-alive` comments. "
                    "`api.request` and `mcp.call` are never carried."
                ),
                "content": {
                    "text/event-stream": {
                        "schema": {
                            "type": "string",
                            "title": "SSE frames",
                            "example": (
                                "id: 148213\n"
                                "event: log\n"
                                'data: {"ts":"2026-08-16T16:35:48.114Z",'
                                '"event":"graph.advanced",'
                                '"work_item":"github:octo/repo#7"}\n\n'
                            ),
                        }
                    }
                },
            },
            400: {"description": "Malformed Last-Event-ID, workItem or transcript."},
            404: {"description": "service.stream.enabled is false."},
            503: {
                "description": (
                    "service.stream.maxSubscribers connections are already open. "
                    "Carries Retry-After."
                )
            },
        },
    )
    async def stream_events(
        request: Request,
        workItem: List[str] = Query(default=[]),
        transcript: List[str] = Query(default=[]),
        last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
    ) -> Response:
        """Hold a connection open and push control-plane change to it (issue-239).

        **`async def`, not `def`.** Every other route here is synchronous and runs
        in the anyio threadpool; a synchronous generator held open for hours would
        hold one of its 40 slots for hours, and `maxSubscribers` of them would take
        a fifth of the pool away from the CLI and `/mcp`. As a coroutine this costs
        one task and no thread, which is what makes R5.1 true rather than hoped for.

        Everything that can refuse the connection is decided **before** the
        response begins — capacity, filter, cursor — so a refusal is an ordinary
        JSON error the client can read, and costs the service one rejected request
        rather than a task, a queue and a file handle.
        """
        conf = stream_config(holder.current)
        if not conf["enabled"]:
            eventlog.emit("stream.refused", reason="disabled")
            return JSONResponse(
                status_code=404,
                content={
                    "detail": "this service does not serve /api/v1/stream "
                    "(service.stream.enabled is false)"
                },
            )

        # Validate the filter before accepting. Failing OPEN here would turn a
        # typo into a subscription to every work item on the workstation, so a
        # ref that will not parse is the caller's error, not a wider stream.
        for ref in list(workItem) + list(transcript):
            try:
                WorkItemRef.parse(ref)
            except ValueError as exc:
                eventlog.emit("stream.refused", reason="bad-filter", detail=str(exc))
                return JSONResponse(status_code=400, content={"detail": str(exc)})

        try:
            cursor = api_stream.parse_cursor(last_event_id)
        except ValueError as exc:
            eventlog.emit("stream.refused", reason="bad-cursor")
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        broker = stream_broker
        broker.max_subscribers = conf["maxSubscribers"]
        try:
            subscriber = broker.subscribe(work_items=workItem, transcripts=transcript)
        except RuntimeError as exc:
            eventlog.emit(
                "stream.refused", reason="at-capacity", subscribers=broker.count
            )
            return JSONResponse(
                status_code=503,
                content={"detail": str(exc)},
                headers={"Retry-After": "5"},
            )

        eventlog.emit(
            "stream.subscribed",
            subscribers=broker.count,
            work_items=list(workItem) or None,
            transcripts=list(transcript) or None,
            cursor=cursor,
        )
        return StreamingResponse(
            api_stream.serve(
                broker,
                subscriber,
                cursor=cursor,
                keep_alive=conf["keepAliveSeconds"],
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                # Without this an nginx in front buffers the whole response and
                # the feature silently becomes a very slow poll.
                "X-Accel-Buffering": "no",
            },
        )

    @router.get(f"{API_PREFIX}/events", operation_id="queryEvents")
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

    @router.get(
        f"{API_PREFIX}/events/types",
        operation_id="eventTypes",
    )
    def event_types() -> Dict[str, str]:
        return core_events.event_types()

    @router.get(f"{API_PREFIX}/daemons", operation_id="listDaemons")
    def list_daemons() -> List[Dict[str, Any]]:
        return [
            core_daemons.daemon_status(name, holder.current)
            for name in core_daemons.DAEMONS
        ]

    @router.post(
        f"{API_PREFIX}/daemons/control",
        operation_id="controlDaemon",
    )
    def control_daemon(body: DaemonControlBody) -> Dict[str, Any]:
        return core_daemons.control_daemon(body.daemon, body.verb, holder.current)

    @router.post(f"{API_PREFIX}/restart", operation_id="restart")
    def restart(body: RestartBody) -> Dict[str, Any]:
        # Scheduling, not doing (issue-228, R4.4): this process is among what a
        # restart stops, so the work happens in a detached `the-loop restart`
        # that outlives it, and the response only promises the spawn.
        return core_lifecycle.schedule_restart(
            holder.current, with_upgrade=body.withUpgrade, config_path=holder.path
        )

    @router.get(
        f"{API_PREFIX}/attention",
        operation_id="listAttention",
    )
    def list_attention() -> List[Dict[str, Any]]:
        return core_attention.list_attention(holder.current)

    @router.get(
        f"{API_PREFIX}/repo/scenarios",
        operation_id="repoScenarios",
    )
    def repo_scenarios(
        repo: str = Query(...), glob: List[str] = Query(default=[])
    ) -> Dict[str, Any]:
        return core_repo.scenarios(repo, globs=glob)

    @router.get(
        f"{API_PREFIX}/repo/instructions",
        operation_id="repoInstructions",
    )
    def repo_instructions(repo: str = Query(...)) -> Dict[str, Any]:
        return core_repo.instructions(repo)

    @router.get(
        f"{API_PREFIX}/repo/critics",
        operation_id="repoCritics",
    )
    def repo_critics(repo: str = Query(...)) -> List[Dict[str, Any]]:
        return core_repo.critics(repo)

    @router.post(
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

    return router
