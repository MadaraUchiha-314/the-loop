"""Whether this CLI invocation routes through the service (issue-161, R2.2).

The service is the default and ONLY execution mode for core capabilities
(owner decision, PR #162). The single exception is an invocation the service
makes into its own CLI (the transitional control adapters in
:mod:`the_loop.core.sessions` / :mod:`the_loop.core.daemons`), marked by
``THE_LOOP_SERVICE_LOCAL=1`` — without the marker those adapters would route
straight back to the service forever. Tests of the local implementations set
the same marker: the local path is still what the service itself executes, so
its behaviour coverage is service-path coverage.
"""

from __future__ import annotations

import os

from ..core.sessions import SERVICE_LOCAL_ENV


def via_service() -> bool:
    return os.environ.get(SERVICE_LOCAL_ENV) != "1"
