"""``mcp-call`` — reach an MCP-only capability by delegating to the harness.

MCP is a protocol for **agents** to call tools: it assumes a model-driven client
with a session. A daemon speaking it is against its grain, and implementing it
would put protocol code, server lifecycle management and credential handling
inside the-loop for capability it can already reach.

So the-loop delegates. It already spawns Claude Code / Cursor, and both are MCP
clients with the operator's servers configured — the harness *is* the client,
which is what it is for. A minimal stdio JSON-RPC client stays on the shelf
(decision-042); revisit only if delegation latency ever matters, which for
notification-shaped calls it will not.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from typing import Any, Dict, List

from ..contract import HookContext, HookResult, Message
from ..registry import hook

logger = logging.getLogger("the-loop.graph")

NAME = "mcp-call"

#: The answer must be structured, so the-loop never parses prose.
_SCHEMA = {
    "type": "object",
    "properties": {
        "ok": {"type": "boolean"},
        "result": {"type": "string"},
    },
    "required": ["ok"],
}


def _argv(harness: str, prompt: str) -> List[str]:
    if harness == "cursor":
        # No schema enforcement in cursor-agent today: the schema is embedded in
        # the prompt and validated locally instead (decision-042).
        return ["cursor-agent", "-p", prompt, "--output-format", "json"]
    return [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(_SCHEMA),
    ]


@hook(NAME)
def mcp_call(ctx: HookContext) -> HookResult:
    tool = str(ctx.params.get("tool") or "")
    if not tool:
        return HookResult.skipped(NAME, "no MCP tool named")
    harness = str(
        ctx.params.get("harness") or ctx.config.get("defaultHarness") or "claude"
    )
    binary = "cursor-agent" if harness == "cursor" else "claude"
    if not shutil.which(binary):
        return HookResult.blocked(
            NAME,
            [Message(text=f"cannot delegate an MCP call: {binary!r} is not on PATH")],
            retriable=False,
        )

    prompt = (
        f"Call the MCP tool `{tool}` with these arguments and return ONLY the "
        f"structured result.\n\nArguments: {json.dumps(ctx.params.get('arguments') or {})}\n\n"
        f"Respond as JSON matching: {json.dumps(_SCHEMA)}"
    )
    try:
        proc = subprocess.run(
            _argv(harness, prompt),
            cwd=str(ctx.repo),
            capture_output=True,
            text=True,
            timeout=float(ctx.params.get("timeoutSeconds", 300)),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return HookResult.blocked(NAME, [Message(text=f"MCP delegation failed: {exc}")])

    if proc.returncode != 0:
        return HookResult.blocked(
            NAME,
            [Message(text=f"MCP delegation exited {proc.returncode}")],
        )

    payload: Dict[str, Any] = {}
    try:
        raw = json.loads(proc.stdout or "{}")
        payload = raw.get("structured_output") or raw
    except json.JSONDecodeError:
        return HookResult.blocked(
            NAME, [Message(text="the harness did not return parseable JSON")]
        )
    if not isinstance(payload, dict) or not payload.get("ok", False):
        return HookResult.blocked(
            NAME, [Message(text=f"MCP tool {tool!r} reported failure")]
        )
    return HookResult.ok(NAME, tool=tool, result=payload.get("result", ""))
