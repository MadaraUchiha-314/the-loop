"""Boot the control-plane service: ``python -m the_loop.api.serve`` (issue-161).

This is what ``the-loop service start`` spawns (argv, no shell). The exposure
guard lives here, before anything binds: a non-loopback host without
``service.exposed: true`` refuses to boot — the API is an RCE-equivalent
surface and "accidentally on the network" must be impossible (requirements
§Security, abuse case 2). The per-boot bearer token is minted before binding,
so there is no unauthenticated window.
"""

from __future__ import annotations

import logging
import sys

from .. import eventlog
from ..cli_config import default_cli_config_path, load_cli_config
from ..runlock import RunLock
from .auth import mint_token
from .config import is_loopback, service_config, service_pidfile, token_path

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
            "loopback (the API can spawn harness sessions)",
            conf["host"],
        )
        return 2

    lock = RunLock(service_pidfile(cli_config), name="service")
    if not lock.acquire():
        logger.error(
            "another control-plane service is already running (pid %s)",
            lock.holder(),
        )
        return 1

    token = mint_token(token_path(cli_config))
    eventlog.configure_from_file("service")

    from .app import create_app

    app = create_app(cli_config, token=token)
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
