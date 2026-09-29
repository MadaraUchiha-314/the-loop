"""Author a lifecycle hook — the SDK's hooks surface (issue-344).

Subclass :class:`LifecycleHooks`, override the points you care about, and either name
the module in the CLI config (``hooks: - {name: …, path: hooks/mine.py}``) to run it
inside the-loop's process, or host it — ``HookServer(MyHooks()).serve_forever()`` — and
name its URL (``- {name: …, url: https://…, tokenEnv: MY_TOKEN}``). Same class, both
ways::

    from the_loop.sdk.hooks import LifecycleHooks, SessionSpawn, WorkItemStart

    class Acme(LifecycleHooks):
        def work_item_start(self, ctx: WorkItemStart):
            if ctx.actor not in ROSTER:
                ctx.proceed = False
                ctx.reason = f"{ctx.actor} is not on the delivery roster"
                return ctx
            return None                      # pass through unchanged

        def session_spawn(self, ctx: SessionSpawn):
            ctx.prompt = HOUSE_RULES + "\\n\\n" + ctx.prompt
            return ctx

Every context is facts plus a few **decisions** (``proceed``, ``prompt``, ``announce``,
``question``, ``notify``…); the-loop applies the decisions and ignores everything else
you might change. :func:`handle_request` is the JSON-RPC server half for a framework of
your own. This module imports no FastAPI, uvicorn or MCP.

Full guide: ``docs/cli/lifecycle-hooks.md``.
"""

from ..lifecycle.contract import (
    POINTS,
    Context,
    DecisionTypeError,
    InputReceived,
    LifecycleHooks,
    PhaseChanged,
    SessionSpawn,
    SessionSpawned,
    WaitingForInput,
    WorkItem,
    WorkItemComplete,
    WorkItemStart,
    describe,
)
from ..lifecycle.remote import HookFailure, HookServer, handle_request

__all__ = [
    "POINTS",
    "Context",
    "DecisionTypeError",
    "HookFailure",
    "HookServer",
    "InputReceived",
    "LifecycleHooks",
    "PhaseChanged",
    "SessionSpawn",
    "SessionSpawned",
    "WaitingForInput",
    "WorkItem",
    "WorkItemComplete",
    "WorkItemStart",
    "describe",
    "handle_request",
]
