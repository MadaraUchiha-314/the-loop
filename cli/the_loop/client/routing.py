"""Whether this CLI invocation routes through the service (issue-161, R2.2).

The service is the default and **only** execution mode for core capabilities
(owner decision, PR #162). This module owns the single exception:
``THE_LOOP_SERVICE_LOCAL=1`` makes a command execute the core facade
in-process instead.

That marker used to exist for loop prevention, because core's control verbs
shelled back into the-loop's own CLI; that adapter is gone (core owns the
logic now), so what remains is a **test seam** — the suite exercises command
behaviour in-process rather than standing a live service up per test, and the
code under test is the same core the service calls. It is deliberately not a
documented operator switch: production installs route through the service.

:func:`routed` is the one-liner every routed command uses, so the decision, the
connection and the error mapping live here rather than being re-typed per
command.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Optional, Tuple

#: Env var marking an invocation that must execute core in-process (tests).
SERVICE_LOCAL_ENV = "THE_LOOP_SERVICE_LOCAL"


def via_service() -> bool:
    return os.environ.get(SERVICE_LOCAL_ENV) != "1"


def routed(
    remote: Callable[[Any], Any],
    local: Callable[[], Any],
    config: Optional[dict] = None,
) -> Any:
    """``remote(connection)`` through the service, else ``local()`` in-process.

    Raises :class:`~the_loop.client.ServiceUnavailable` when no service is
    reachable and none could be started — never a silent fallback to ``local``
    (R2.3). Commands render that as an error; :func:`service_error` turns any
    client-side failure into the ``(message, exit code)`` they print.
    """
    if not via_service():
        return local()
    from .. import client

    return remote(client.connect(config))


#: What a harness verb says when it runs in-process (issue-447, R2.2): the
#: fallback is never silent.
IN_PROCESS_NOTE = (
    "note: no control-plane service is reachable; running in-process on this "
    "session's GitHub token (integrations.github.api.tokenEnv)"
)


def harness_routed(
    remote: Callable[[Any], Any],
    local: Callable[[], Any],
    config: Optional[dict] = None,
) -> Any:
    """``remote`` through a **running** service, else ``local()`` — and say so.

    The harness's GitHub verbs (issue-447, decision-140 D2) differ from every
    other core verb in one way: their only state is on GitHub, and all a
    service adds is the daemon's token. So they prefer the service when one
    answers ``/health`` — the session then never holds a token — and otherwise
    run in-process on the session's own, as ``ask`` does, rather than failing.
    They never auto-start a service: in a cloud checkout that would only move the
    session's token into a second process. The fallback prints
    :data:`IN_PROCESS_NOTE` on stderr every time (A5).
    """
    if not via_service():
        return local()
    from .. import client

    resolved = client.resolved_config(config)
    if client.healthy(resolved):
        return remote(client.Client(resolved))
    print(IN_PROCESS_NOTE, file=sys.stderr)
    return local()


def service_error(exc: Exception) -> Optional[Tuple[str, int]]:
    """``(message, exit code)`` for a client-side failure, or ``None``.

    Mirrors the API's own mapping back onto the CLI's conventions: a 400 is the
    caller's mistake (exit 2, same as an argparse rejection), a 404 is "not
    found" (exit 1, same as the local path's "no session recorded"), and an
    unreachable service is a lifecycle problem (exit 2).
    """
    from ..client import ApiError, ServiceUnavailable

    if isinstance(exc, ServiceUnavailable):
        return f"error: {exc}", 2
    if isinstance(exc, ApiError):
        return f"error: {exc.detail or exc}", 2 if exc.status == 400 else 1
    return None
