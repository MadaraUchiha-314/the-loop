"""Boot the control-plane service: ``python -m the_loop.api.serve`` (issue-161).

This is what ``the-loop service start`` spawns (argv, no shell). The service
carries **no in-app authentication** — it is deployed behind a gateway that
owns auth (owner decision, PR #162). The **exposure guard** below is therefore
the sole network boundary the service enforces itself: a non-loopback host
without ``service.exposed: true`` refuses to boot, so the API — which can spawn
harness sessions — is never accidentally on the network. A real deployment sets
``exposed: true`` and puts the auth-terminating gateway in front.

A second guard sits beside it (issue-211): ``service.cors`` is resolved here so
a configuration that must never be served — every origin allowed *and*
credentials permitted — stops the process before it binds, rather than at the
first request.
"""

from __future__ import annotations

import logging
import sys

from .. import eventlog
from ..cli_config import default_cli_config_path, load_cli_config
from ..runlock import RunLock
from .config import cors_config, is_loopback, service_config, service_pidfile

logger = logging.getLogger("the-loop.service")


def main() -> int:
    try:
        cli_config = load_cli_config(default_cli_config_path())
    except Exception:  # config problems must not leave the service half-up
        logger.exception("cannot load the CLI config; refusing to start")
        return 2
    conf = service_config(cli_config)
    if not is_loopback(conf["host"]) and not conf["exposed"]:
        logger.error(
            "refusing to bind %s: set service.exposed: true to serve beyond "
            "loopback, and front it with an auth-terminating gateway "
            "(the API can spawn harness sessions)",
            conf["host"],
        )
        return 2
    try:
        cors_config(cli_config)
    except ValueError as exc:
        # Beside the exposure guard on purpose, and for the same reason: a
        # configuration that must not be served is refused before anything is
        # bound or locked, not repaired on the operator's behalf.
        logger.error("%s", exc)
        return 2

    lock = RunLock(service_pidfile(cli_config), name="service")
    if not lock.acquire():
        logger.error(
            "another control-plane service is already running (pid %s)",
            lock.holder(),
        )
        return 1

    eventlog.configure_from_file("service")

    from .app import create_app

    app = create_app(cli_config)
    eventlog.emit("service.started", host=conf["host"], port=conf["port"])
    try:
        import uvicorn

        uvicorn.run(app, host=conf["host"], port=conf["port"], log_level="info")
    finally:
        eventlog.emit("service.stopped")
        lock.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
