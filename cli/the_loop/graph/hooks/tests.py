"""``verify-tests`` — the node's declared test command passed.

The only hook that runs a subprocess, and it is never used by ``the-loop
check`` (which is pure by contract, R8.8) — only by the runtime when a node
declares one.
"""

from __future__ import annotations

import shlex
import subprocess

from ..contract import HookContext, HookResult, Message
from ..registry import hook

NAME = "verify-tests"


@hook(NAME)
def verify_tests(ctx: HookContext) -> HookResult:
    command = ctx.params.get("command")
    if not command:
        return HookResult.skipped(NAME, "no test command declared for this node")
    argv = (
        shlex.split(command) if isinstance(command, str) else [str(c) for c in command]
    )
    try:
        proc = subprocess.run(
            argv,
            cwd=str(ctx.repo),
            capture_output=True,
            text=True,
            timeout=float(ctx.params.get("timeoutSeconds", 900)),
        )
    except FileNotFoundError:
        return HookResult.blocked(
            NAME, [Message(text=f"test command not found: {argv[0]}")], retriable=False
        )
    except subprocess.TimeoutExpired:
        return HookResult.blocked(NAME, [Message(text=f"tests timed out: {command}")])
    if proc.returncode != 0:
        tail = (proc.stdout or proc.stderr or "").strip().split("\n")[-20:]
        return HookResult.blocked(
            NAME,
            [Message(text=f"tests failed ({command}), exit {proc.returncode}")]
            + [Message(text=line, severity="info") for line in tail if line.strip()],
        )
    return HookResult.ok(NAME, command=command)
