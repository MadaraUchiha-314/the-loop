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

Since issue-374 every tool body calls the **facade** the REST routes call — the
worker's :class:`~the_loop.api.facade.CoreFacade`, or a manager's — so the two roles
serve one tool list, and the keyed tools take the same optional ``instance`` the
routes do. ``list_instances`` is registered; ``register_instance`` and
``unregister_instance`` are not (R4.5): they re-point the manager, which is the config
write above with a longer reach.

The harness's GitHub verbs (issue-447) are registered — comment, ticket, pull
request, **merge included**: the merge is gated inside core by the operator's
``routing.mergeOnApproval``, read from this process's config, so a tool call can
do nothing the ``the-loop pr merge`` verb could not.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from .. import prompts
from ..cli_config import ConfigHolder, default_cli_config_path
from .config import service_config
from .facade import CoreFacade

#: The path the MCP endpoint answers on, exactly — no trailing-slash redirect.
MCP_PATH = "/mcp"


def build_server(cli_config: Optional[dict] = None, *, facade: Any = None) -> MCPServer:
    """An :class:`MCPServer` whose tools are the facade's operations.

    Every tool body is a one-liner delegating to the facade — the same object the
    REST routes call, so the two interfaces cannot drift. ``facade`` defaults to a
    worker's over ``cli_config``.
    """
    if facade is None:
        facade = CoreFacade(ConfigHolder(cli_config, default_cli_config_path()))
    server = MCPServer(
        name="the-loop",
        title="the-loop control plane",
        version="1",
        instructions=prompts.load("mcp/server-instructions", inline=True),
    )

    def list_work_items() -> List[Dict[str, Any]]:
        """Every work item's portable record (control + poll state)."""
        return facade.list_work_items()

    def get_work_item(ref: str, instance: str = "") -> Dict[str, Any]:
        """One work item's portable record by ref."""
        return facade.get_work_item(ref, instance=instance)

    def check_work_item(
        repo: str, work_item: str, recompute: bool = False, instance: str = ""
    ) -> Dict[str, Any]:
        """Evaluate a work item's process-graph gates (pure read)."""
        return facade.graph_check(
            repo, work_item, recompute=recompute, instance=instance
        )

    def graph_show(repo: str, instance: str = "") -> Dict[str, Any]:
        """The process graph this repo runs on: its nodes and edges."""
        return facade.graph_show(repo, instance=instance)

    def graph_advance(
        repo: str, work_item: str, ref: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """Evaluate the current node's exit chain and take the matching edge."""
        return facade.graph_advance(repo, work_item, ref=ref, instance=instance)

    def graph_complete(
        repo: str,
        work_item: str,
        node: str = "",
        actor: str = "",
        ref: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        """File a completion claim for the current (or named) graph node."""
        return facade.graph_complete(
            repo, work_item, node=node, actor=actor, ref=ref, instance=instance
        )

    def list_sessions(status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Registered harness sessions with their last control command."""
        return facade.list_sessions(status=status)

    def session_transcript(
        ref: str, tail: int = 200, instance: str = ""
    ) -> Dict[str, Any]:
        """The tail of a session's own harness transcript."""
        return facade.session_transcript(ref, tail=tail, instance=instance)

    def control_session(
        ref: str, verb: str, comment: bool = True, instance: str = ""
    ) -> Dict[str, Any]:
        """Apply a session control verb with the full paper trail."""
        return facade.control_session(ref, verb, comment=comment, instance=instance)

    def register_session(
        ref: str,
        harness: str,
        harness_session_id: str,
        cwd: str = ".",
        force: bool = False,
        instance: str = "",
    ) -> Dict[str, Any]:
        """Link a work item to the harness session working it."""
        return facade.register_session(
            ref,
            harness,
            harness_session_id,
            cwd=cwd,
            force=force,
            instance=instance,
        )

    def link_pull_request(
        ref: str,
        pull_request: str = "",
        instance: str = "",
        discover: bool = False,
        branch: str = "",
        repository: str = "",
        head_owner: str = "",
    ) -> Dict[str, Any]:
        """Record a pull request as delivering a work item."""
        if discover:
            return facade.link_session_pull_request(
                ref,
                "",
                instance=instance,
                discover=True,
                branch=branch,
                repository=repository,
                head_owner=head_owner,
            )
        return facade.link_session_pull_request(ref, pull_request, instance=instance)

    # -- the harness's GitHub verbs (issue-447): what an agent used `gh` for ----

    def post_comment(ref: str, body: str, instance: str = "") -> Dict[str, Any]:
        """Post the agent's comment on a work item."""
        return facade.post_work_item_comment(ref, body, instance=instance)

    def get_ticket(ref: str, instance: str = "") -> Dict[str, Any]:
        """A ticket with its comments and attachment links."""
        return facade.get_ticket(ref, instance=instance)

    def create_ticket(
        title: str,
        repository: str = "",
        body: str = "",
        labels: Optional[List[str]] = None,
        instance: str = "",
        project: str = "",
        issue_type: str = "",
        parent: str = "",
    ) -> Dict[str, Any]:
        """Open a GitHub issue or a Jira ticket."""
        return facade.create_ticket(
            repository,
            title,
            body,
            labels=labels or [],
            instance=instance,
            project=project,
            issue_type=issue_type,
            parent=parent,
        )

    def create_pull_request(
        ref: str,
        title: str,
        body: str,
        head: str,
        base: str = "",
        repository: str = "",
        draft: bool = False,
        instance: str = "",
    ) -> Dict[str, Any]:
        """Open a pull request for a work item and link it."""
        return facade.create_pull_request(
            ref,
            title,
            body,
            head,
            base=base,
            repository=repository,
            draft=draft,
            instance=instance,
        )

    def pull_request_status(
        ref: str, work_item: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """A pull request's state, mergeability and checks verdict."""
        return facade.get_pull_request_status(ref, work_item, instance=instance)

    def pull_request_checks(
        ref: str,
        work_item: str = "",
        failing_only: bool = False,
        log_lines: int = 80,
        instance: str = "",
    ) -> Dict[str, Any]:
        """Every check run and commit status on a pull request's head."""
        return facade.list_pull_request_checks(
            ref,
            work_item,
            failing_only=failing_only,
            log_lines=log_lines,
            instance=instance,
        )

    def pull_request_threads(
        ref: str,
        work_item: str = "",
        include_resolved: bool = False,
        instance: str = "",
    ) -> Dict[str, Any]:
        """A pull request's review threads."""
        return facade.list_pull_request_threads(
            ref, work_item, include_resolved=include_resolved, instance=instance
        )

    def close_ticket(
        ref: str, reason: str = "completed", work_item: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """Close a registered work item's ticket."""
        return facade.close_ticket(ref, reason, work_item, instance=instance)

    def resolve_review_thread(
        ref: str, thread: str, work_item: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """Resolve one review thread on a pull request."""
        return facade.resolve_review_thread(ref, thread, work_item, instance=instance)

    def mark_pull_request_ready(
        ref: str, work_item: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """Take a draft pull request out of draft."""
        return facade.mark_pull_request_ready(ref, work_item, instance=instance)

    def merge_pull_request(
        ref: str,
        work_item: str = "",
        method: str = "merge",
        sha: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        """Merge a pull request, when the operator allows it."""
        return facade.merge_pull_request(
            ref, work_item, method, instance=instance, sha=sha
        )

    def list_standing_sessions() -> List[Dict[str, Any]]:
        """The standing sessions (issue-277)."""
        return facade.list_standing_sessions()

    def get_standing_session(name: str, instance: str = "") -> Dict[str, Any]:
        """One standing session by name."""
        return facade.get_standing_session(name, instance=instance)

    def say_to_standing_session(
        name: str, text: str, actor: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        """Send a message to a running standing session."""
        return facade.say_to_standing_session(
            name, text, actor=actor, instance=instance
        )

    def close_session(
        ref: str, keep_tmux: Optional[bool] = None, instance: str = ""
    ) -> Dict[str, Any]:
        """Close a work item's registration and settle its tmux session."""
        return facade.close_session(ref, keep_tmux=keep_tmux, instance=instance)

    def query_events(
        work_item: Optional[str] = None,
        source: Optional[str] = None,
        level: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query the structured event log (routing, dispatch, sessions, API)."""
        return facade.query_events(
            work_item=work_item,
            source=source,
            min_level=level,
            since=since,
            limit=limit,
        )

    def daemon_status() -> List[Dict[str, Any]]:
        """The ingress daemons and whether each is running."""
        return facade.list_daemons()

    def control_daemon(daemon: str, verb: str, instance: str = "") -> Dict[str, Any]:
        """Start or stop an ingress daemon (poller | gh-webhook)."""
        return facade.control_daemon(daemon, verb, instance=instance)

    def get_instance(instance: str = "") -> Dict[str, Any]:
        """This instance of the-loop (issue-322)."""
        return facade.get_instance(instance=instance)

    def list_instances() -> Dict[str, Any]:
        """The fleet (issue-374): one row per instance."""
        return facade.list_instances()

    def list_attention() -> List[Dict[str, Any]]:
        """Work items needing attention."""
        return facade.list_attention()

    def repo_scenarios(
        repo: str, globs: Optional[List[str]] = None, instance: str = ""
    ) -> Dict[str, Any]:
        """Gherkin scenarios covered by a repo's integration tests."""
        return facade.repo_scenarios(repo, globs=globs, instance=instance)

    def repo_instructions(
        repo: str,
        docs: Optional[List[str]] = None,
        on_missing: str = "warn",
        instance: str = "",
    ) -> Dict[str, Any]:
        """Whether a repo's registered instruction docs resolve."""
        return facade.repo_instructions(
            repo, docs=docs, on_missing=on_missing, instance=instance
        )

    def repo_critics(repo: str, instance: str = "") -> List[Dict[str, Any]]:
        """The critic harnesses the CLI config declares (critics[])."""
        return facade.repo_critics(repo, instance=instance)

    def repo_review_policy(repo: str = "", instance: str = "") -> Dict[str, Any]:
        """The review-round policy (the CLI config's reviews block), defaulted."""
        return facade.repo_review_policy(repo, instance=instance)

    def repo_critic_run(
        repo: str,
        name: str,
        prompt: str = "",
        prompt_file: str = "",
        work_item: str = "",
        spec_dir: str = "",
        timeout: Optional[float] = None,
        cwd: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        """Run ONE critic-review round and return its JSON envelope."""
        return facade.repo_critic_run(
            repo,
            name,
            prompt,
            prompt_file,
            work_item=work_item,
            spec_dir=spec_dir,
            timeout=timeout,
            cwd=cwd,
            instance=instance,
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
        post_comment,
        get_ticket,
        create_ticket,
        create_pull_request,
        pull_request_status,
        pull_request_checks,
        pull_request_threads,
        resolve_review_thread,
        close_ticket,
        mark_pull_request_ready,
        merge_pull_request,
        list_standing_sessions,
        get_standing_session,
        say_to_standing_session,
        query_events,
        daemon_status,
        control_daemon,
        get_instance,
        list_instances,
        list_attention,
        repo_scenarios,
        repo_instructions,
        repo_critics,
        repo_review_policy,
        repo_critic_run,
    ):
        # The description an agent reads is the prompt file, not the docstring
        # (issue-540): the docstring is a one-line note for Python readers.
        server.add_tool(
            fn,
            name=fn.__name__,
            description=prompts.load(f"mcp/tools/{fn.__name__}", inline=True),
        )

    return server


def build_app(
    cli_config: Optional[dict] = None,
    *,
    allowed_hosts: Optional[List[str]] = None,
    facade: Any = None,
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
    server = build_server(cli_config, facade=facade)
    return server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        transport_security=TransportSecuritySettings(
            allowed_hosts=sorted(set(allowed_hosts)),
            allowed_origins=[f"http://{h}" for h in sorted(set(allowed_hosts))],
        ),
    )
