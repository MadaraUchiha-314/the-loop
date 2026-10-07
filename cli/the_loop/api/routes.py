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

**The routes call a facade, not ``the_loop.core``** (issue-374, decision-138 D3). A
worker's is :class:`~the_loop.api.facade.CoreFacade`; a manager's, which serves the same
surface over its own state plus the registered instances', is
:class:`the_loop.manager.facade.ManagerFacade`. Every keyed operation carries an optional
``instance`` (R2.6) — a query parameter on a ``GET``, a body field on a ``POST`` — that
a worker accepts only as its own name; two more mappings, ``Conflict`` → 409 and
``MemberUnavailable`` → 502, are the manager's outcomes; and a list read that could not
reach every member names them in ``The-Loop-Instances-Unreachable`` (R2.9).
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
from ..core.github_ops import DEFAULT_LOG_LINES
from ..workitem import WorkItemRef
from ..yamlpatch import SpliceError
from . import stream as api_stream
from .config import stream_config
from .errors import Conflict, MemberUnavailable
from .facade import LEFT_OUT, PARTIAL_HEADER, TARGET, CoreFacade

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
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphCheckBody(BaseModel):
    repo: str
    workItem: str
    recompute: bool = False
    # A PR number selects that pull request's INNER loop (pdlc-pr-loop,
    # issue-172); None is the work item's outer pdlc-work-item-loop. prRepo
    # qualifies it by repository when the work item spans several (issue-183).
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphCompleteBody(BaseModel):
    repo: str
    workItem: str
    node: str = ""
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphAdvanceBody(BaseModel):
    repo: str
    workItem: str
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphForceBody(BaseModel):
    repo: str
    workItem: str
    toNode: str
    reason: str
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphSkipBody(BaseModel):
    repo: str
    workItem: str
    nodes: List[str]
    reason: str
    actor: str = ""
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class GraphReposBody(BaseModel):
    repo: str
    workItem: str
    repositories: Optional[List[str]] = None
    clear: bool = False
    ref: str = ""
    pr: Optional[int] = None
    prRepo: str = ""
    specDir: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class SessionControlBody(BaseModel):
    ref: str
    verb: str
    comment: bool = True
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class SessionReplyBody(BaseModel):
    ref: str
    text: str
    # Recorded on the event and the ticket for the audit trail; never trusted
    # as authentication (decision-059: the gateway owns auth).
    actor: str = ""
    comment: bool = True
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class StandingControlBody(BaseModel):
    # A standing session is addressed by NAME, never by a work-item ref
    # (issue-277): the two namespaces are separate so no event can cross between
    # them. An empty name means "every declared session" for start, and "every
    # recorded one" for stop; `restart` requires one.
    name: str = ""
    verb: str
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class StandingSayBody(BaseModel):
    name: str
    text: str
    # Recorded on the event for the audit trail; never trusted as
    # authentication (decision-059: the gateway owns auth).
    actor: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class StandingCreateBody(BaseModel):
    # The whole definition, so a session can exist without a config edit
    # (issue-277 R6). Every field but `name` falls back to the `routing`
    # defaults a declared entry would inherit.
    name: str
    harness: str = ""
    cwd: str = ""
    prompt: str = ""
    description: str = ""
    # None (absent) inherits the harness's launch arguments — harnesses[].args,
    # else the deprecated routing.harnessArgs.<harness> (issue-377); [] means none.
    harnessArgs: Optional[List[str]] = None
    slackEnabled: bool = False
    slackChannel: str = ""
    autoStart: bool = True
    start: bool = True
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class StandingDeleteBody(BaseModel):
    name: str
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class SessionRegisterBody(BaseModel):
    ref: str
    harness: str
    harnessSessionId: str
    cwd: str = "."
    force: bool = False
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class SessionLinkPrBody(BaseModel):
    ref: str
    pullRequest: str = ""
    # issue-447: ask GitHub for the open pull requests whose head is `branch`
    # in `repository` (the work item's when empty) instead of naming one.
    discover: bool = False
    branch: str = ""
    repository: str = ""
    # A fork's owner, when the head branch is not in `repository`'s namespace.
    headOwner: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


# -- the harness's GitHub verbs (issue-447) ------------------------------------
# Work-item and pull-request scoped, never a generic GitHub proxy: the contract
# says what the agent may do, and the merge gate stays reachable.


class WorkItemCommentBody(BaseModel):
    ref: str
    body: str
    instance: str = ""


class TicketCreateBody(BaseModel):
    # Exactly one of the two (issue-475): a GitHub issue, or a Jira ticket.
    repository: str = ""
    project: str = ""
    title: str
    body: str = ""
    labels: List[str] = []
    instance: str = ""


class PullRequestCreateBody(BaseModel):
    ref: str
    title: str
    body: str = ""
    head: str
    base: str = ""
    repository: str = ""
    draft: bool = False
    instance: str = ""


class TicketCloseBody(BaseModel):
    ref: str
    reason: str = "completed"
    workItem: str = ""
    instance: str = ""


class ThreadResolveBody(BaseModel):
    ref: str
    thread: str
    workItem: str = ""
    instance: str = ""


class PullRequestReadyBody(BaseModel):
    ref: str
    workItem: str = ""
    instance: str = ""


class PullRequestMergeBody(BaseModel):
    ref: str
    workItem: str = ""
    method: str = "merge"
    # The head the caller reviewed; GitHub refuses the merge if it moved.
    sha: str = ""
    instance: str = ""


class SessionCloseBody(BaseModel):
    ref: str
    keepTmux: Optional[bool] = None
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class DaemonControlBody(BaseModel):
    daemon: str
    verb: str
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class RestartBody(BaseModel):
    # One boolean, nothing else on the wire (issue-228 §Security): the spawned
    # process is a fixed argv, and the config path it receives is the one this
    # process already reads — no request can name another.
    withUpgrade: bool = False
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


class InstanceRegisterBody(BaseModel):
    # The registry entry (issue-374 R4): the member's own name and its address as
    # this manager reaches it. Validated by core exactly as the config reader does.
    name: str
    url: str


class InstanceUnregisterBody(BaseModel):
    name: str


class CriticRunBody(BaseModel):
    repo: str
    name: str
    prompt: str = ""
    promptFile: str = ""
    workItem: str = ""
    specDir: str = ""
    timeout: Optional[float] = None
    cwd: str = ""
    # Which instance this is for (issue-374 R2.6): empty means this one.
    instance: str = ""


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
                token = LEFT_OUT.set([])
                target_token = TARGET.set([])
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
                except Conflict as exc:
                    # Two instances answer for one key (issue-374 R2.4): refused,
                    # never resolved by picking one; the candidates are named so the
                    # caller can pick with `instance`.
                    response = JSONResponse(
                        status_code=409,
                        content={
                            "detail": str(exc),
                            "candidates": list(exc.candidates),
                        },
                    )
                except MemberUnavailable as exc:
                    # A registered instance did not answer a keyed operation (R2.9):
                    # 502 with the reason, never an empty 200.
                    response = JSONResponse(
                        status_code=502,
                        content={"detail": str(exc), "instance": exc.instance},
                    )
                except LookupError as exc:
                    response = JSONResponse(
                        status_code=404, content={"detail": str(exc)}
                    )
                except ValueError as exc:
                    response = JSONResponse(
                        status_code=400, content={"detail": str(exc)}
                    )
                finally:
                    left_out = list(LEFT_OUT.get() or [])
                    targets = list(TARGET.get() or [])
                    LEFT_OUT.reset(token)
                    TARGET.reset(target_token)
                if left_out:
                    # The members a list read could not include (R2.9): a bare array
                    # cannot carry the fact, so the header does.
                    response.headers[PARTIAL_HEADER] = ", ".join(left_out)
                if operation_id not in _UNAUDITED_OPERATIONS:
                    # Debug level (issue-283 B7): a dashboard polling every 15s
                    # emits ~25 of these per cycle, and at info they push the
                    # events an operator actually reads (gates, dispatches,
                    # poll errors) out of every default window — the UI's own
                    # reads become ~100% of the log it renders. The audit trail
                    # is intact; a debug-level query still returns them.
                    eventlog.emit(
                        "api.request",
                        level="debug",
                        method=request.method,
                        path=request.url.path,
                        status=response.status_code,
                        # The member a manager sent this to (a body field on a
                        # POST, the facade's note), else the query's (abuse case 7).
                        instance=(
                            ",".join(targets)
                            or request.query_params.get("instance")
                            or None
                        ),
                    )
                return response

            return handler

    return CoreRoute


def build_router(
    holder: ConfigHolder, *, facade: Any = None, **router_kwargs: Any
) -> APIRouter:
    """Every ``/api/v1`` operation, as a router any FastAPI app can include.

    ``router_kwargs`` are passed to :class:`~fastapi.APIRouter` — an embedder uses
    ``dependencies=[Depends(...)]`` to put their own authorization in front of every
    operation (issue-212 R3.2). The ``/api/v1`` prefix stays *inside* the router: the
    API's version is the API's, and any namespace an embedder wants is theirs to add at
    ``include_router`` time.

    ``facade`` is the implementation behind every route (issue-374): the worker's
    :class:`~the_loop.api.facade.CoreFacade` when omitted, a manager's otherwise.
    """
    if facade is None:
        facade = CoreFacade(holder)
    router = APIRouter(route_class=_core_route_class(holder), **router_kwargs)

    @router.get(f"{API_PREFIX}/health", operation_id="health")
    def health(instance: str = Query("")) -> Dict[str, Any]:
        return facade.health(instance=instance)

    @router.get(f"{API_PREFIX}/instance", operation_id="getInstance")
    def get_instance(instance: str = Query("")) -> Dict[str, Any]:
        # Which instance answered, and what it manages (issue-322): the seam a
        # manager of several instances aggregates across (decision-110 D8). On a
        # manager, `instance` proxies the read to that member (issue-374 R2.7).
        return facade.get_instance(instance=instance)

    @router.get(f"{API_PREFIX}/instances", operation_id="listInstances")
    def list_instances() -> Dict[str, Any]:
        # The fleet (issue-374 R3.1): one row per instance, itself included.
        return facade.list_instances()

    @router.post(
        f"{API_PREFIX}/instances/register",
        operation_id="registerInstance",
    )
    def register_instance(body: InstanceRegisterBody) -> Dict[str, Any]:
        # A config write through the same splice `POST /config` uses (R4.2); a
        # worker answers 400 naming instance.role (R4.4).
        return facade.register_instance(body.name, body.url)

    @router.post(
        f"{API_PREFIX}/instances/unregister",
        operation_id="unregisterInstance",
    )
    def unregister_instance(body: InstanceUnregisterBody) -> Dict[str, Any]:
        return facade.unregister_instance(body.name)

    @router.get(
        f"{API_PREFIX}/work-items",
        operation_id="listWorkItems",
    )
    def list_work_items() -> List[Dict[str, Any]]:
        return facade.list_work_items()

    @router.get(
        f"{API_PREFIX}/work-items/one",
        operation_id="getWorkItem",
    )
    def get_work_item(
        ref: str = Query(...), instance: str = Query("")
    ) -> Dict[str, Any]:
        return facade.get_work_item(ref, instance=instance)

    @router.get(f"{API_PREFIX}/config", operation_id="getConfig")
    def get_config(instance: str = Query("")) -> Dict[str, Any]:
        return facade.get_config(instance=instance)

    @router.get(f"{API_PREFIX}/config/schema", operation_id="getConfigSchema")
    def get_config_schema(instance: str = Query("")) -> Dict[str, Any]:
        return facade.get_config_schema(instance=instance)

    @router.post(f"{API_PREFIX}/config", operation_id="updateConfig")
    def update_config(body: ConfigUpdateBody) -> Dict[str, Any]:
        # The holder picks the new file up on the *next* request through the route class,
        # which is what makes a saved change live without a restart. The response's
        # `config` is the document just written, so this response never lags the file.
        return facade.update_config(body.patch, instance=body.instance)

    @router.get(f"{API_PREFIX}/graph", operation_id="graphShow")
    def graph_show(
        repo: str = Query(...),
        pr: Optional[int] = Query(None),
        prRepo: str = Query(""),
        specDir: str = Query(""),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.graph_show(
            repo, pr=pr, pr_repo=prRepo, spec_dir=specDir, instance=instance
        )

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

        `workItem` is a spec-directory id (`issue-7`) or a work-item ref
        (`github:OWNER/REPO#7`), which names the same directory the daemon
        writes. Every resolving answer carries `statePath` — the
        `work-item-state.json` it was read from, or the path looked for — and
        `stateFound` (issue-396), so a report that fell back to the graph's
        start node is distinguishable from a work item that sits there. It
        also carries `pointer` (issue-429): the node that file records, `""`
        when none was found. With `recompute`, `currentNode` is the first node
        the artifacts leave unmet and can run ahead of `pointer`; a caller that
        must not ask about a node the item never entered bounds itself by
        `pointer`.

        A **ref** whose state file is not found and whose closure this machine
        stamped is answered from that stamp (issue-452): the report carries
        `archived` (`outcome`: completed | cancelled | closed-externally |
        unknown, `detail`: recorded | unavailable, the closure's facts and the
        `terminal` record), `nodes` is empty, and `ok` is true only for a
        completed item. A found state file always wins.

        `repo` is a path on the machine `instance` names — this one when it is
        empty (issue-374 R2.5).
        """
        return facade.graph_check(
            body.repo,
            body.workItem,
            recompute=body.recompute,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/graph/complete",
        operation_id="graphComplete",
    )
    def graph_complete(body: GraphCompleteBody) -> Dict[str, Any]:
        return facade.graph_complete(
            body.repo,
            body.workItem,
            node=body.node,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/graph/advance",
        operation_id="graphAdvance",
    )
    def graph_advance(body: GraphAdvanceBody) -> Dict[str, Any]:
        return facade.graph_advance(
            body.repo,
            body.workItem,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/graph/force",
        operation_id="graphForce",
    )
    def graph_force(body: GraphForceBody) -> Dict[str, Any]:
        return facade.graph_force(
            body.repo,
            body.workItem,
            body.toNode,
            body.reason,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/graph/skip",
        operation_id="graphSkip",
    )
    def graph_skip(body: GraphSkipBody) -> Dict[str, Any]:
        return facade.graph_skip(
            body.repo,
            body.workItem,
            body.nodes,
            body.reason,
            actor=body.actor,
            ref=body.ref,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/graph/repos",
        operation_id="graphRepos",
    )
    def graph_repos(body: GraphReposBody) -> Dict[str, Any]:
        return facade.graph_repos(
            body.repo,
            body.workItem,
            body.repositories,
            ref=body.ref,
            clear=body.clear,
            pr=body.pr,
            pr_repo=body.prRepo,
            spec_dir=body.specDir,
            instance=body.instance,
        )

    @router.get(f"{API_PREFIX}/sessions", operation_id="listSessions")
    def list_sessions(status: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
        return facade.list_sessions(status=status)

    @router.get(
        f"{API_PREFIX}/sessions/one",
        operation_id="getSession",
    )
    def get_session(ref: str = Query(...), instance: str = Query("")) -> Dict[str, Any]:
        return facade.get_session(ref, instance=instance)

    @router.get(
        f"{API_PREFIX}/sessions/transcript",
        operation_id="sessionTranscript",
    )
    def session_transcript(
        ref: str = Query(...), tail: int = Query(200, ge=0), instance: str = Query("")
    ) -> Dict[str, Any]:
        return facade.session_transcript(ref, tail=tail, instance=instance)

    @router.post(
        f"{API_PREFIX}/sessions/control",
        operation_id="controlSession",
    )
    def control_session(body: SessionControlBody) -> Dict[str, Any]:
        return facade.control_session(
            body.ref, body.verb, comment=body.comment, instance=body.instance
        )

    @router.post(
        f"{API_PREFIX}/sessions/reply",
        operation_id="replySession",
    )
    def reply_session(body: SessionReplyBody) -> Dict[str, Any]:
        return facade.reply_session(
            body.ref,
            body.text,
            actor=body.actor,
            comment=body.comment,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/sessions/register",
        operation_id="registerSession",
    )
    def register_session(body: SessionRegisterBody) -> Dict[str, Any]:
        return facade.register_session(
            body.ref,
            body.harness,
            body.harnessSessionId,
            cwd=body.cwd,
            force=body.force,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/sessions/link-pr",
        operation_id="linkSessionPullRequest",
    )
    def link_session_pull_request(body: SessionLinkPrBody) -> Dict[str, Any]:
        if body.discover:
            return facade.link_session_pull_request(
                body.ref,
                "",
                instance=body.instance,
                discover=True,
                branch=body.branch,
                repository=body.repository,
                head_owner=body.headOwner,
            )
        return facade.link_session_pull_request(
            body.ref, body.pullRequest, instance=body.instance
        )

    # -- the harness's GitHub verbs (issue-447) ---------------------------------

    @router.post(
        f"{API_PREFIX}/work-items/comments",
        operation_id="postWorkItemComment",
    )
    def post_work_item_comment(body: WorkItemCommentBody) -> Dict[str, Any]:
        return facade.post_work_item_comment(
            body.ref, body.body, instance=body.instance
        )

    @router.get(f"{API_PREFIX}/work-items/ticket", operation_id="getTicket")
    def get_ticket(ref: str = Query(...), instance: str = Query("")) -> Dict[str, Any]:
        return facade.get_ticket(ref, instance=instance)

    @router.post(f"{API_PREFIX}/work-items/tickets", operation_id="createTicket")
    def create_ticket(body: TicketCreateBody) -> Dict[str, Any]:
        return facade.create_ticket(
            body.repository,
            body.title,
            body.body,
            labels=body.labels,
            instance=body.instance,
            project=body.project,
        )

    @router.post(f"{API_PREFIX}/work-items/tickets/close", operation_id="closeTicket")
    def close_ticket(body: TicketCloseBody) -> Dict[str, Any]:
        return facade.close_ticket(
            body.ref, body.reason, body.workItem, instance=body.instance
        )

    @router.post(
        f"{API_PREFIX}/pull-requests/threads/resolve",
        operation_id="resolveReviewThread",
    )
    def resolve_review_thread(body: ThreadResolveBody) -> Dict[str, Any]:
        return facade.resolve_review_thread(
            body.ref, body.thread, body.workItem, instance=body.instance
        )

    @router.post(
        f"{API_PREFIX}/work-items/pull-requests",
        operation_id="createPullRequest",
    )
    def create_pull_request(body: PullRequestCreateBody) -> Dict[str, Any]:
        return facade.create_pull_request(
            body.ref,
            body.title,
            body.body,
            body.head,
            base=body.base,
            repository=body.repository,
            draft=body.draft,
            instance=body.instance,
        )

    @router.get(
        f"{API_PREFIX}/pull-requests/status",
        operation_id="getPullRequestStatus",
    )
    def get_pull_request_status(
        ref: str = Query(...),
        workItem: str = Query(""),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.get_pull_request_status(ref, workItem, instance=instance)

    @router.get(
        f"{API_PREFIX}/pull-requests/checks",
        operation_id="listPullRequestChecks",
    )
    def list_pull_request_checks(
        ref: str = Query(...),
        workItem: str = Query(""),
        failing: bool = Query(False),
        logLines: int = Query(DEFAULT_LOG_LINES, ge=0),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.list_pull_request_checks(
            ref,
            workItem,
            failing_only=failing,
            log_lines=logLines,
            instance=instance,
        )

    @router.get(
        f"{API_PREFIX}/pull-requests/threads",
        operation_id="listPullRequestThreads",
    )
    def list_pull_request_threads(
        ref: str = Query(...),
        workItem: str = Query(""),
        all: bool = Query(False),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.list_pull_request_threads(
            ref, workItem, include_resolved=all, instance=instance
        )

    @router.post(
        f"{API_PREFIX}/pull-requests/ready",
        operation_id="markPullRequestReady",
    )
    def mark_pull_request_ready(body: PullRequestReadyBody) -> Dict[str, Any]:
        return facade.mark_pull_request_ready(
            body.ref, body.workItem, instance=body.instance
        )

    @router.post(
        f"{API_PREFIX}/pull-requests/merge",
        operation_id="mergePullRequest",
    )
    def merge_pull_request(body: PullRequestMergeBody) -> Dict[str, Any]:
        return facade.merge_pull_request(
            body.ref, body.workItem, body.method, instance=body.instance, sha=body.sha
        )

    @router.post(
        f"{API_PREFIX}/sessions/close",
        operation_id="closeSession",
    )
    def close_session(body: SessionCloseBody) -> Dict[str, Any]:
        return facade.close_session(
            body.ref, keep_tmux=body.keepTmux, instance=body.instance
        )

    @router.get(
        f"{API_PREFIX}/standing-sessions",
        operation_id="listStandingSessions",
    )
    def list_standing_sessions() -> List[Dict[str, Any]]:
        return facade.list_standing_sessions()

    @router.get(
        f"{API_PREFIX}/standing-sessions/one",
        operation_id="getStandingSession",
    )
    def get_standing_session(
        name: str = Query(...), instance: str = Query("")
    ) -> Dict[str, Any]:
        return facade.get_standing_session(name, instance=instance)

    @router.post(
        f"{API_PREFIX}/standing-sessions/create",
        operation_id="createStandingSession",
    )
    def create_standing_session(body: StandingCreateBody) -> Dict[str, Any]:
        return facade.create_standing_session(
            body.name,
            harness=body.harness,
            cwd=body.cwd,
            prompt=body.prompt,
            description=body.description,
            harness_args=body.harnessArgs,
            slack_enabled=body.slackEnabled,
            slack_channel=body.slackChannel,
            auto_start=body.autoStart,
            start=body.start,
            instance=body.instance,
        )

    @router.post(
        f"{API_PREFIX}/standing-sessions/delete",
        operation_id="deleteStandingSession",
    )
    def delete_standing_session(body: StandingDeleteBody) -> Dict[str, Any]:
        return facade.delete_standing_session(body.name, instance=body.instance)

    @router.post(
        f"{API_PREFIX}/standing-sessions/control",
        operation_id="controlStandingSession",
    )
    def control_standing_session(body: StandingControlBody) -> Dict[str, Any]:
        return facade.control_standing_session(
            body.name, body.verb, instance=body.instance
        )

    @router.post(
        f"{API_PREFIX}/standing-sessions/say",
        operation_id="sayToStandingSession",
    )
    def say_to_standing_session(body: StandingSayBody) -> Dict[str, Any]:
        return facade.say_to_standing_session(
            body.name, body.text, actor=body.actor, instance=body.instance
        )

    # The response is declared rather than inferred: FastAPI would derive
    # `application/json` from the return annotation, and the contract this repo
    # publishes would then describe a media type this route never sends
    # (`apiSpecs`, contract-first). The frame shapes live here because they are
    # the wire contract — a client parses `event:` and this `data:`.
    @router.get(
        f"{API_PREFIX}/stream",
        operation_id="streamEvents",
        # Without `response_class` FastAPI infers `application/json` from the
        # return annotation and MERGES it with the declaration below, so the
        # published contract would offer a media type this route never sends.
        response_class=StreamingResponse,
        responses={
            200: {
                "description": (
                    "An open Server-Sent Events stream. Each frame is one of "
                    "`log` (an event-log record, with its byte offset as the SSE "
                    "`id` — quote it back as `Last-Event-ID` to resume; on a "
                    "manager the id is one offset per instance, "
                    "`name=offset,…`, and each record carries `instance`), "
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
        for name, refs in (("workItem", workItem), ("transcript", transcript)):
            if len(refs) > api_stream.MAX_FILTER_ENTRIES:
                detail = (
                    f"{name} accepts at most "
                    f"{api_stream.MAX_FILTER_ENTRIES} entries, got {len(refs)}"
                )
                eventlog.emit("stream.refused", reason="bad-filter", detail=detail)
                return JSONResponse(status_code=400, content={"detail": detail})
        for ref in list(workItem) + list(transcript):
            try:
                WorkItemRef.parse(ref)
            except ValueError as exc:
                # Truncated: the message quotes the caller, and the event log is
                # append-only and read by people.
                eventlog.emit(
                    "stream.refused",
                    reason="bad-filter",
                    detail=str(exc)[: api_stream.MAX_REFUSAL_DETAIL],
                )
                return JSONResponse(status_code=400, content={"detail": str(exc)})

        try:
            cursor = facade.parse_cursor(last_event_id)
        except ValueError as exc:
            eventlog.emit("stream.refused", reason="bad-cursor")
            return JSONResponse(status_code=400, content={"detail": str(exc)})

        broker = facade.stream_broker()
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
            facade.serve_stream(
                broker,
                subscriber,
                cursor,
                conf["keepAliveSeconds"],
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
        return facade.query_events(
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
        return facade.event_types()

    @router.get(f"{API_PREFIX}/daemons", operation_id="listDaemons")
    def list_daemons() -> List[Dict[str, Any]]:
        return facade.list_daemons()

    @router.post(
        f"{API_PREFIX}/daemons/control",
        operation_id="controlDaemon",
    )
    def control_daemon(body: DaemonControlBody) -> Dict[str, Any]:
        return facade.control_daemon(body.daemon, body.verb, instance=body.instance)

    @router.post(f"{API_PREFIX}/restart", operation_id="restart")
    def restart(body: RestartBody) -> Dict[str, Any]:
        # Scheduling, not doing (issue-228, R4.4): this process is among what a
        # restart stops, so the work happens in a detached `the-loop restart`
        # that outlives it, and the response only promises the spawn.
        return facade.restart(with_upgrade=body.withUpgrade, instance=body.instance)

    @router.get(
        f"{API_PREFIX}/attention",
        operation_id="listAttention",
    )
    def list_attention() -> List[Dict[str, Any]]:
        return facade.list_attention()

    @router.get(
        f"{API_PREFIX}/repo/scenarios",
        operation_id="repoScenarios",
    )
    def repo_scenarios(
        repo: str = Query(...),
        glob: List[str] = Query(default=[]),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.repo_scenarios(repo, globs=glob, instance=instance)

    @router.get(
        f"{API_PREFIX}/repo/instructions",
        operation_id="repoInstructions",
    )
    def repo_instructions(
        repo: str = Query(...),
        doc: List[str] = Query(default=[]),
        onMissing: str = Query("warn"),
        instance: str = Query(""),
    ) -> Dict[str, Any]:
        return facade.repo_instructions(
            repo, docs=doc, on_missing=onMissing, instance=instance
        )

    @router.get(
        f"{API_PREFIX}/repo/critics",
        operation_id="repoCritics",
    )
    def repo_critics(
        repo: str = Query(...), instance: str = Query("")
    ) -> List[Dict[str, Any]]:
        return facade.repo_critics(repo, instance=instance)

    @router.get(
        f"{API_PREFIX}/repo/critics/policy",
        operation_id="repoReviewPolicy",
    )
    def repo_review_policy(
        repo: str = Query(...), instance: str = Query("")
    ) -> Dict[str, Any]:
        return facade.repo_review_policy(repo, instance=instance)

    @router.post(
        f"{API_PREFIX}/repo/critics/run",
        operation_id="repoCriticRun",
    )
    def repo_critic_run(body: CriticRunBody) -> Dict[str, Any]:
        return facade.repo_critic_run(
            body.repo,
            body.name,
            body.prompt,
            body.promptFile,
            work_item=body.workItem,
            spec_dir=body.specDir,
            timeout=body.timeout,
            cwd=body.cwd,
            instance=body.instance,
        )

    return router
