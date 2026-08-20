"""The MCP interface, on the **official** MCP Python SDK (issue-161, R5).

Owner decision (PR #162): *"I hope we are using the official python SDK for
MCP… Don't want to maintain custom implementation. Follow official SDKs."* —
so the protocol is entirely the SDK's (`mcp.server.MCPServer`), and this module
is only the **binding** from the-loop's core facade to it: one thin function
per tool, registered with `add_tool`, which derives each tool's input schema
from the annotations. There is no hand-rolled JSON-RPC here any more.

Transport is **streamable HTTP only — no stdio** (owner decision): the SDK's
`streamable_http_app()` is mounted on the same FastAPI app that serves
`/api/v1`, so one `the-loop start` exposes both. The SDK's DNS-rebinding
protection is left **on** and pinned to the service's configured host, which
matches the loopback-by-default posture the exposure guard enforces.

Exclusions are policy (R5.3): ``sessions reset`` is destructive and stays a
local decision; ``graph force`` requires a human-attributed reason an agent
must not forge. The **CLI config** (``/api/v1/config``, issue-222) is excluded
for the same reason with a longer half-life: it names who may command the loop
and which binaries the daemon runs, so changing it is an operator's act, and an
agent that could rewrite it would be editing the rules it is judged by. None of
the three is registered as a tool. ``restart`` (``POST /api/v1/restart``,
issue-228) is excluded on both grounds at once: it tears down the very
transport the MCP client is speaking over mid-call, and ``--with-upgrade``
reaches the installer — an agent must not be able to replace the code it is
judged by. A client that legitimately needs it has the REST route. **Standing-session
control, create and delete** (``POST /api/v1/standing-sessions/{control,create,
delete}``, issue-277) join them: an agent that could stop or restart a standing
session could stop the very one supervising it, and bringing a harness process
into — or out of — existence is an operator's act. Reading them and *talking*
to them are registered, because those are what an agent coordinating with a
supervisor session actually needs.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from ..core import attention as core_attention
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import standing as core_standing
from ..core import workitems as core_workitems
from .config import service_config

#: The path the MCP endpoint answers on, exactly — no trailing-slash redirect.
MCP_PATH = "/mcp"


def build_server(cli_config: Optional[dict] = None) -> MCPServer:
    """An :class:`MCPServer` whose tools are the core facade's operations.

    Every tool body is a one-liner delegating to ``the_loop.core`` — the same
    functions the REST routers call, so the two interfaces cannot drift.
    """
    server = MCPServer(
        name="the-loop",
        title="the-loop control plane",
        version="1",
        instructions=(
            "Inspect and steer the-loop's work items: read portable records, "
            "evaluate process-graph gates, control harness sessions and the "
            "ingress daemons, and query the structured event log."
        ),
    )

    def list_work_items() -> List[Dict[str, Any]]:
        """Every work item's portable record (control + poll state)."""
        return core_workitems.list_work_items(cli_config)

    def get_work_item(ref: str) -> Dict[str, Any]:
        """One work item's portable record by ref (e.g. github:OWNER/REPO#7)."""
        return core_workitems.get_work_item(ref, cli_config)

    def check_work_item(
        repo: str, work_item: str, recompute: bool = False
    ) -> Dict[str, Any]:
        """Evaluate a work item's process-graph gates against its checked-in
        artifacts (pure read; the same report `the-loop check` prints).

        A `repo` that is not a directory on this machine comes back as
        `{"repoResolved": false, "nodes": [], "currentNode": ""}` rather than an
        error. That is "this checkout is not here", NOT "this work item has no
        phases" — do not report progress from it; check the path instead."""
        return core_graphs.check(repo, work_item, recompute=recompute)

    def graph_show(repo: str) -> Dict[str, Any]:
        """The process graph this repo runs on: its nodes and edges."""
        return core_graphs.show(repo)

    def graph_advance(repo: str, work_item: str, ref: str = "") -> Dict[str, Any]:
        """Evaluate the current node's exit chain and take the matching edge."""
        return core_graphs.advance(repo, work_item, ref=ref)

    def graph_complete(
        repo: str, work_item: str, node: str = "", actor: str = "", ref: str = ""
    ) -> Dict[str, Any]:
        """File a completion claim for the current (or named) graph node."""
        return core_graphs.complete(repo, work_item, node=node, actor=actor, ref=ref)

    def list_sessions(status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Registered harness sessions with their last control command."""
        return core_sessions.list_sessions(status=status, config=cli_config)

    def session_transcript(ref: str, tail: int = 200) -> Dict[str, Any]:
        """The tail of a session's own harness transcript (Claude Code JSONL),
        resolved from the registered cwd + session id and served fail-closed —
        only `<id>.jsonl` files inside the harness's projects directory. `tail`
        is the number of entries to return; 0 means the whole file."""
        return core_sessions.get_transcript(ref, tail=tail, config=cli_config)

    def control_session(ref: str, verb: str, comment: bool = True) -> Dict[str, Any]:
        """Apply a session control verb (start | pause | resume | stop |
        cleanup) with the full paper trail. `cleanup` is destructive: it
        releases the work item's LOCAL resources — every endpoint's tmux
        session, the workspace checkout (uncommitted work in it is gone) and
        the machine-local session record — keeping the portable record and
        touching nothing remote."""
        return core_sessions.control_session(
            ref, verb, comment=comment, config=cli_config
        )

    def register_session(
        ref: str,
        harness: str,
        harness_session_id: str,
        cwd: str = ".",
        force: bool = False,
    ) -> Dict[str, Any]:
        """Link a work item to the harness session working it, so ingress
        events route to that session."""
        return core_sessions.register_session(
            ref,
            harness,
            harness_session_id,
            cwd=cwd,
            force=force,
            config=cli_config,
        )

    def link_pull_request(ref: str, pull_request: str) -> Dict[str, Any]:
        """Record a pull request as delivering a work item, so its comments,
        reviews and CI results route to that work item's session. Call this in
        the same step as opening the pull request: a pull request the-loop
        authored carries none of the linkages the router can otherwise infer.
        `pull_request` is its number in the work item's own repository, or a
        full ref (github:OWNER/REPO#16) for one in another repository."""
        return core_sessions.link_pull_request(ref, pull_request, config=cli_config)

    def list_standing_sessions() -> List[Dict[str, Any]]:
        """The standing sessions (issue-277) — the long-lived sessions that
        belong to no work item, declared in the CLI config and addressed by
        name. `running` is tmux's answer now, not the record's."""
        return core_standing.list_standing(config=cli_config)

    def get_standing_session(name: str) -> Dict[str, Any]:
        """One standing session by name, or an error when it is neither
        declared nor recorded."""
        return core_standing.get_standing(name, config=cli_config)

    def say_to_standing_session(
        name: str, text: str, actor: str = ""
    ) -> Dict[str, Any]:
        """Send a message to a running standing session — pasted into its
        terminal and submitted. A standing session owns no ticket, so nothing
        is posted anywhere; `standing.said` is the record. Fail-closed: a
        message never starts a session, so an unknown or stopped name is an
        error naming `the-loop standing start <name>`."""
        return core_standing.say_standing(name, text, actor=actor, config=cli_config)

    def close_session(ref: str, keep_tmux: Optional[bool] = None) -> Dict[str, Any]:
        """Close a work item's registration and settle its tmux session."""
        return core_sessions.close_session(ref, keep_tmux=keep_tmux, config=cli_config)

    def query_events(
        work_item: Optional[str] = None,
        source: Optional[str] = None,
        level: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query the structured event log (routing, dispatch, sessions, API)."""
        return core_events.query_events(
            None,
            work_item=work_item,
            source=source,
            min_level=level,
            since=since,
            limit=limit,
        )

    def daemon_status() -> List[Dict[str, Any]]:
        """The ingress daemons (poller, gh-webhook): whether each is running, its
        pid, pidfile and logfile, and — for the poller — when it started and last
        completed a cycle. Liveness is the pidfile's lock, never the heartbeat."""
        return [
            core_daemons.daemon_status(name, cli_config)
            for name in core_daemons.DAEMONS
        ]

    def control_daemon(daemon: str, verb: str) -> Dict[str, Any]:
        """Start or stop an ingress daemon (poller | gh-webhook)."""
        return core_daemons.control_daemon(daemon, verb, cli_config)

    def list_attention() -> List[Dict[str, Any]]:
        """Work items needing attention: paused sessions, armed items with no
        live session, recent errors."""
        return core_attention.list_attention(cli_config)

    def repo_scenarios(repo: str, globs: Optional[List[str]] = None) -> Dict[str, Any]:
        """Gherkin scenarios covered by a repo's integration tests, with the
        globs they were collected from."""
        return core_repo.scenarios(repo, globs=globs)

    def repo_instructions(repo: str) -> Dict[str, Any]:
        """A repo's registered custom-instruction docs, their resolution state
        and the onMissing policy that grades them."""
        return core_repo.instructions(repo)

    def repo_critics(repo: str) -> List[Dict[str, Any]]:
        """A repo's configured critic harnesses."""
        return core_repo.critics(repo)

    def repo_critic_run(
        repo: str,
        name: str,
        prompt: str = "",
        prompt_file: str = "",
        work_item: str = "",
        spec_dir: str = "",
        timeout: Optional[float] = None,
        cwd: str = "",
    ) -> Dict[str, Any]:
        """Run ONE critic-review round and return its JSON envelope."""
        return core_repo.critic_run(
            repo,
            name,
            prompt,
            prompt_file,
            work_item=work_item,
            spec_dir=spec_dir,
            timeout=timeout,
            cwd=cwd,
        )

    for fn in (
        list_work_items,
        get_work_item,
        check_work_item,
        graph_show,
        graph_advance,
        graph_complete,
        list_sessions,
        session_transcript,
        control_session,
        register_session,
        link_pull_request,
        close_session,
        list_standing_sessions,
        get_standing_session,
        say_to_standing_session,
        query_events,
        daemon_status,
        control_daemon,
        list_attention,
        repo_scenarios,
        repo_instructions,
        repo_critics,
        repo_critic_run,
    ):
        server.add_tool(fn, name=fn.__name__)

    return server


def build_app(
    cli_config: Optional[dict] = None, *, allowed_hosts: Optional[List[str]] = None
):
    """The SDK's streamable-HTTP ASGI app, ready to mount at :data:`MCP_PATH`.

    DNS-rebinding protection stays enabled (the SDK's default) with the hosts
    the service actually answers on — the same loopback-by-default posture the
    exposure guard enforces for the REST surface.

    ``allowed_hosts`` overrides that derivation, and exists for the embedded case
    (issue-212): a mount inside somebody else's application answers on *their* host and
    port, which ``service.host``/``service.port`` do not describe. Absent, the derivation
    is unchanged, so the standalone service behaves exactly as before.
    """
    if allowed_hosts is None:
        conf = service_config(cli_config)
        host, port = conf["host"], conf["port"]
        allowed_hosts = [f"{host}:{port}", host]
        if host in ("127.0.0.1", "localhost"):
            allowed_hosts += [f"localhost:{port}", "localhost", f"127.0.0.1:{port}"]
    server = build_server(cli_config)
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        transport_security=TransportSecuritySettings(
            allowed_hosts=sorted(set(allowed_hosts)),
            allowed_origins=[f"http://{h}" for h in sorted(set(allowed_hosts))],
        ),
    )
