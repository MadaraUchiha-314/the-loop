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
from pathlib import Path

from .base import Command, register
from ..webhook import serve

logger = logging.getLogger("the-loop.gh-webhook")

_DEFAULTS = {
    "host": "127.0.0.1",
    "port": 8787,
    "path": "/webhook",
    "secretEnv": "THE_LOOP_GH_WEBHOOK_SECRET",
    "pidfile": ".the-loop/gh-webhook.pid",
}


def _load_config_defaults() -> dict:
    """Best-effort read of webhooks.ghWebhook from .the-loop/config.yaml.

    Returns ``{}`` if the file or PyYAML is unavailable — the CLI must work with
    zero runtime dependencies.
    """
    cfg_path = Path(".the-loop/config.yaml")
    if not cfg_path.is_file():
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        logger.debug("pyyaml not installed; skipping config-file defaults")
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text()) or {}
    except Exception:  # noqa: BLE001
        logger.warning("could not parse %s; using built-in defaults", cfg_path)
        return {}
    return ((data.get("webhooks") or {}).get("ghWebhook")) or {}


@register
class GhWebhookCommand(Command):
    name = "gh-webhook"
    help = "Manage the GitHub webhook receiver server (start/stop)"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        defaults = {**_DEFAULTS, **_load_config_defaults()}
        actions = parser.add_subparsers(dest="action", metavar="<action>")
        actions.required = True

        start = actions.add_parser("start", help="Start the webhook receiver")
        start.add_argument("--host", default=defaults["host"])
        start.add_argument("--port", type=int, default=int(defaults["port"]))
        start.add_argument("--path", default=defaults["path"])
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
        secret = os.environ.get(args.secret_env)
        if not secret:
            logger.warning(
                "no webhook secret in $%s — signatures will NOT be verified",
                args.secret_env,
            )

        try:
            httpd = serve(host=args.host, port=args.port, path=args.path, secret=secret)
        except OSError as exc:
            logger.error("could not bind %s:%s — %s", args.host, args.port, exc)
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
        try:
            httpd.serve_forever()
        finally:
            httpd.server_close()
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
