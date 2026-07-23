"""``the-loop gh-webhook start|stop`` — manage the GitHub webhook receiver.

Primary CLI: ``the-loop``; sub-command: ``gh-webhook``; actions: ``start`` / ``stop``.
Defaults can come from ``.the-loop/config.yaml`` (``webhooks.ghWebhook``) when PyYAML
is available; CLI flags always win. The secret is read from an env var (never a flag)
so it doesn't leak into process listings.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from .base import Command, register
from .. import eventlog
from ..webhook import serve

logger = logging.getLogger("the-loop.gh-webhook")

_CONFIG_PATH = Path(".the-loop/config.yaml")

_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8787,
    "path": "/gh-webhook",
    "secretEnv": "THE_LOOP_GH_WEBHOOK_SECRET",
    "pidfile": ".the-loop/gh-webhook.pid",
}


def _read_gh_webhook_config(strict: bool = False) -> dict:
    """Read ``webhooks.ghWebhook`` from ``.the-loop/config.yaml``.

    ``strict=False`` (defaults path): returns ``{}`` when the file or PyYAML is
    unavailable or unparseable — the CLI must work with zero runtime deps.
    ``strict=True`` (hot-reload path): raises on a missing file / missing PyYAML
    / parse error, so the :class:`Reloader` keeps the previously loaded config
    instead of resetting to defaults on a transient broken save.
    """
    if not _CONFIG_PATH.is_file():
        if strict:
            raise FileNotFoundError(f"{_CONFIG_PATH} not found")
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        if strict:
            raise
        logger.debug("pyyaml not installed; skipping config-file defaults")
        return {}
    text = _CONFIG_PATH.read_text()
    if strict:
        data = yaml.safe_load(text) or {}  # let a YAMLError propagate
    else:
        try:
            data = yaml.safe_load(text) or {}
        except Exception:  # noqa: BLE001
            logger.warning("could not parse %s; using built-in defaults", _CONFIG_PATH)
            return {}
    return ((data.get("webhooks") or {}).get("ghWebhook")) or {}


def _load_config_defaults() -> dict:
    """Best-effort read of webhooks.ghWebhook (never raises)."""
    return _read_gh_webhook_config(strict=False)


def _ticketing_owner() -> Optional[str]:
    """``ticketing.github.owner`` — the fallback authorized user (or ``None``)."""
    if not _CONFIG_PATH.is_file():
        return None
    try:
        import yaml  # optional dependency
    except ImportError:
        return None
    try:
        data = yaml.safe_load(_CONFIG_PATH.read_text()) or {}
    except Exception:  # noqa: BLE001
        return None
    owner = ((data.get("ticketing") or {}).get("github") or {}).get("owner")
    return str(owner) if owner else None


def _build_routing(gh_webhook_config: dict, owner: Optional[str] = None):
    """Compose router + dispatcher into the server's on_event callback.

    Spec: docs/specs/issue-15/design.md §6. Imported lazily-ish here (module
    level is fine — everything is stdlib) and returned with the dispatcher so
    `start` can drain it on shutdown. ``owner`` is ``ticketing.github.owner``,
    the fallback authorized user (prompt-injection guard, issue-34 review).
    """
    from ..authz import resolve_authorized_users
    from ..harness import build_adapters
    from ..reload import Reloader
    from ..sessions import SessionRegistry
    from ..webhook.dispatcher import Dispatcher, RoutingConfig
    from ..webhook.router import Router

    config = RoutingConfig.from_mapping(gh_webhook_config.get("routing") or {})
    dispatcher = Dispatcher(
        registry=SessionRegistry(config.registry_dir),
        adapters=build_adapters(config.harness_args),
        config=config,
    )
    authorized = resolve_authorized_users(config.authorized_users, owner)
    if not authorized:
        logger.warning(
            "no authorizedUsers configured (and no ticketing.github.owner) — the "
            "receiver will act on NO human-authored events until you set "
            "webhooks.ghWebhook.routing.authorizedUsers (prompt-injection guard)"
        )
    # The router shares the dispatcher's deduper: the dispatcher marks processed
    # delivery ids, the router drops duplicates before extraction.
    router = Router(
        events=gh_webhook_config.get("events") or [],
        deduper=dispatcher.deduper,
        auto_execute_label=config.auto_execute_label,
        authorized_users=authorized,
    )

    def apply(gh_cfg: dict) -> None:
        """Hot-swap the soft routing policy from a freshly read config."""
        new = RoutingConfig.from_mapping(gh_cfg.get("routing") or {})
        dispatcher.reload(new)
        router.events = list(gh_cfg.get("events") or [])
        router.auto_execute_label = new.auto_execute_label
        router.authorized_users = resolve_authorized_users(new.authorized_users, owner)
        logger.info(
            "hot-reloaded gh-webhook routing: spawnOnUnmatched=%s runner=%s "
            "label=%r events=%d authorizedUsers=%d",
            new.spawn_on_unmatched,
            new.runner,
            new.auto_execute_label,
            len(router.events),
            len(router.authorized_users),
        )
        eventlog.emit(
            "config.reloaded",
            detail=(
                f"gh-webhook routing: spawnOnUnmatched={new.spawn_on_unmatched} "
                f"runner={new.runner} events={len(router.events)} "
                f"authorizedUsers={len(router.authorized_users)}"
            ),
        )

    # Re-read the config file on each event and hot-swap soft policy on change
    # (a bad edit is logged and the previous config kept). Bind/secret, the web
    # terminal and the dispatcher's threads/dedup/registry are start-time only.
    reloader = Reloader(_CONFIG_PATH, lambda: _read_gh_webhook_config(strict=True))
    reload_lock = threading.Lock()

    def on_event(event: str, payload: dict, delivery_id: str) -> None:
        # One thread reloads at a time; others skip and pick it up next event
        # (the ThreadingHTTPServer handles events concurrently).
        if reload_lock.acquire(blocking=False):
            try:
                changed = reloader.poll_for_change()
                if changed is not None:
                    apply(changed)
            finally:
                reload_lock.release()
        routed = router.route(event, payload, delivery_id)
        if routed is not None:
            dispatcher.handle(routed)

    logger.info(
        "routing enabled: registry=%s defaultHarness=%s spawnOnUnmatched=%s runner=%s "
        "(routing config hot-reloads on change)",
        config.registry_dir,
        config.default_harness,
        config.spawn_on_unmatched,
        config.runner,
    )
    return on_event, dispatcher, config


@register
class GhWebhookCommand(Command):
    name = "gh-webhook"
    help = "Manage the GitHub webhook receiver server (start/stop)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        defaults = {**_DEFAULTS, **_load_config_defaults()}
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        routing_defaults = defaults.get("routing") or {}
        start = actions.add_parser("start", help="Start the webhook receiver")
        start.add_argument("--host", default=defaults["host"])
        start.add_argument("--port", type=int, default=int(defaults["port"]))
        start.add_argument("--path", default=defaults["path"])
        start.add_argument(
            "--route",
            action=argparse.BooleanOptionalAction,
            default=bool(routing_defaults.get("enabled", False)),
            help="Route events to registered harness sessions "
            "(default: webhooks.ghWebhook.routing.enabled).",
        )
        start.add_argument(
            "--pidfile",
            default=defaults["pidfile"],
            help="Where to record the server PID (for `stop`).",
        )
        start.add_argument(
            "--secret-env",
            default=defaults["secretEnv"],
            help="Env var holding the GitHub webhook secret (HMAC verification).",
        )
        start.set_defaults(_action=self._start)

        stop = actions.add_parser("stop", help="Stop a running webhook receiver")
        stop.add_argument("--pidfile", default=defaults["pidfile"])
        stop.set_defaults(_action=self._stop)

    def run(self, args: argparse.Namespace) -> int:
        return int(args._action(args) or 0)

    # -- actions ---------------------------------------------------------------

    def _start(self, args: argparse.Namespace) -> int:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        eventlog.configure_from_file("gh-webhook")
        secret = os.environ.get(args.secret_env)
        if not secret:
            logger.warning(
                "no webhook secret in $%s — signatures will NOT be verified",
                args.secret_env,
            )

        from ..runner import check_dependencies, start_web_terminal, stop_web_terminal

        on_event = dispatcher = web_proc = None
        if args.route:
            on_event, dispatcher, routing_config = _build_routing(
                _load_config_defaults(), owner=_ticketing_owner()
            )
            missing = check_dependencies(
                routing_config.runner, routing_config.web_terminal.enabled
            )
            if missing:  # R6.1: fail with per-platform guidance; R6.2: else silent
                for line in missing:
                    logger.error(line)
                return 1
            if routing_config.web_terminal.enabled:
                web_proc = start_web_terminal(routing_config.web_terminal)

        try:
            httpd = serve(
                host=args.host,
                port=args.port,
                path=args.path,
                secret=secret,
                on_event=on_event,
            )
        except OSError as exc:
            logger.error("could not bind %s:%s — %s", args.host, args.port, exc)
            stop_web_terminal(web_proc)
            return 1

        pidfile = Path(args.pidfile)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(os.getpid()))

        def _shutdown(signum, _frame):
            logger.info("received signal %s, shutting down", signum)
            httpd.shutdown()

        signal.signal(signal.SIGTERM, _shutdown)
        signal.signal(signal.SIGINT, _shutdown)

        logger.info(
            "gh-webhook listening on http://%s:%s%s (pidfile=%s)",
            args.host,
            args.port,
            args.path,
            pidfile,
        )
        eventlog.emit(
            "server.started",
            host=args.host,
            port=args.port,
            path=args.path,
            routing=bool(args.route),
            verifying_signatures=bool(secret),
        )
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
            if dispatcher is not None:
                dispatcher.stop()
            stop_web_terminal(web_proc)
            eventlog.emit("server.stopped", host=args.host, port=args.port)
            try:
                pidfile.unlink()
            except FileNotFoundError:
                pass
        return 0

    def _stop(self, args: argparse.Namespace) -> int:
        pidfile = Path(args.pidfile)
        if not pidfile.is_file():
            print(f"no pidfile at {pidfile}; is the server running?", file=sys.stderr)
            return 1
        try:
            pid = int(pidfile.read_text().strip())
        except ValueError:
            print(f"pidfile {pidfile} is corrupt", file=sys.stderr)
            return 1
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            print(f"process {pid} not running; removing stale pidfile", file=sys.stderr)
            pidfile.unlink(missing_ok=True)
            return 1
        print(f"sent SIGTERM to gh-webhook server (pid {pid})")
        return 0
