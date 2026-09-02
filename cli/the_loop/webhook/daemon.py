"""The GitHub webhook receiver's run loop, out from under the removed
``gh-webhook`` command (issue-228, owner review on PR #229).

issue-228 first removed the ``poll`` command; on review the owner folded the
remaining granular lifecycle commands (``gh-webhook``, ``service``) into the
one surface too — *"It should all fold into `the-loop start`"*. So, exactly as
:mod:`the_loop.poller.daemon` is the poller's run loop, this module is the
receiver's: options resolved from the CLI config (``webhooks.ghWebhook`` for
the listener, the top-level ``routing`` block for dispatch — issue-142), driven
by ``python -m the_loop.daemon_entry gh-webhook`` (what ``the-loop start`` and
the control plane spawn detached, and what a systemd unit runs in the
foreground). The secret is read from an env var (never a flag or config value)
so it doesn't leak into process listings.

Since issue-228 the receiver holds its pidfile as a ``RunLock`` — the
issue-159 flock discipline the poller has had all along — so liveness answers
(`the-loop status`, ``core.daemons``) come from the lock, and a stop is
verified and blocking.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from dataclasses import dataclass

from .. import cli_config, eventlog
from ..runlock import RunLock
from ..state import StateLayout, layout_from_config
from . import serve

logger = logging.getLogger("the-loop.gh-webhook")

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


@dataclass
class ReceiverOptions:
    """Everything :func:`run` needs, resolved from the CLI config."""

    host: str
    port: int
    path: str
    secret_env: str
    pidfile: str
    route: bool


def _config_path():
    """Resolved per call, never cached at import: a ``--config`` override set by
    :mod:`the_loop.cli`'s pre-scan (or a test's env var) must always win."""
    return cli_config.default_cli_config_path()


def _state_layout() -> StateLayout:
    """``state.root`` from the CLI config — the root of everything generated."""
    return layout_from_config(cli_config.load_cli_config(_config_path()))


def _read_gh_webhook_config(strict: bool = False) -> dict:
    """Read ``webhooks.ghWebhook`` from the CLI config.

    ``strict=False`` (defaults path): returns ``{}`` when the file is missing or
    unparseable, so a half-saved hand edit never breaks ingress.
    ``strict=True`` (hot-reload path): raises on a missing file / parse error, so
    the :class:`Reloader` keeps the previously loaded config instead of resetting
    to defaults on a transient broken save.
    """
    data = cli_config.load_cli_config(_config_path(), strict=strict)
    return ((data.get("webhooks") or {}).get("ghWebhook")) or {}


def _load_config_defaults() -> dict:
    """Best-effort read of webhooks.ghWebhook (never raises)."""
    return _read_gh_webhook_config(strict=False)


def default_options() -> ReceiverOptions:
    """The options the removed ``gh-webhook start`` parser would have defaulted to."""
    conf = {**_DEFAULTS, **_load_config_defaults()}
    routing = cli_config.load_routing_config(_config_path())
    return ReceiverOptions(
        host=str(conf["host"]),
        port=int(conf["port"]),
        path=str(conf["path"]),
        secret_env=str(conf["secretEnv"]),
        pidfile=str(conf.get("pidfile") or _state_layout().pidfile),
        route=bool(routing.get("enabled", False)),
    )


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


def _build_routing(routing_config: dict, gh_webhook_config: dict):
    """Compose router + dispatcher into the server's on_event callback.

    Takes the two blocks separately, because they are two concerns: the shared
    top-level ``routing`` policy, and the receiver's own event filter
    (issue-142). Spec: docs/specs/issue-15/design.md §6. Returned with the
    dispatcher so :func:`run` can drain it on shutdown.
    """
    from ..authz import resolve_authorized_users
    from ..harness import build_adapters
    from ..reload import Reloader
    from ..sessions import SessionRegistry
    from .dispatcher import Dispatcher, RoutingConfig
    from .router import Router

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
    from ..channels.publishers import comment_publisher

    router = Router(
        events=events,
        deduper=dispatcher.deduper,
        auto_execute_label=config.auto_execute_label,
        authorized_users=authorized,
        # One roster, read by both halves: the router to let a granted login's
        # comment through, the dispatcher to write it (issue-307).
        collaborators=dispatcher.collaborator_store,
        # The bus (issue-309): accepted and agent comments go to the subscribed
        # channels. Reads the config per call, so a reload is honoured.
        publisher=comment_publisher(lambda: cli_config.load_cli_config(_config_path())),
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
        _config_path(),
        lambda: cli_config.load_cli_config(_config_path(), strict=True),
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


def run(options: ReceiverOptions | None = None) -> int:
    """Run the receiver in this process until stopped.

    The one startup sequence every path converges on (NFR1): lock acquisition,
    dependency checks, bind, the serve loop.
    """
    options = options or default_options()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    eventlog.configure_from_file("gh-webhook")

    # At most one receiver per pidfile, and the pidfile is the flock — the
    # issue-159 discipline the poller has had all along (adopted here by
    # issue-228, which needs the lock to prove a spawned receiver came up).
    lock = RunLock(options.pidfile, name="gh-webhook")
    try:
        acquired = lock.acquire()
    except OSError as exc:
        logger.error("cannot use the receiver lockfile %s: %s", options.pidfile, exc)
        return 1
    if not acquired:
        logger.error(
            "another gh-webhook receiver is already running (pid %s, pidfile "
            "%s); stop it first with `the-loop stop`",
            lock.holder() or "unknown",
            options.pidfile,
        )
        return 1
    try:
        return _serve(options)
    finally:
        lock.release()


def build_receiver(options: ReceiverOptions):
    """Everything up to (and including) the bind: ``(httpd, cleanup)``.

    Shared by the standalone run below and the **hosted** form (issue-231),
    where the control-plane service drives ``httpd.serve_forever()`` on a
    background thread and calls ``httpd.shutdown()`` from its lifespan instead
    of a signal handler. Returns ``None`` when the receiver cannot start (a
    missing dependency, an unbindable port); the reasons are logged. ``cleanup``
    closes the server and drains the dispatcher — call it exactly once, after
    the serve loop returns.
    """
    secret = os.environ.get(options.secret_env)
    if not secret:
        logger.warning(
            "no webhook secret in $%s — signatures will NOT be verified",
            options.secret_env,
        )

    from ..runner import check_dependencies, start_web_terminal, stop_web_terminal

    on_event = dispatcher = web_proc = None
    if options.route:
        on_event, dispatcher, routing_config = _build_routing(
            cli_config.load_routing_config(_config_path()), _load_config_defaults()
        )
        missing = check_dependencies(routing_config.web_terminal.enabled)
        if missing:  # R6.1: fail with per-platform guidance; R6.2: else silent
            for line in missing:
                logger.error(line)
            return None
        if routing_config.web_terminal.enabled:
            web_proc = start_web_terminal(routing_config.web_terminal)

    try:
        httpd = serve(
            host=options.host,
            port=options.port,
            path=options.path,
            secret=secret,
            on_event=on_event,
        )
    except OSError as exc:
        logger.error("could not bind %s:%s — %s", options.host, options.port, exc)
        stop_web_terminal(web_proc)
        return None

    logger.info(
        "gh-webhook listening on http://%s:%s%s (pidfile=%s)",
        options.host,
        options.port,
        options.path,
        options.pidfile,
    )
    eventlog.emit(
        "server.started",
        host=options.host,
        port=options.port,
        path=options.path,
        routing=bool(options.route),
        verifying_signatures=bool(secret),
    )

    # Background watchers, both opt-in and bounded by this receiver's
    # lifetime: self-diagnosis (issue-242) scanning the event log, and the
    # channels reader (issue-245) fetching Slack thread replies when
    # channels.slack has read.mode: poll.
    from ..channels import watcher as channels_watcher
    from ..core import selfdiagnosis

    watchers_stop = threading.Event()
    selfdiagnosis.start_watcher(
        cli_config.load_cli_config(_config_path()), watchers_stop
    )
    channels_watcher.start_watcher(
        cli_config.load_cli_config(_config_path()), watchers_stop
    )

    def cleanup() -> None:
        watchers_stop.set()
        httpd.server_close()
        if dispatcher is not None:
            dispatcher.stop()
        stop_web_terminal(web_proc)
        eventlog.emit("server.stopped", host=options.host, port=options.port)

    return httpd, cleanup


def _serve(options: ReceiverOptions) -> int:
    """The receiver run itself, with the single-instance lock already held."""
    built = build_receiver(options)
    if built is None:
        return 1
    httpd, cleanup = built

    def _shutdown(signum, _frame):
        logger.info("received signal %s, shutting down", signum)
        httpd.shutdown()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        httpd.serve_forever()
    finally:
        cleanup()
    return 0
