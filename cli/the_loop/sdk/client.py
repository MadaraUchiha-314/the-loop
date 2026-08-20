""":class:`TheLoop` — the-loop as a component of somebody else's service (issue-212).

Two surfaces, one object:

* **capabilities** — eight namespaces of plain method calls (``loop.work_items.list()``,
  ``loop.graph.check(...)``) that reach :mod:`the_loop.core` directly. No HTTP, no
  subprocess, no running service.
* **the HTTP seam** — :meth:`TheLoop.router`, :meth:`TheLoop.mcp_app`,
  :meth:`TheLoop.lifespan` and :meth:`TheLoop.mount`, which hand the *same* router the
  standalone service serves to an application the-loop does not own.

Everything is driven by one CLI config, named at construction — the ticket's shape:
``TheLoop(config_path=".../cli-config.yaml")``. That file is the single place that says
who may command the loop, where sessions are checked out and which binaries are run, and
the SDK reads it strictly: a missing or unparseable config raises at construction rather
than degrading to ``{}``, because a long-lived service that starts on defaults nobody
chose fails closed *invisibly* (issue-212 R4.5).

The FastAPI and MCP imports are deferred into the methods that need them (NFR2), so a
batch script that only wants ``loop.events.query(...)`` pays for :mod:`the_loop.core` and
nothing more.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..cli_config import ConfigHolder, default_cli_config_path, load_cli_config
from ..core import attention as core_attention
from ..core import config as core_config
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import lifecycle as core_lifecycle
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import standing as core_standing
from ..core import workitems as core_workitems
from .environment import check_environment

logger = logging.getLogger("the-loop.sdk")

#: Where the SDK namespaces the-loop inside a host application. Not ``""``: a root mount
#: would let the MCP endpoint shadow every host route declared after ``mount()``.
DEFAULT_PREFIX = "/the-loop"


class _Namespace:
    """Base for the capability namespaces: they all need the live config."""

    def __init__(self, loop: "TheLoop") -> None:
        self._loop = loop

    @property
    def _config(self) -> Dict[str, Any]:
        return self._loop.config


class WorkItems(_Namespace):
    """Portable work-item records (:mod:`the_loop.core.workitems`)."""

    def list(self) -> List[Dict[str, Any]]:
        return core_workitems.list_work_items(self._config)

    def get(self, ref: str) -> Dict[str, Any]:
        return core_workitems.get_work_item(ref, self._config)


class Sessions(_Namespace):
    """Harness sessions: what is registered, what it is saying, and steering it."""

    def list(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return core_sessions.list_sessions(status=status, config=self._config)

    def get(self, ref: str) -> Dict[str, Any]:
        return core_sessions.get_session(ref, config=self._config)

    def transcript(self, ref: str, tail: int = 200) -> Dict[str, Any]:
        return core_sessions.get_transcript(ref, tail=tail, config=self._config)

    def control(self, ref: str, verb: str, comment: bool = True) -> Dict[str, Any]:
        return core_sessions.control_session(
            ref, verb, comment=comment, config=self._config
        )

    def reply(
        self, ref: str, text: str, actor: str = "", comment: bool = True
    ) -> Dict[str, Any]:
        return core_sessions.reply_session(
            ref, text, actor=actor, comment=comment, config=self._config
        )

    def ask(self, ref: str, question: str) -> Dict[str, Any]:
        return core_sessions.ask_session(ref, question, config=self._config)

    def register(
        self,
        ref: str,
        harness: str,
        harness_session_id: str,
        cwd: str = ".",
        force: bool = False,
    ) -> Dict[str, Any]:
        return core_sessions.register_session(
            ref,
            harness,
            harness_session_id,
            cwd=cwd,
            force=force,
            config=self._config,
        )

    def link_pr(self, ref: str, pull_request: str) -> Dict[str, Any]:
        return core_sessions.link_pull_request(ref, pull_request, config=self._config)

    def close(self, ref: str, keep_tmux: Optional[bool] = None) -> Dict[str, Any]:
        return core_sessions.close_session(
            ref, keep_tmux=keep_tmux, config=self._config
        )


class Standing(_Namespace):
    """Standing sessions: the sessions that belong to no work item (issue-277).

    Addressed by **name**, never by a work-item ref — a separate namespace, so
    nothing routed by ref can reach one and nothing here can reach a work item's
    session.
    """

    def list(self) -> List[Dict[str, Any]]:
        return core_standing.list_standing(config=self._config)

    def get(self, name: str) -> Dict[str, Any]:
        return core_standing.get_standing(name, config=self._config)

    def control(self, name: str, verb: str) -> Dict[str, Any]:
        return core_standing.control_standing(name, verb, config=self._config)

    def say(self, name: str, text: str, actor: str = "") -> Dict[str, Any]:
        return core_standing.say_standing(name, text, actor=actor, config=self._config)


class Graph(_Namespace):
    """The process graph: where a work item stands, and moving it (issue-148)."""

    def show(
        self, repo: str, pr: Optional[int] = None, pr_repo: str = ""
    ) -> Dict[str, Any]:
        return core_graphs.show(repo, pr=pr, pr_repo=pr_repo)

    def check(
        self,
        repo: str,
        work_item: str,
        recompute: bool = False,
        pr: Optional[int] = None,
        pr_repo: str = "",
    ) -> Dict[str, Any]:
        """The work item's gate report.

        A ``repo`` that does not resolve returns ``repoResolved: False`` with an
        empty ``nodes`` list instead of raising (issue-238) — an embedder gating
        on this report should treat that as *unevaluated*, not as *satisfied*.
        """
        return core_graphs.check(
            repo, work_item, recompute=recompute, pr=pr, pr_repo=pr_repo
        )

    def complete(
        self,
        repo: str,
        work_item: str,
        node: str = "",
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
    ) -> Dict[str, Any]:
        return core_graphs.complete(
            repo, work_item, node=node, actor=actor, ref=ref, pr=pr, pr_repo=pr_repo
        )

    def advance(
        self,
        repo: str,
        work_item: str,
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
    ) -> Dict[str, Any]:
        return core_graphs.advance(repo, work_item, ref=ref, pr=pr, pr_repo=pr_repo)

    def force(
        self,
        repo: str,
        work_item: str,
        to_node: str,
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
    ) -> Dict[str, Any]:
        return core_graphs.force(
            repo,
            work_item,
            to_node,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
        )

    def skip(
        self,
        repo: str,
        work_item: str,
        nodes: List[str],
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
    ) -> Dict[str, Any]:
        return core_graphs.skip(
            repo,
            work_item,
            nodes,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
        )


class Events(_Namespace):
    """The JSONL event log, queried (issue-63, decision-025)."""

    def query(
        self,
        types: Optional[List[str]] = None,
        work_item: Optional[str] = None,
        delivery_id: Optional[str] = None,
        source: Optional[str] = None,
        min_level: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return core_events.query_events(
            None,
            types=types or [],
            work_item=work_item,
            delivery_id=delivery_id,
            source=source,
            min_level=min_level,
            since=since,
            limit=limit,
        )

    def types(self) -> Dict[str, str]:
        return core_events.event_types()


class Daemons(_Namespace):
    """The ingress daemons — the poller and the webhook receiver."""

    def list(self) -> List[Dict[str, Any]]:
        return [
            core_daemons.daemon_status(name, self._config)
            for name in core_daemons.DAEMONS
        ]

    def control(self, daemon: str, verb: str) -> Dict[str, Any]:
        return core_daemons.control_daemon(daemon, verb, self._config)


class Attention(_Namespace):
    """What is waiting on a human right now (issue-179)."""

    def list(self) -> List[Dict[str, Any]]:
        return core_attention.list_attention(self._config)


class Repo(_Namespace):
    """Reads and runs scoped to a repository checkout."""

    def scenarios(self, repo: str, globs: Optional[List[str]] = None) -> Dict[str, Any]:
        return core_repo.scenarios(repo, globs=globs)

    def instructions(self, repo: str) -> Dict[str, Any]:
        return core_repo.instructions(repo)

    def critics(self, repo: str) -> List[Dict[str, Any]]:
        return core_repo.critics(repo)

    def critic_run(
        self,
        repo: str,
        name: str,
        prompt: str = "",
        prompt_file: str = "",
        work_item: str = "",
        spec_dir: str = "",
        timeout: Optional[float] = None,
        cwd: str = "",
    ) -> Dict[str, Any]:
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


class Settings(_Namespace):
    """The CLI config itself, read and changed (issue-222).

    Writes go to the path this instance already reads — there is no parameter naming a
    destination, by design: the config says who may command the loop, so a caller that
    could redirect the write would be editing the rules it is judged by.
    """

    def get(self) -> Dict[str, Any]:
        return core_config.get_config(self._loop.config_path)

    def schema(self) -> Dict[str, Any]:
        return core_config.get_schema()

    def update(self, patch: Dict[str, Any]) -> Dict[str, Any]:
        return core_config.update_config(patch, self._loop.config_path)


class TheLoop:
    """the-loop, driven from inside your own Python process.

    ``config_path`` names the CLI config to read; omit it for the resolution order every
    other the-loop process uses (``$THE_LOOP_CLI_CONFIG``, ``./.the-loop/cli-config.yaml``,
    ``~/.the-loop/cli-config.yaml``). ``config`` supplies the document directly instead —
    for tests, and for deployments that assemble their config from a secret store. Passing
    both is a :class:`ValueError`: there would be no answer to which one a write goes to.
    """

    def __init__(
        self,
        config_path: Optional[Union[str, Path]] = None,
        *,
        config: Optional[dict] = None,
    ) -> None:
        if config is not None and config_path is not None:
            raise ValueError(
                "pass config_path or config, not both — a TheLoop reads exactly one "
                "CLI config, and a write has to have one destination"
            )
        path = (
            Path(config_path) if config_path is not None else default_cli_config_path()
        )
        if config is None:
            initial = self._load_strictly(path)
        else:
            initial = dict(config)
        self._holder = ConfigHolder(initial, path)

        # Built on first use and cached: the app that gets mounted must be the same
        # object whose session manager the lifespan starts.
        self._mcp_app: Any = None
        self._mcp_built = False
        self._mcp_allowed_hosts: Optional[List[str]] = None
        self._mcp_wanted = True
        self._host_ingresses: Optional[bool] = None
        self._lifespan_running = False

        self.work_items = WorkItems(self)
        self.sessions = Sessions(self)
        self.standing = Standing(self)
        self.graph = Graph(self)
        self.events = Events(self)
        self.daemons = Daemons(self)
        self.attention = Attention(self)
        self.repo = Repo(self)
        self.settings = Settings(self)

    # ---- configuration -------------------------------------------------------

    @staticmethod
    def _load_strictly(path: Path) -> dict:
        """Read the config, raising rather than degrading to ``{}`` (R4.5).

        ``FileNotFoundError`` already names the path. A parse failure is re-raised as
        ``ValueError`` naming it too, so the SDK's exception contract stays the
        two-exception one :mod:`the_loop.core` has.
        """
        try:
            return load_cli_config(path, strict=True)
        except FileNotFoundError:
            raise
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 — every parse failure reads the same
            raise ValueError(f"{path}: {exc}") from exc

    @property
    def config(self) -> Dict[str, Any]:
        """The CLI config as it is *now* — re-read when the file changes."""
        return self._holder.current

    @property
    def config_path(self) -> Path:
        """The file :attr:`config` is read from and :attr:`settings` writes to."""
        return self._holder.path

    def reload(self) -> Dict[str, Any]:
        """Re-read the config file if it changed, and return the current document.

        The HTTP seam does this once per request on its own; a long-lived non-HTTP caller
        (a worker loop, a scheduled job) calls this at whatever point suits it.
        """
        self._holder.refresh()
        return self._holder.current

    # ---- host-environment and deployment facts -------------------------------

    def check_environment(self) -> Dict[str, Any]:
        """Which external binaries this configuration needs, and which are present.

        A report, never a gate: nothing here blocks a call, and nothing it finds is
        executed. See :mod:`the_loop.sdk.environment`.
        """
        return check_environment(self.config)

    def status(self) -> Dict[str, Any]:
        """Per-service status of the *standalone* deployment this config describes.

        The read half of ``the-loop status``. The write half — ``start``/``stop``/
        ``restart`` — is deliberately not on the SDK: it spawns and kills the-loop's own
        processes, which inside your service is either meaningless or actively wrong.
        Your process's lifecycle is yours.
        """
        return core_lifecycle.status_all(self.config)

    # ---- the HTTP seam -------------------------------------------------------

    def router(self, **kwargs: Any):
        """The ``/api/v1`` surface as a :class:`fastapi.APIRouter`.

        ``kwargs`` reach :class:`~fastapi.APIRouter` — most usefully
        ``dependencies=[Depends(your_auth)]``, which runs for every the-loop operation
        before any handler executes. Include it in your app under whatever prefix you
        like::

            app.include_router(loop.router(dependencies=[Depends(verify)]),
                               prefix="/the-loop")
        """
        from ..api.routes import build_router

        return build_router(self._holder, **kwargs)

    def mcp_app(self, *, allowed_hosts: Optional[List[str]] = None) -> Any:
        """The MCP streamable-HTTP app, or ``None`` when ``service.mcp.enabled`` is false.

        Built once and cached — the object that gets mounted has to be the object whose
        session manager :meth:`lifespan` starts, or the first MCP call fails. Later calls
        return the cached app and ignore ``allowed_hosts``.

        ``allowed_hosts`` is the DNS-rebinding allowlist. It defaults to a derivation from
        ``service.host``/``service.port``, which describes the *standalone* service's bind
        and not yours — an embedded deployment reachable at ``loop.example.com`` passes
        ``["loop.example.com"]`` here, or gets a 421 from the MCP SDK's transport guard.
        """
        if self._mcp_built:
            return self._mcp_app
        from ..api.config import service_config

        self._mcp_built = True
        if not service_config(self.config)["mcpEnabled"]:
            self._mcp_app = None
            return None
        from ..api.mcp import build_app as build_mcp_app

        self._mcp_allowed_hosts = list(allowed_hosts) if allowed_hosts else None
        self._mcp_app = build_mcp_app(
            self.config, allowed_hosts=self._mcp_allowed_hosts
        )
        return self._mcp_app

    def host_ingresses(self) -> bool:
        """Whether *this* process runs the enabled ingresses (poller, receiver).

        Follows ``service.hostIngresses`` (default true) unless :meth:`mount` was given an
        explicit value. Worth an explicit ``False`` when your service runs several
        workers: each would otherwise start its own poller, and only the first would win
        the lock.
        """
        if self._host_ingresses is not None:
            return self._host_ingresses
        from ..api.config import service_config

        return bool(service_config(self.config)["hostIngresses"])

    def lifespan(self, app: Any = None):
        """The process-lifetime concerns, as an async context manager.

        Holds open whatever needs the process to be alive: the MCP session manager, and
        the hosted ingresses when :meth:`host_ingresses` says so. Compose it with your
        own::

            @asynccontextmanager
            async def lifespan(app):
                async with loop.lifespan(app):
                    async with my_startup(app):
                        yield

        or pass it straight to FastAPI (``FastAPI(lifespan=loop.lifespan)``) when
        the-loop is the only thing that needs one. :meth:`mount` wraps it around your
        app's existing lifespan by default, so most callers never write either form.
        """
        from ..api.lifespan import build_lifespan

        base = build_lifespan(
            self.config,
            mcp_app=self.mcp_app() if self._mcp_wanted else None,
            host_ingresses=self.host_ingresses(),
        )

        @asynccontextmanager
        async def run():
            self._lifespan_running = True
            try:
                async with base(app):
                    yield
            finally:
                self._lifespan_running = False

        return run()

    def mount(
        self,
        app: Any,
        *,
        prefix: str = DEFAULT_PREFIX,
        dependencies: Optional[List[Any]] = None,
        lifespan: bool = True,
        mcp: bool = True,
        host_ingresses: Optional[bool] = None,
        mcp_allowed_hosts: Optional[List[str]] = None,
        **router_kwargs: Any,
    ) -> Dict[str, Any]:
        """Attach the-loop to ``app``, and report what was attached.

        Call it while the application is being constructed — it may wrap ``app``'s
        lifespan, which is read once when the app starts.

        The SDK touches ``app`` in **at most two** ways, both requested here:
        ``include_router``, and (unless ``lifespan=False``) its lifespan. It installs no
        middleware, registers no exception handlers, and applies no CORS policy — your
        app's cross-origin policy is yours, and its scope is the whole app rather than one
        router.

        ``dependencies`` reach every the-loop operation. **On a publicly reachable
        application, pass one**: this surface can spawn harness sessions with the
        operator's credentials, and the-loop's own network guards (the loopback bind, the
        CORS allowlist) belong to the standalone service, not to yours.

        Returns a report — the prefix, the operation count, whether MCP was mounted and
        where, how the lifespan was arranged, and whether this process hosts the
        ingresses — because a mount that silently did less than you expected (MCP disabled
        in the config, ingresses declined) is worth seeing at startup.
        """
        prefix = self._normalize_prefix(prefix)
        self._host_ingresses = host_ingresses
        self._mcp_wanted = mcp

        router = self.router(dependencies=dependencies, **router_kwargs)
        app.include_router(router, prefix=prefix)

        mcp_app = self.mcp_app(allowed_hosts=mcp_allowed_hosts) if mcp else None
        if mcp_app is not None:
            if not prefix:
                raise ValueError(
                    "mounting the MCP endpoint needs a non-empty prefix: the MCP app is "
                    "mounted at the prefix so that <prefix>/mcp answers with no "
                    "trailing-slash redirect, and at the root it would shadow every "
                    "route your app declares after mount(). Pass prefix='/the-loop', or "
                    "mcp=False."
                )
            # Mounted *after* include_router, exactly as the standalone app does at the
            # root: Starlette matches in order, so the /api/v1 routes still win, and the
            # MCP SDK's own `streamable_http_path="/mcp"` lands on <prefix>/mcp.
            app.mount(prefix, _LifespanGuardedApp(mcp_app, self))

        if lifespan:
            self._wrap_lifespan(app)

        report = {
            "prefix": prefix,
            "operations": len(router.routes),
            "mcp": {
                "mounted": mcp_app is not None,
                "path": f"{prefix}/mcp" if mcp_app is not None else "",
            },
            "lifespan": "wrapped" if lifespan else "caller",
            "hostIngresses": self.host_ingresses(),
            "dependencies": len(dependencies or []),
        }
        logger.info("the-loop mounted: %s", report)
        return report

    # ---- internals -----------------------------------------------------------

    @staticmethod
    def _normalize_prefix(prefix: str) -> str:
        if not prefix:
            return ""
        if not prefix.startswith("/"):
            raise ValueError(f"prefix must start with '/' (got {prefix!r})")
        if prefix.endswith("/"):
            raise ValueError(f"prefix must not end with '/' (got {prefix!r})")
        return prefix

    def _wrap_lifespan(self, app: Any) -> None:
        """Run the-loop's lifespan around whatever ``app`` already had.

        The host's lifespan is entered *inside* the-loop's and still runs; nothing it does
        is skipped or reordered relative to itself. Wrapping is the default because the
        failure mode of forgetting is silent at import, silent at startup, and surfaces as
        a session-manager error on the first MCP call — from a client, in production.
        """
        existing = app.router.lifespan_context
        outer = self

        @asynccontextmanager
        async def composed(scoped_app: Any):
            async with outer.lifespan(scoped_app):
                async with existing(scoped_app):
                    yield

        app.router.lifespan_context = composed


class _LifespanGuardedApp:
    """The MCP app, refusing to serve before its session manager has started (R2.6).

    Without this, ``mount(lifespan=False)`` plus a forgotten composition produces an
    obscure session-manager error on the first MCP call. With it, the answer says what was
    not done.
    """

    def __init__(self, app: Any, loop: TheLoop) -> None:
        self._app = app
        self._loop = loop

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and not self._loop._lifespan_running:
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "the-loop's lifespan is not running, so the MCP session manager "
                        "has not started. Compose `TheLoop.lifespan` into your "
                        "application's lifespan, or call `mount()` without "
                        "`lifespan=False`."
                    )
                },
            )
            await response(scope, receive, send)
            return
        await self._app(scope, receive, send)
