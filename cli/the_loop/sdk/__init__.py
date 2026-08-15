"""the-loop as a library: embed the control plane in your own Python service.

``the-loopy-one`` ships a CLI and a standalone control-plane service. This package is the
third way to run the same code — **inside a process you already have**::

    from fastapi import Depends, FastAPI
    from the_loop.sdk import TheLoop

    loop = TheLoop(config_path="/etc/the-loop/cli-config.yaml")
    app = FastAPI()
    loop.mount(app, prefix="/the-loop", dependencies=[Depends(verify_caller)])

That mounts every ``/api/v1`` operation the standalone service serves — the same router,
so the two cannot drift — plus the MCP endpoint, under your prefix, behind your
middleware, inside your process. The capabilities are also callable directly, with no HTTP
in the way::

    loop.work_items.list()
    loop.graph.check("/srv/checkouts/app", "issue-42")

**What is public.** Everything in :data:`__all__`, and the methods and namespaces
documented on :class:`~the_loop.sdk.client.TheLoop`. They change under semantic
versioning. Everything else in the package — :mod:`the_loop.core`, :mod:`the_loop.api`,
and the rest — is internal and may change in any release; reach for it and you are
maintaining a fork of the seam.

**What it expects from the host.** the-loop drives other programs (``gh``, a harness CLI,
``tmux``, ``git``). Which of them your configuration actually needs is answerable at
startup — ``loop.check_environment()`` — and written out in ``docs/sdk/environment.md``.

**What it does not do.** It adds no authentication (decision-059: the deployment owns
auth; the SDK makes attaching yours a parameter), it installs nothing on your application
beyond the router and — unless you say otherwise — its lifespan, and it applies no CORS
policy to an app it does not own.
"""

from .client import DEFAULT_PREFIX, TheLoop
from .environment import REQUIREMENTS, Requirement, check_environment

__all__ = [
    "DEFAULT_PREFIX",
    "REQUIREMENTS",
    "Requirement",
    "TheLoop",
    "check_environment",
]
