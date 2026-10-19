"""The gateway's ingresses as a set that follows ``gateway-config.yaml`` (issue-496,
R1.1, R1.6, R8.4, R8.5, R8.6).

Reuses the control-plane service's supervisor (``api/ingress.py``): the same
``_HostedIngress`` (a lock, a thread, a way to stop), the same ``_host`` discipline (a
loop that ends on its own releases its lock and records ``ingress.hosted_failed``), the
same ``Reloader`` (a content hash every five seconds; an unloadable file keeps the
previous value). What differs is the table of starters — ``slack-socket``,
``github-poll``, ``jira-poll``; the HTTP routes are app routes, enabled or 404 by config,
so they need no thread — and the predicate: the gateway config's own ``enabled`` flags.

A reload applies membership (start what is newly enabled, stop what no longer is) and
records ``gateway.reloaded``; a bad edit records ``config.reload-failed`` and changes
nothing (R8.5). The listen address and the Slack tokens are start-time only: when the
file's values differ from the running ones, ``restart_required`` names them for
``gateway status`` (R8.6).
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import eventlog
from ..api.ingress import (
    RECONCILE_INTERVAL_SECONDS,
    HostedIngresses,
    _acquire,
    _host,
    _HostedIngress,
)
from ..reload import Reloader
from .adapters.ingest import Ingest
from .config import ConfigError, GatewayConfig, load_gateway_config
from .consume import GatewayState

__all__ = ["GatewayIngresses", "enabled_ingresses", "restart_required"]

logger = logging.getLogger("the-loop.gateway.ingresses")

_Start = Tuple[Optional[_HostedIngress], str]


def enabled_ingresses(config: GatewayConfig) -> Dict[str, bool]:
    """What the config enables, by ingress name — the HTTP routes included, for health."""
    github = config.github
    jira = config.jira
    slack = config.slack
    return {
        "gh-webhook": bool(github and github.webhook.enabled),
        "jira-webhook": bool(jira and jira.webhook.enabled),
        "slack-http": bool(slack and slack.http.enabled),
        "slack-socket": bool(slack and slack.socket.enabled),
        "github-poll": bool(github and github.poll.enabled and github.poll.sources),
        "jira-poll": bool(jira and jira.poll.enabled and jira.projects),
    }


def restart_required(running: GatewayConfig, fresh: GatewayConfig) -> List[str]:
    """The start-time-only keys whose values differ between the running config and the
    file (R8.6)."""
    keys: List[str] = []
    if running.listen != fresh.listen:
        keys.append("listen")
    old_slack = running.slack.socket if running.slack else None
    new_slack = fresh.slack.socket if fresh.slack else None
    old_tokens = (
        (old_slack.app_token_env, old_slack.bot_token_env) if old_slack else None
    )
    new_tokens = (
        (new_slack.app_token_env, new_slack.bot_token_env) if new_slack else None
    )
    if old_tokens != new_tokens:
        keys.append("slack.socket tokens")
    if running.state_root != fresh.state_root or running.store.path != fresh.store.path:
        keys.append("state.root / store.path")
    return keys


class GatewayIngresses(HostedIngresses):
    """The threaded ingresses of one gateway process, hot-reloaded from its config."""

    def __init__(
        self,
        state: GatewayState,
        *,
        interval: float = RECONCILE_INTERVAL_SECONDS,
        socket_factory: Optional[Callable[..., Any]] = None,
        poll_api: Any = None,
    ) -> None:
        # The parent's __init__ builds a CLI-config reloader; this one follows the
        # gateway's own file, so the fields are set here directly.
        self.state = state
        self.ingest = Ingest(state)
        self.config: Any = state.config
        self.path = Path(state.config.path)
        self.interval = float(interval)
        self._hosted: List[_HostedIngress] = []
        self._lock = threading.RLock()
        self._stopping = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self._socket_factory = socket_factory
        self._poll_api = poll_api
        self.adapters: Dict[str, Any] = {}
        self._reloader = Reloader(self.path, self._load)  # type: ignore[assignment]

    # -- the reloader's build: a bad edit is recorded and keeps the previous config ----------

    def _load(self) -> GatewayConfig:
        try:
            return load_gateway_config(self.path)
        except ConfigError as exc:
            eventlog.emit(
                "config.reload-failed",
                level="error",
                path=str(self.path),
                error="; ".join(exc.errors)[:500],
            )
            raise

    # -- starters -------------------------------------------------------------------------------

    def _starters(self) -> List[Tuple[str, Callable[[GatewayConfig], _Start]]]:
        return [
            ("slack-socket", self._start_slack_socket),
            ("github-poll", self._start_github_poll),
            ("jira-poll", self._start_jira_poll),
        ]

    def _wanted_names(self, config: GatewayConfig) -> List[str]:
        enabled = enabled_ingresses(config)
        return [name for name, _ in self._starters() if enabled.get(name)]

    def _lockfile(self, name: str) -> str:
        return str(self.state.config.state_root / "locks" / f"{name}.pid")

    def _start_slack_socket(self, config: GatewayConfig) -> _Start:
        from .adapters.slack_socket import SlackSocketAdapter, slack_tokens

        if slack_tokens(config) is None:
            assert config.slack is not None
            return None, (
                "missing-secret: "
                f"{config.slack.socket.app_token_env} and {config.slack.socket.bot_token_env}"
            )
        lock, reason = _acquire("slack-socket", self._lockfile("slack-socket"))
        if lock is None:
            return None, reason
        adapter = SlackSocketAdapter(
            self.ingest, config, client_factory=self._socket_factory, watch=None
        )
        stop_event = threading.Event()

        def run() -> None:
            if not adapter.start():
                raise RuntimeError("Slack Socket Mode did not start")
            self.state.slack_socket = "up"
            stop_event.wait()
            adapter.stop()
            self.state.slack_socket = "off"

        self.adapters["slack-socket"] = adapter
        return _host("slack-socket", lock, run, stop_event.set), ""

    def _start_poll(self, name: str, config: GatewayConfig, build) -> _Start:
        from .adapters.poll import PollAdapter

        try:
            providers = build(config)
        except Exception as exc:  # noqa: BLE001 — a provider that cannot be built
            return None, f"cannot build the {name} providers: {exc}"
        if not providers:
            return None, "no sources"
        lock, reason = _acquire(name, self._lockfile(name))
        if lock is None:
            return None, reason
        interval = (
            config.github.poll.interval_seconds
            if name == "github-poll" and config.github
            else (config.jira.poll.interval_seconds if config.jira else 60)
        )
        adapters = [
            PollAdapter(
                p, self.ingest, interval_s=interval, provider_name=name.split("-", 1)[0]
            )
            for p in providers
        ]
        stop_event = threading.Event()

        def run() -> None:
            for adapter in adapters:
                adapter.start()
            stop_event.wait()
            for adapter in adapters:
                adapter.stop()

        self.adapters[name] = adapters
        return _host(name, lock, run, stop_event.set), ""

    def _start_github_poll(self, config: GatewayConfig) -> _Start:
        from .adapters.poll import build_github_providers

        if config.github is not None and not os.environ.get(
            config.github.poll.token_env
        ):
            return None, f"missing-secret: {config.github.poll.token_env}"
        return self._start_poll(
            "github-poll",
            config,
            lambda c: build_github_providers(c, api=self._poll_api),
        )

    def _start_jira_poll(self, config: GatewayConfig) -> _Start:
        from .adapters.poll import build_jira_providers

        return self._start_poll("jira-poll", config, build_jira_providers)

    # -- start / reconcile -------------------------------------------------------------------------

    def _start_one(
        self, name: str, config: GatewayConfig, *, why: str
    ) -> Optional[_HostedIngress]:
        start = dict(self._starters())[name]
        try:
            ingress, reason = start(config)
        except Exception as exc:  # noqa: BLE001 — one ingress must not take the gateway down
            logger.exception("gateway: hosting the %s failed (%s)", name, why)
            ingress, reason = None, str(exc) or exc.__class__.__name__
        if ingress is not None:
            logger.info("gateway: hosting the %s (%s)", name, why)
            eventlog.emit("ingress.hosted", ingress=name, reason=why)
            self.state.ingresses[name] = "running"
            return ingress
        eventlog.emit(
            "ingress.hosted_failed",
            level="error",
            ingress=name,
            reason=reason or "unknown",
        )
        self.state.ingresses[name] = f"failed:{(reason or 'unknown').split(':', 1)[0]}"
        return None

    def _refresh_states(self, config: GatewayConfig) -> None:
        enabled = enabled_ingresses(config)
        running = {h.name for h in self._hosted if h.thread.is_alive()}
        for name, on in enabled.items():
            if not on:
                self.state.ingresses[name] = "off"
            elif name in ("gh-webhook", "jira-webhook", "slack-http"):
                self.state.ingresses[name] = "running"
            elif name in running:
                self.state.ingresses[name] = "running"
            elif not str(self.state.ingresses.get(name, "")).startswith("failed"):
                self.state.ingresses[name] = "off"

    def start(self) -> None:
        with self._lock:
            config = self.state.config
            self._hosted = []
            for name in self._wanted_names(config):
                ingress = self._start_one(name, config, why="startup")
                if ingress is not None:
                    self._hosted.append(ingress)
            self._refresh_states(config)
        self._stopping.clear()
        self.thread = threading.Thread(
            target=self._supervise, name="the-loop-gateway-supervisor", daemon=True
        )
        self.thread.start()

    def reconcile(self, config: Any) -> None:
        """Apply a re-read config: membership changes and the restart-required list."""
        fresh: GatewayConfig = config
        with self._lock:
            if self._stopping.is_set():
                return
            running = self.state.config
            self.state.restart_required = restart_required(running, fresh)
            # start-time-only values keep running as they were; everything else is live
            applied = GatewayConfig(
                path=fresh.path,
                state_root=running.state_root,
                listen=running.listen,
                store=running.store,
                consume=fresh.consume,
                repositories=fresh.repositories,
                github=fresh.github,
                jira=fresh.jira,
                slack=fresh.slack,
                instances=fresh.instances,
                event_log=running.event_log,
                event_log_enabled=running.event_log_enabled,
                env_file=fresh.env_file,
                version=fresh.version,
            )
            self.state.config = applied
            self.config = applied
            wanted = self._wanted_names(applied)
            alive = [h for h in self._hosted if h.thread.is_alive()]
            stopped: List[str] = []
            for ingress in reversed([h for h in alive if h.name not in wanted]):
                ingress.stop(reason="config")
                stopped.append(ingress.name)
                self.adapters.pop(ingress.name, None)
            keep = [h for h in alive if h.name in wanted]
            started: List[str] = []
            for name in wanted:
                if any(h.name == name for h in keep):
                    continue
                ingress = self._start_one(name, applied, why="config")
                if ingress is not None:
                    keep.append(ingress)
                    started.append(name)
            self._hosted = keep
            self._refresh_states(applied)
            detail = {
                "started": started,
                "stopped": stopped,
                "restartRequired": list(self.state.restart_required),
            }
            eventlog.emit("config.reloaded", detail=detail)
            eventlog.emit("gateway.reloaded", detail=detail)
