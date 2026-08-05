"""``the-loop gh-webhook start|stop`` — manage the GitHub webhook receiver.

Primary CLI: ``the-loop``; sub-command: ``gh-webhook``; actions: ``start`` / ``stop``.
Defaults can come from the CLI config (``webhooks.ghWebhook``; see
``the_loop.cli_config`` for the ``cli-config.yaml`` resolution order — ``--config``,
then ``$THE_LOOP_CLI_CONFIG``, then ``./.the-loop/cli-config.yaml``, then
``~/.the-loop/cli-config.yaml``, decision-032); CLI flags always win. The secret is
read from an env var (never a flag) so it doesn't leak into process listings.

``webhooks.ghWebhook`` is the *receiver's* half only — the HTTP listener, its pid
and its event filter. What happens to an event once accepted is the top-level
``routing`` block (issue-142), read here through
:func:`the_loop.cli_config.load_routing_config` because the poller dispatches on
exactly the same values.
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from .base import Command, register
from .. import cli_config, eventlog
from ..state import StateLayout, layout_from_config
from ..webhook import serve

logger = logging.getLogger("the-loop.gh-webhook")

# The CLI config (webhooks/polling/eventLog). Deliberately the ONLY config
# source the receiver reads (issue-63 review): which GitHub logins may
# trigger it is a CLI-config concern, not the repo-local plugin config's.
_CONFIG_PATH = cli_config.default_cli_config_path()


def _state_layout() -> StateLayout:
    """``state.root`` from the CLI config — the root of everything generated."""
    return layout_from_config(cli_config.load_cli_config(_CONFIG_PATH))


_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8787,
    "path": "/gh-webhook",
    "secretEnv": "THE_LOOP_GH_WEBHOOK_SECRET",
}

# The events the-loop can actually map to a work item (``extract_work_items``),
# used when ``events`` is unset. Anything outside this set can never resolve to
# one, so naming them is the previous "empty = accept all" behaviour said out
# loud — with the difference that matters: `issues` and `pull_request` are in
# the default, so a work item ending always reaches the receiver (issue-94).
DEFAULT_EVENTS = [
    "issues",
    "issue_comment",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "workflow_run",
    "check_run",
    "check_suite",
    "status",
]

# Without these, a closed issue or a merged/closed PR never reaches the receiver
# and its session is never auto-closed — the leak issue-94 fixed. An explicit
# `events` list that drops them is almost always an oversight, so say so.
_LIFECYCLE_EVENTS = ("issues", "pull_request")


def resolve_events(gh_webhook_config: dict) -> list:
    """The event filter to run with: the configured list, else the default set."""
    configured = [str(e) for e in (gh_webhook_config.get("events") or []) if e]
    return configured or list(DEFAULT_EVENTS)


def warn_on_missing_lifecycle_events(events) -> list:
    """Warn when the event filter cannot see a work item ending. Returns the missing."""
    missing = [event for event in _LIFECYCLE_EVENTS if event not in events]
    if missing:
        logger.warning(
            "webhooks.ghWebhook.events omits %s — a closed issue / merged PR will "
            "never reach the receiver, so its session stays open (and its tmux "
            "session with it). Add %s to the list, or drop the list entirely to "
            "use the default set.",
            ", ".join(missing),
            ", ".join(missing),
        )
    return missing


def _read_gh_webhook_config(strict: bool = False) -> dict:
    """Read ``webhooks.ghWebhook`` from the CLI config (``_CONFIG_PATH``).

    ``strict=False`` (defaults path): returns ``{}`` when the file is missing or
    unparseable, so a half-saved hand edit never breaks ingress.
    ``strict=True`` (hot-reload path): raises on a missing file / parse error, so
    the :class:`Reloader` keeps the previously loaded config instead of resetting
    to defaults on a transient broken save.
    """
    data = cli_config.load_cli_config(_CONFIG_PATH, strict=strict)
    return ((data.get("webhooks") or {}).get("ghWebhook")) or {}


def _load_config_defaults() -> dict:
    """Best-effort read of webhooks.ghWebhook (never raises)."""
    return _read_gh_webhook_config(strict=False)


def _build_routing(routing_config: dict, gh_webhook_config: dict):
    """Compose router + dispatcher into the server's on_event callback.

    Takes the two blocks separately, because they are two concerns: the shared
    top-level ``routing`` policy, and the receiver's own event filter
    (issue-142). Spec: docs/specs/issue-15/design.md §6. Imported lazily-ish here
    (module level is fine — everything is stdlib) and returned with the
    dispatcher so `start` can drain it on shutdown.
    """
    from ..authz import resolve_authorized_users
    from ..harness import build_adapters
    from ..reload import Reloader
    from ..sessions import SessionRegistry
    from ..webhook.dispatcher import Dispatcher, RoutingConfig
    from ..webhook.router import Router

    layout = _state_layout()
    config = RoutingConfig.from_mapping(routing_config or {}, layout)
    dispatcher = Dispatcher(
        registry=SessionRegistry(config.registry_dir),
        adapters=build_adapters(
            config.harness_args, config.harness_trust, config.harness_plugins
        ),
        config=config,
    )
    authorized = resolve_authorized_users(config.authorized_users)
    if not authorized:
        logger.warning(
            "no authorizedUsers configured — the receiver will act on NO "
            "human-authored events until you set routing.authorizedUsers in the "
            "CLI config (prompt-injection guard)"
        )
    # The router shares the dispatcher's deduper: the dispatcher marks processed
    # delivery ids, the router drops duplicates before extraction.
    events = resolve_events(gh_webhook_config)
    warn_on_missing_lifecycle_events(events)
    router = Router(
        events=events,
        deduper=dispatcher.deduper,
        auto_execute_label=config.auto_execute_label,
        authorized_users=authorized,
    )

    def apply(cfg: dict) -> None:
        """Hot-swap the soft routing policy from a freshly read config.

        Takes the whole document: since issue-142 the dispatch policy and the
        receiver's event filter live in different top-level blocks.
        """
        gh_cfg = ((cfg.get("webhooks") or {}).get("ghWebhook")) or {}
        new = RoutingConfig.from_mapping(cfg.get("routing") or {}, layout)
        dispatcher.reload(new)
        router.events = resolve_events(gh_cfg)
        warn_on_missing_lifecycle_events(router.events)
        router.auto_execute_label = new.auto_execute_label
        router.authorized_users = resolve_authorized_users(new.authorized_users)
        logger.info(
            "hot-reloaded gh-webhook routing: spawnOnUnmatched=%s "
            "label=%r events=%d authorizedUsers=%d",
            new.spawn_on_unmatched,
            new.auto_execute_label,
            len(router.events),
            len(router.authorized_users),
        )
        eventlog.emit(
            "config.reloaded",
            detail=(
                f"gh-webhook routing: spawnOnUnmatched={new.spawn_on_unmatched} "
                f"events={len(router.events)} "
                f"authorizedUsers={len(router.authorized_users)}"
            ),
        )

    # Re-read the config file on each event and hot-swap soft policy on change
    # (a bad edit is logged and the previous config kept). Bind/secret, the web
    # terminal and the dispatcher's threads/dedup/registry are start-time only.
    reloader = Reloader(
        _CONFIG_PATH, lambda: cli_config.load_cli_config(_CONFIG_PATH, strict=True)
    )
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
        "routing enabled: registry=%s defaultHarness=%s spawnOnUnmatched=%s "
        "requireStartCommand=%s (routing config hot-reloads on change)",
        config.registry_dir,
        config.default_harness,
        config.spawn_on_unmatched,
        config.control.require_start_command and config.control.enabled,
    )
    if config.control.enabled and config.control.require_start_command:
        logger.info(
            "the auto-execute label arms a work item; an authorized user starts "
            "it by commenting %r (or running `the-loop sessions start`) — set "
            "routing.control.requireStartCommand: false for the pre-issue-106 "
            "label-alone behaviour",
            config.control.keyword("start"),
        )
    return on_event, dispatcher, config


@register
class GhWebhookCommand(Command):
    name = "gh-webhook"
    help = "Manage the GitHub webhook receiver server (start/stop)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        # The pidfile default comes from `state.root` (issue-106) and is computed
        # here, not at import: `--config` is resolved just before this runs.
        defaults = {
            **_DEFAULTS,
            "pidfile": _state_layout().pidfile,
            **_load_config_defaults(),
        }
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        routing_defaults = cli_config.load_routing_config(_CONFIG_PATH)
        start = actions.add_parser("start", help="Start the webhook receiver")
        start.add_argument("--host", default=defaults["host"])
        start.add_argument("--port", type=int, default=int(defaults["port"]))
        start.add_argument("--path", default=defaults["path"])
        start.add_argument(
            "--route",
            action=argparse.BooleanOptionalAction,
            default=bool(routing_defaults.get("enabled", False)),
            help="Route events to registered harness sessions "
            "(default: routing.enabled).",
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
                cli_config.load_routing_config(_CONFIG_PATH), _load_config_defaults()
            )
            missing = check_dependencies(routing_config.web_terminal.enabled)
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
