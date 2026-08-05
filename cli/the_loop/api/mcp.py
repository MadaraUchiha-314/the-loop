"""The MCP interface: ``POST /mcp`` on the control-plane app (issue-161, R5).

HTTP transport **only** — no stdio (owner decision, PR #162). A deliberate
minimal implementation of the streamable-HTTP shape rather than the SDK
(decision-058): the protocol subset an agent host needs — ``initialize``,
``notifications/initialized``, ``tools/list``, ``tools/call`` — is a few
JSON-RPC handlers over the same core facade the REST routers use, and every
tool result is the same JSON the corresponding REST route serves.

The tool registry is **generated from the core surface** (R1.4): each entry
names its handler; there is no second implementation to drift. Exclusions are
policy (R5.3, design §Security design): ``sessions reset`` is destructive and
stays a local decision; ``graph force`` requires a human-attributed reason an
agent must not forge. Same bearer token as REST; every call lands in the event
log as ``mcp.call``.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from .. import eventlog
from ..core import attention as core_attention
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import workitems as core_workitems

PROTOCOL_VERSION = "2025-06-18"

_STR = {"type": "string"}
_BOOL = {"type": "boolean"}


def _schema(properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _tools(cli_config: Optional[dict]) -> Dict[str, Dict[str, Any]]:
    """name → {description, inputSchema, handler}. Read + manage; no reset, no force."""
    return {
        "list_work_items": {
            "description": "Every work item's portable record (control + poll state).",
            "inputSchema": _schema({}, []),
            "handler": lambda a: core_workitems.list_work_items(cli_config),
        },
        "get_work_item": {
            "description": "One work item's portable record by ref "
            "(e.g. github:OWNER/REPO#7).",
            "inputSchema": _schema({"ref": _STR}, ["ref"]),
            "handler": lambda a: core_workitems.get_work_item(a["ref"], cli_config),
        },
        "check_work_item": {
            "description": "Evaluate a work item's process-graph gates against its "
            "checked-in artifacts (pure read; same report as `the-loop check`).",
            "inputSchema": _schema(
                {"repo": _STR, "workItem": _STR, "recompute": _BOOL},
                ["repo", "workItem"],
            ),
            "handler": lambda a: core_graphs.check(
                a["repo"], a["workItem"], recompute=bool(a.get("recompute"))
            ),
        },
        "graph_advance": {
            "description": "Evaluate the current node's exit chain and take the "
            "matching edge.",
            "inputSchema": _schema(
                {"repo": _STR, "workItem": _STR}, ["repo", "workItem"]
            ),
            "handler": lambda a: core_graphs.advance(a["repo"], a["workItem"]),
        },
        "graph_complete": {
            "description": "File a completion claim for the current (or named) node.",
            "inputSchema": _schema(
                {"repo": _STR, "workItem": _STR, "node": _STR, "actor": _STR},
                ["repo", "workItem"],
            ),
            "handler": lambda a: core_graphs.complete(
                a["repo"],
                a["workItem"],
                node=a.get("node", ""),
                actor=a.get("actor", ""),
            ),
        },
        "list_sessions": {
            "description": "Registered harness sessions with their last control "
            "command.",
            "inputSchema": _schema({"status": _STR}, []),
            "handler": lambda a: core_sessions.list_sessions(
                status=a.get("status") or None, config=cli_config
            ),
        },
        "control_session": {
            "description": "Apply a session control verb "
            "(start | pause | resume | stop) with the full paper trail.",
            "inputSchema": _schema(
                {"ref": _STR, "verb": _STR, "comment": _BOOL}, ["ref", "verb"]
            ),
            "handler": lambda a: core_sessions.control_session(
                a["ref"],
                a["verb"],
                comment=bool(a.get("comment", True)),
                config=cli_config,
            ),
        },
        "query_events": {
            "description": "Query the structured event log (routing, dispatch, "
            "sessions, API operations).",
            "inputSchema": _schema(
                {
                    "workItem": _STR,
                    "source": _STR,
                    "level": _STR,
                    "since": _STR,
                    "limit": {"type": "integer"},
                },
                [],
            ),
            "handler": lambda a: core_events.query_events(
                None,
                work_item=a.get("workItem"),
                source=a.get("source"),
                min_level=a.get("level"),
                since=a.get("since"),
                limit=int(a.get("limit", 50)),
            ),
        },
        "daemon_status": {
            "description": "The ingress daemons (poller, gh-webhook) and whether "
            "each is running.",
            "inputSchema": _schema({}, []),
            "handler": lambda a: [
                core_daemons.daemon_status(name, cli_config)
                for name in core_daemons.DAEMONS
            ],
        },
        "control_daemon": {
            "description": "Start or stop an ingress daemon (poller | gh-webhook).",
            "inputSchema": _schema({"daemon": _STR, "verb": _STR}, ["daemon", "verb"]),
            "handler": lambda a: core_daemons.control_daemon(
                a["daemon"], a["verb"], cli_config
            ),
        },
        "list_attention": {
            "description": "Work items needing human attention: paused sessions, "
            "armed items with no live session, recent errors.",
            "inputSchema": _schema({}, []),
            "handler": lambda a: core_attention.list_attention(cli_config),
        },
        "repo_scenarios": {
            "description": "Gherkin scenarios covered by a repo's integration tests.",
            "inputSchema": _schema({"repo": _STR}, ["repo"]),
            "handler": lambda a: core_repo.scenarios(a["repo"]),
        },
        "repo_instructions": {
            "description": "A repo's registered custom-instruction docs and their "
            "resolution state.",
            "inputSchema": _schema({"repo": _STR}, ["repo"]),
            "handler": lambda a: core_repo.instructions(a["repo"]),
        },
        "repo_critics": {
            "description": "A repo's configured critic harnesses.",
            "inputSchema": _schema({"repo": _STR}, ["repo"]),
            "handler": lambda a: core_repo.critics(a["repo"]),
        },
    }


def _rpc_error(id_: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}
    )


def _rpc_result(id_: Any, result: Dict[str, Any]) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": id_, "result": result})


def add_mcp(
    app: FastAPI,
    cli_config: Optional[dict],
    authenticate: Callable[[Request], None],
) -> None:
    tools = _tools(cli_config)

    @app.post("/mcp", include_in_schema=False)
    async def mcp_endpoint(request: Request) -> Response:
        authenticate(request)  # 401 before anything is parsed further
        try:
            message = await request.json()
        except Exception:
            return _rpc_error(None, -32700, "parse error")
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "invalid request")

        method = message.get("method", "")
        id_ = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            return _rpc_result(
                id_,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "the-loop", "version": "1"},
                },
            )
        if method == "notifications/initialized":
            return Response(status_code=202)
        if method == "tools/list":
            return _rpc_result(
                id_,
                {
                    "tools": [
                        {
                            "name": name,
                            "description": tool["description"],
                            "inputSchema": tool["inputSchema"],
                        }
                        for name, tool in sorted(tools.items())
                    ]
                },
            )
        if method == "tools/call":
            name = params.get("name", "")
            tool = tools.get(name)
            if tool is None:
                return _rpc_error(id_, -32602, f"unknown tool: {name}")
            arguments = params.get("arguments") or {}
            try:
                result = tool["handler"](arguments)
                ok = True
            except (ValueError, LookupError, KeyError) as exc:
                result = {"error": str(exc)}
                ok = False
            eventlog.emit("mcp.call", tool=name, ok=ok)
            return _rpc_result(
                id_,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, default=str)}
                    ],
                    "isError": not ok,
                },
            )
        return _rpc_error(id_, -32601, f"method not found: {method}")
