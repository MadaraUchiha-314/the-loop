"""The gateway process (issue-496, R1.1, R9.1, R14.2, R14.3).

Mirrors ``api/serve.py``: load the env file the config names, load and validate the
config (exit 2 naming each path on a violation), refuse a non-loopback bind without
``listen.exposed`` (exit 2 — the instance-to-gateway boundary carries no authentication,
so the network is the boundary), take the pidfile lock (exit 1 when another gateway holds
it), configure the event log with ``source="gateway"``, and serve the FastAPI app with
uvicorn. ``create_app`` mounts the ingress routes and the consumer API and starts the
threaded ingresses and the retention timer in the lifespan.

``python -m the_loop.gateway.serve [--config PATH]`` is the foreground entry point a
supervisor runs; ``the-loop gateway start`` spawns it detached.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from .. import eventlog
from ..api.config import is_loopback
from ..runlock import RunLock
from .config import (
    ConfigError,
    GatewayConfig,
    load_gateway_config,
    load_gateway_env_file,
)
from .consume import GatewayState, mount
from .store import SqliteStore

__all__ = ["RETENTION_INTERVAL_S", "create_app", "main"]

logger = logging.getLogger("the-loop.gateway")

RETENTION_INTERVAL_S = 3600.0
#: Open requests uvicorn serves at once before answering 503 (SEC-5).
LIMIT_CONCURRENCY = 256


def _retention_loop(
    state: GatewayState, stop: threading.Event, interval: float
) -> None:
    while True:
        try:
            result = state.store.expire()
            for subject, event_id, instance in result.expired:
                eventlog.emit(
                    "subject.expired",
                    level="warning",
                    subject=subject,
                    event_id=event_id,
                    instance=instance or None,
                )
            if result.pruned_instances or result.pruned_subjects:
                logger.info(
                    "gateway: retention pruned %d lapsed instance(s) %s and %d empty subject(s)",
                    len(result.pruned_instances),
                    list(result.pruned_instances),
                    result.pruned_subjects,
                )
        except Exception:  # noqa: BLE001 — retention never ends the process
            logger.exception("gateway: retention pass failed")
            state.store_ok = False
        else:
            state.store_ok = True
        if stop.wait(interval):
            return


def create_app(
    config: GatewayConfig,
    *,
    store: Optional[SqliteStore] = None,
    host_ingresses: bool = True,
    retention_interval: float = RETENTION_INTERVAL_S,
    **ingress_kwargs: Any,
) -> Any:
    """The gateway's FastAPI app. ``host_ingresses=False`` serves the routes alone (what
    a contract test wants); ``ingress_kwargs`` reach :class:`GatewayIngresses`."""
    from fastapi import FastAPI

    from .adapters.github import build_github_router
    from .adapters.ingest import Ingest
    from .adapters.jira import build_jira_router
    from .adapters.slack_http import build_slack_http_router
    from .ingresses import GatewayIngresses, enabled_ingresses

    store = store or SqliteStore(
        config.store.path,
        retention_days=config.store.retention_days,
        max_attempts=config.store.max_attempts,
        dedup_window=config.store.dedup_window,
    )
    state = GatewayState(config, store)
    state.ingresses = {
        name: ("running" if on else "off")
        for name, on in enabled_ingresses(config).items()
    }
    ingresses: Optional[GatewayIngresses] = None
    stop_retention = threading.Event()

    @asynccontextmanager
    async def lifespan(_app: Any):
        nonlocal ingresses
        retention = threading.Thread(
            target=_retention_loop,
            args=(state, stop_retention, retention_interval),
            name="the-loop-gateway-retention",
            daemon=True,
        )
        retention.start()
        if host_ingresses:
            ingresses = GatewayIngresses(state, **ingress_kwargs)
            ingresses.start()
        try:
            yield
        finally:
            state.stopping.set()
            state.store.wake_all()
            stop_retention.set()
            if ingresses is not None:
                ingresses.stop()

    app = FastAPI(
        title="the-loop gateway",
        version="1",
        description="One ingress, many instances: the gateway's provider routes and consumer API (issue-496).",
        lifespan=lifespan,
    )
    ingest = Ingest(state)
    app.include_router(build_github_router(ingest, config))
    app.include_router(build_jira_router(ingest, config))
    app.include_router(build_slack_http_router(ingest, config))
    mount(app, state)
    app.state.gateway_ingresses = lambda: ingresses
    app.state.gateway_state = state
    return app


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(prog="the-loop gateway serve")
    parser.add_argument("--config", "-c", default=None)
    args = parser.parse_args(argv)
    load_gateway_env_file(args.config)
    try:
        config = load_gateway_config(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 2
    if not is_loopback(config.listen.host) and not config.listen.exposed:
        logger.error(
            "refusing to bind %s: set listen.exposed: true to serve beyond loopback — "
            "an exposed gateway is readable, claimable and committable by any peer on "
            "that network (no instance authentication in this release)",
            config.listen.host,
        )
        print(
            f"refusing to bind {config.listen.host}: set listen.exposed: true to serve "
            "beyond loopback",
            file=sys.stderr,
        )
        return 2
    config.state_root.mkdir(parents=True, exist_ok=True)
    lock = RunLock(str(config.pidfile), name="gateway")
    if not lock.acquire():
        print(
            f"another gateway is already running (pid {lock.holder()})", file=sys.stderr
        )
        return 1
    eventlog.configure(
        "gateway",
        path=config.event_log or config.state_root / "logs" / "events.jsonl",
        enabled=config.event_log_enabled,
    )
    app = create_app(config)
    try:
        config.listen_file.write_text(
            f"{config.listen.host}:{config.listen.port}\n", encoding="utf-8"
        )
    except OSError as exc:  # the verbs then fall back to the file's values
        logger.warning("gateway: cannot record the listen address (%s)", exc)
    from .ingresses import enabled_ingresses

    eventlog.emit(
        "gateway.started",
        listen=f"{config.listen.host}:{config.listen.port}",
        store=str(config.store.path),
        ingresses=[n for n, on in enabled_ingresses(config).items() if on],
    )
    # uvicorn captures SIGTERM/SIGINT for its graceful shutdown, then restores the
    # handlers it found and re-raises the signal. With the default handler that ends the
    # process before this function's cleanup runs; raising SystemExit instead unwinds
    # through the `finally`, so `gateway.stopped` is recorded and the pidfile released.
    _install_exit_handlers()
    code = 0
    try:
        import uvicorn

        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=config.listen.host,
                port=config.listen.port,
                log_level="info",
                # beyond this many open requests uvicorn answers 503 at once rather
                # than queueing them on the worker pool (security review SEC-5)
                limit_concurrency=LIMIT_CONCURRENCY,
            )
        )
        # uvicorn's graceful stop waits for open requests, and a fetch may be holding
        # a long-poll for `consume.maxWaitSeconds`: release them the moment uvicorn
        # decides to exit, so a stop outlasts no long-poll (R8.5).
        _release_long_polls_on_exit(server, app.state.gateway_state)
        server.run()
    except SystemExit as exc:
        code = int(exc.code or 0) if isinstance(exc.code, int) else 0
    finally:
        eventlog.emit("gateway.stopped", reason="shutdown")
        try:
            config.listen_file.unlink()
        except OSError:
            pass
        lock.release()
    return code


def _release_long_polls_on_exit(server: Any, state: Any) -> None:
    def watch() -> None:
        while not getattr(server, "should_exit", False):
            time.sleep(0.1)
        state.stopping.set()
        state.store.wake_all()

    threading.Thread(target=watch, name="the-loop-gateway-exit", daemon=True).start()


def _install_exit_handlers() -> None:
    def _exit(signum: int, _frame: Any) -> None:
        raise SystemExit(0)

    try:
        import signal

        signal.signal(signal.SIGTERM, _exit)
        signal.signal(signal.SIGINT, _exit)
    except (ValueError, OSError):  # not the main thread, or no signals here
        return


if __name__ == "__main__":
    sys.exit(main())
