"""The facade seam: one router, two facades (issue-374, decision-138 D3).

:func:`the_loop.api.routes.build_router` used to import twelve ``the_loop.core``
modules and call them by name. A manager must serve the identical surface over a
different implementation — its own state **plus** the registered instances' — and the
one construction that makes "identical" a property rather than a promise is for the
router to call **one object with one method per operation**, and for the worker and the
manager to be two implementations of it. The contract parity test then proves both
applications serve the authored contract, and a route added to the router without a
facade method fails loudly on both.

:class:`CoreFacade` is the worker's: every method is the same one-liner over
:mod:`the_loop.core` the route body used to be, plus the ``instance`` parameter every
keyed operation now carries (R2.6) — accepted empty or as this instance's own name, and
``LookupError`` (404) for anything else, so a worker sends nothing anywhere on a foreign
name. The manager's lives in :mod:`the_loop.manager.facade` and wraps this one for the
manager's own state (R1.3).

:data:`LEFT_OUT` is the one piece of per-request state the seam needs: a list read on a
manager that could not reach every member still answers ``200`` with the rest, and the
route class turns whatever a facade left here into the
``The-Loop-Instances-Unreachable`` header (R2.9). The worker never writes it.
"""

from __future__ import annotations

import contextvars
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Dict, List, Optional, Sequence, Union

from ..cli_config import ConfigHolder
from ..core import attention as core_attention
from ..core import config as core_config
from ..core import daemons as core_daemons
from ..core import events as core_events
from ..core import graphs as core_graphs
from ..core import instance as core_instance
from ..core import instances as core_instances
from ..core import lifecycle as core_lifecycle
from ..core import repo as core_repo
from ..core import sessions as core_sessions
from ..core import standing as core_standing
from ..core import workitems as core_workitems

__all__ = ["LEFT_OUT", "PARTIAL_HEADER", "CoreFacade", "facade_for", "note_left_out"]

#: The response header naming the members a list read could not include (R2.9).
PARTIAL_HEADER = "The-Loop-Instances-Unreachable"

#: The members left out of the operation being served, set by a manager facade and
#: read by the route class after the handler returns. A context variable rather than an
#: attribute so two requests in the anyio threadpool never see each other's list.
LEFT_OUT: contextvars.ContextVar[Optional[List[str]]] = contextvars.ContextVar(
    "the_loop_left_out", default=None
)


def note_left_out(names: List[str]) -> None:
    """Record members a facade could not include, for the route class's header.

    The route runs the handler in a worker thread with a *copy* of the context, so
    a ``set`` there would not be seen back on the request; the list object the route
    class set is shared, so it is **extended** in place. Outside a request (the SDK,
    a test) there is no list, and the fact is dropped — it is carried by the
    ``instances`` document there.
    """
    bucket = LEFT_OUT.get()
    if bucket is None or not names:
        return
    for name in names:
        if name not in bucket:
            bucket.append(name)
    bucket.sort()


def _version() -> str:
    try:
        return version("the-loopy-one")
    except PackageNotFoundError:  # pragma: no cover — source checkout
        return "unknown"


class CoreFacade:
    """The worker's implementation: :mod:`the_loop.core`, one method per operation.

    Holds the :class:`~the_loop.cli_config.ConfigHolder` the router already refreshes
    once per request, so every method reads the config as it is *now*; ``config_path``
    is what the config routes read and write.
    """

    role = "worker"

    def __init__(self, holder: ConfigHolder) -> None:
        self.holder = holder
        self._broker: Any = None

    # -- helpers ----------------------------------------------------------------

    @property
    def config(self) -> dict:
        return self.holder.current

    @property
    def config_path(self):
        return self.holder.path

    def _self(self, instance: str) -> None:
        core_instance.assert_self(instance, self.config)

    # -- identity and health ----------------------------------------------------

    def health(self, instance: str = "") -> Dict[str, Any]:
        # Liveness, and whether this process is doing the job it was configured for
        # (issue-339). `status` is `degraded` — not `ok` — when an ingress the config
        # ENABLES holds no lock. The status CODE stays 200 while degraded: it answers
        # "did the service answer", which is what `client.healthy` measures and what
        # `ensure_service` loops on. `configPath`/`stateRoot` name the files this
        # process is actually using and escalate nothing: GET /api/v1/config already
        # serves the whole document across this boundary.
        from ..state import layout_from_config

        self._self(instance)
        config = self.config
        ingresses = core_lifecycle.ingress_health(config)
        degraded = any(row["enabled"] and not row["running"] for row in ingresses)
        return {
            "status": "degraded" if degraded else "ok",
            "version": _version(),
            "configPath": str(self.config_path),
            "stateRoot": str(layout_from_config(config).root),
            "ingresses": ingresses,
        }

    def get_instance(self, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_instance.describe_instance(self.config)

    def list_instances(self) -> Dict[str, Any]:
        return core_instances.list_instances(self.config)

    def register_instance(self, name: str, url: str) -> Dict[str, Any]:
        return core_instances.register_instance(
            self.config, name, url, config_path=self.config_path
        )

    def unregister_instance(self, name: str) -> Dict[str, Any]:
        return core_instances.unregister_instance(
            self.config, name, config_path=self.config_path
        )

    # -- work items ---------------------------------------------------------------

    def list_work_items(self) -> List[Dict[str, Any]]:
        return core_workitems.list_work_items(self.config)

    def get_work_item(self, ref: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_workitems.get_work_item(ref, self.config)

    # -- the config -----------------------------------------------------------------

    def get_config(self, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_config.get_config(self.config_path)

    def get_config_schema(self, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_config.get_schema()

    def update_config(self, patch: Dict[str, Any], instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        # The holder picks the new file up on the *next* request through the route
        # class, which is what makes a saved change live without a restart.
        return core_config.update_config(patch, self.config_path)

    # -- the graph ------------------------------------------------------------------

    def graph_show(
        self,
        repo: str,
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.show(repo, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir)

    def graph_check(
        self,
        repo: str,
        work_item: str,
        recompute: bool = False,
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.check(
            repo, work_item, recompute=recompute, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir
        )

    def graph_complete(
        self,
        repo: str,
        work_item: str,
        node: str = "",
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.complete(
            repo,
            work_item,
            node=node,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        )

    def graph_advance(
        self,
        repo: str,
        work_item: str,
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.advance(
            repo, work_item, ref=ref, pr=pr, pr_repo=pr_repo, spec_dir=spec_dir
        )

    def graph_force(
        self,
        repo: str,
        work_item: str,
        to_node: str,
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.force(
            repo,
            work_item,
            to_node,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        )

    def graph_skip(
        self,
        repo: str,
        work_item: str,
        nodes: List[str],
        reason: str,
        actor: str = "",
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.skip(
            repo,
            work_item,
            nodes,
            reason,
            actor=actor,
            ref=ref,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        )

    def graph_repos(
        self,
        repo: str,
        work_item: str,
        repositories: Optional[List[str]] = None,
        clear: bool = False,
        ref: str = "",
        pr: Optional[int] = None,
        pr_repo: str = "",
        spec_dir: str = "",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_graphs.repos(
            repo,
            work_item,
            repositories,
            ref=ref,
            clear=clear,
            pr=pr,
            pr_repo=pr_repo,
            spec_dir=spec_dir,
        )

    # -- sessions ---------------------------------------------------------------------

    def list_sessions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return core_sessions.list_sessions(status=status, config=self.config)

    def get_session(self, ref: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.get_session(ref, config=self.config)

    def session_transcript(
        self, ref: str, tail: int = 200, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.get_transcript(ref, tail=tail, config=self.config)

    def control_session(
        self, ref: str, verb: str, comment: bool = True, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.control_session(
            ref, verb, comment=comment, config=self.config
        )

    def reply_session(
        self,
        ref: str,
        text: str,
        actor: str = "",
        comment: bool = True,
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.reply_session(
            ref, text, actor=actor, comment=comment, config=self.config
        )

    def register_session(
        self,
        ref: str,
        harness: str,
        harness_session_id: str,
        cwd: str = ".",
        force: bool = False,
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.register_session(
            ref, harness, harness_session_id, cwd=cwd, force=force, config=self.config
        )

    def link_session_pull_request(
        self, ref: str, pull_request: str, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.link_pull_request(ref, pull_request, config=self.config)

    def close_session(
        self, ref: str, keep_tmux: Optional[bool] = None, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_sessions.close_session(
            ref, keep_tmux=keep_tmux, config=self.config
        )

    # -- standing sessions ----------------------------------------------------------

    def list_standing_sessions(self) -> List[Dict[str, Any]]:
        return core_standing.list_standing(config=self.config)

    def get_standing_session(self, name: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_standing.get_standing(name, config=self.config)

    def create_standing_session(
        self,
        name: str,
        harness: str = "",
        cwd: str = "",
        prompt: str = "",
        description: str = "",
        harness_args: Optional[List[str]] = None,
        slack_enabled: bool = False,
        slack_channel: str = "",
        auto_start: bool = True,
        start: bool = True,
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_standing.create_standing(
            name,
            harness=harness,
            cwd=cwd,
            prompt=prompt,
            description=description,
            harness_args=harness_args,
            slack_enabled=slack_enabled,
            slack_channel=slack_channel,
            auto_start=auto_start,
            start=start,
            config=self.config,
        )

    def delete_standing_session(self, name: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_standing.delete_standing(name, config=self.config)

    def control_standing_session(
        self, name: str, verb: str, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_standing.control_standing(name, verb, config=self.config)

    def say_to_standing_session(
        self, name: str, text: str, actor: str = "", instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_standing.say_standing(name, text, actor=actor, config=self.config)

    # -- events -------------------------------------------------------------------------

    def query_events(
        self,
        types: Sequence[str] = (),
        work_item: Optional[str] = None,
        delivery_id: Optional[str] = None,
        source: Optional[str] = None,
        min_level: Optional[str] = None,
        since: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return core_events.query_events(
            None,
            types=list(types),
            work_item=work_item,
            delivery_id=delivery_id,
            source=source,
            min_level=min_level,
            since=since,
            limit=limit,
        )

    def event_types(self) -> Dict[str, str]:
        return core_events.event_types()

    # -- daemons, restart, attention ----------------------------------------------

    def list_daemons(self) -> List[Dict[str, Any]]:
        return [
            core_daemons.daemon_status(name, self.config) for name in core_daemons.DAEMONS
        ]

    def control_daemon(self, daemon: str, verb: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_daemons.control_daemon(daemon, verb, self.config)

    def restart(self, with_upgrade: bool = False, instance: str = "") -> Dict[str, Any]:
        # Scheduling, not doing (issue-228, R4.4): this process is among what a
        # restart stops, so the work happens in a detached `the-loop restart` that
        # outlives it, and the response only promises the spawn.
        self._self(instance)
        return core_lifecycle.schedule_restart(
            self.config, with_upgrade=with_upgrade, config_path=self.config_path
        )

    def list_attention(self) -> List[Dict[str, Any]]:
        return core_attention.list_attention(self.config)

    # -- repo-scoped ----------------------------------------------------------------------

    def repo_scenarios(
        self, repo: str, globs: Optional[List[str]] = None, instance: str = ""
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_repo.scenarios(repo, globs=globs)

    def repo_instructions(
        self,
        repo: str,
        docs: Optional[List[str]] = None,
        on_missing: str = "warn",
        instance: str = "",
    ) -> Dict[str, Any]:
        self._self(instance)
        return core_repo.instructions(repo, docs=docs, on_missing=on_missing)

    def repo_critics(self, repo: str, instance: str = "") -> List[Dict[str, Any]]:
        self._self(instance)
        return core_repo.critics(repo)

    def repo_review_policy(self, repo: str, instance: str = "") -> Dict[str, Any]:
        self._self(instance)
        return core_repo.review_policy(repo)

    def repo_critic_run(
        self,
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
        self._self(instance)
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

    # -- the stream -------------------------------------------------------------------------

    def stream_broker(self):
        """The stream's broker, pointed at this config's event log — built once.

        Owned by the facade the ROUTER holds, not by the lifespan (issue-239): the
        router is the only thing that travels into an embedder's application, and a
        lifespan-owned broker would simply not exist for SDK consumers. It costs
        nothing to own it here: the tailer task starts with the first subscriber
        and stops with the last, so a service nobody is watching runs no task.
        The transcript resolver is injected so the path derivation stays in one
        place — ``core.sessions.transcript_path``, which owns the fail-closed rules
        issue-209 wrote.
        """
        if self._broker is None:
            from ..state import layout_from_config
            from .config import stream_config
            from .stream import StreamBroker

            conf = stream_config(self.config)

            def resolve(ref: str):
                # LookupError is the *normal* answer for a work item whose session
                # has not registered a conversation yet: the broker retries.
                try:
                    return core_sessions.transcript_path(ref, config=self.config)
                except (LookupError, ValueError):
                    return None

            self._broker = StreamBroker(
                layout_from_config(self.config or {}).event_log,
                max_subscribers=conf["maxSubscribers"],
                transcript_path=resolve,
            )
        return self._broker

    def parse_cursor(self, raw: Optional[str]):
        from .stream import parse_cursor

        return parse_cursor(raw)

    def serve_stream(self, broker, subscriber, cursor, keep_alive: int):
        from .stream import serve

        return serve(broker, subscriber, cursor=cursor, keep_alive=keep_alive)


def facade_for(holder: ConfigHolder) -> Any:
    """The facade for the role ``holder``'s config declares — chosen once, at boot.

    ``instance.role`` is boot-only (R1.4): the facade is what a manager *is*, and
    swapping it under live requests is not a reload anyone asked for. A manager is
    built over a :class:`CoreFacade` for its own state (R1.3).
    """
    identity = core_instance.instance_config(holder.current)
    core = CoreFacade(holder)
    if identity.is_manager:
        from ..manager.facade import ManagerFacade

        return ManagerFacade(holder, core)
    return core
