"""Adapter contract + shared subprocess plumbing (issue-15, R4).

Every adapter shells out to its harness's official CLI in non-interactive
print mode with JSON output, run in the session's recorded working directory
(resume lookup is scoped to the project directory). Extra args come from
``routing.harnessArgs`` — the dispatcher never widens permissions itself.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Sequence

from ..sessions import Session, WorkItemRef

logger = logging.getLogger("the-loop.harness")


class UnsupportedRunnerError(Exception):
    """The adapter cannot host an interactive (tmux-mode) session (issue-32)."""


# JSON keys the harness CLIs use for their session/chat id, in match order.
_SESSION_ID_KEYS = ("session_id", "sessionId", "chat_id", "chatId", "id")

# Token-usage key aliases across harness JSON outputs (issue-37 telemetry).
_USAGE_KEYS = ("usage", "token_usage", "tokenUsage")
_INPUT_TOKEN_KEYS = ("input_tokens", "inputTokens", "prompt_tokens", "promptTokens")
_OUTPUT_TOKEN_KEYS = (
    "output_tokens",
    "outputTokens",
    "completion_tokens",
    "completionTokens",
)
_CACHE_READ_KEYS = (
    "cache_read_input_tokens",
    "cacheReadInputTokens",
    "cache_read_tokens",
)
_CACHE_WRITE_KEYS = (
    "cache_creation_input_tokens",
    "cacheCreationInputTokens",
    "cache_creation_tokens",
)
_COST_KEYS = ("total_cost_usd", "totalCostUsd", "cost_usd", "costUsd")


@dataclass
class Usage:
    """Best-effort token/cost accounting parsed from a harness's JSON output.

    Fields default to 0 when a harness omits them, so callers can always sum
    without None-checks (issue-37 telemetry). ``present`` records whether any
    usage was actually reported, distinguishing "0 tokens" from "not reported".
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float = 0.0
    present: bool = False

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass
class DispatchResult:
    """Outcome of one resume/spawn subprocess."""

    ok: bool
    session_id: str = ""
    output: str = ""
    error: str = ""
    usage: Usage = field(default_factory=Usage)


class HarnessAdapter:
    """Contract: ``resume`` an existing session / ``spawn`` a new one.

    Subclasses set ``name``/``default_binary`` and implement the two
    ``_*_argv`` methods. SDK-based implementations remain possible behind
    this same contract (R4.5) but are out of scope (decision-016).
    """

    name: str = ""
    default_binary: str = ""

    def __init__(
        self,
        binary: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
    ):
        self.binary = binary or self.default_binary
        self.extra_args = list(extra_args or [])

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def _resume_argv(self, session: Session, prompt: str) -> List[str]:
        raise NotImplementedError

    def _spawn_argv(self, prompt: str) -> List[str]:
        raise NotImplementedError

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        """Argv hosting this harness's interactive TUI with a pre-assigned
        session id (tmux runner, issue-32). Adapters without a pre-assignable
        id keep this raising so tmux-mode spawns fail cleanly (R2.2)."""
        raise UnsupportedRunnerError(
            f"the {self.name or self.binary} harness does not support the tmux "
            "runner (no pre-assignable session id in interactive mode)"
        )

    def resume(
        self, session: Session, prompt: str, timeout: Optional[float] = None
    ) -> DispatchResult:
        """Wake ``session`` with ``prompt``, run in the session's cwd (R4.2)."""
        return self._run(self._resume_argv(session, prompt), session.cwd, timeout)

    def spawn(
        self,
        work_item: WorkItemRef,
        prompt: str,
        cwd: str,
        timeout: Optional[float] = None,
    ) -> DispatchResult:
        """Start a fresh session; the new id is in ``result.session_id`` (R4.4)."""
        result = self._run(self._spawn_argv(prompt), cwd, timeout)
        if result.ok and not result.session_id:
            result = DispatchResult(
                ok=False,
                output=result.output,
                error=(
                    f"{self.binary} did not report a session id in its JSON "
                    "output; cannot register the spawned session"
                ),
            )
        return result

    def _run(
        self, argv: List[str], cwd: str, timeout: Optional[float]
    ) -> DispatchResult:
        if not self.is_available():
            return DispatchResult(
                ok=False,
                error=(
                    f"harness CLI {self.binary!r} not found on PATH; install it "
                    f"or point the {self.name} adapter at the right binary"
                ),
            )
        cmd = [self.binary] + argv
        logger.debug("running %s (cwd=%s)", " ".join(cmd[:5]) + " …", cwd)
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            return DispatchResult(
                ok=False, error=f"{self.binary} timed out after {timeout}s"
            )
        except OSError as exc:
            return DispatchResult(ok=False, error=f"could not run {self.binary}: {exc}")
        if proc.returncode != 0:
            return DispatchResult(
                ok=False,
                output=proc.stdout,
                error=(
                    f"{self.binary} exited {proc.returncode}: "
                    f"{proc.stderr.strip() or proc.stdout.strip()}"
                ),
            )
        return DispatchResult(
            ok=True,
            session_id=_session_id_from_output(proc.stdout),
            output=proc.stdout,
            usage=_usage_from_output(proc.stdout),
        )


def _session_id_from_output(stdout: str) -> str:
    """Best-effort session/chat id from the CLI's JSON output."""
    data = _parse_json_object(stdout)
    for key in _SESSION_ID_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _usage_from_output(stdout: str) -> Usage:
    """Best-effort token/cost accounting from the CLI's JSON output (issue-37).

    Harness-agnostic: reads a top-level ``usage`` object (under any of the
    aliased keys) for token counts and a top-level cost field, tolerating a
    harness that reports neither. Never raises — telemetry is advisory.
    """
    data = _parse_json_object(stdout)
    usage = Usage()
    block = next(
        (data[k] for k in _USAGE_KEYS if isinstance(data.get(k), dict)),
        None,
    )
    if isinstance(block, dict):
        usage.input_tokens = _first_int(block, _INPUT_TOKEN_KEYS)
        usage.output_tokens = _first_int(block, _OUTPUT_TOKEN_KEYS)
        usage.cache_read_tokens = _first_int(block, _CACHE_READ_KEYS)
        usage.cache_write_tokens = _first_int(block, _CACHE_WRITE_KEYS)
        usage.present = usage.present or bool(block)
    for key in _COST_KEYS:
        value = data.get(key)
        if isinstance(value, (int, float)):
            usage.cost_usd = float(value)
            usage.present = True
            break
    return usage


def _parse_json_object(stdout: str) -> dict:
    """Parse the CLI's stdout as a JSON object, or ``{}`` on any failure."""
    try:
        data = json.loads(stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _first_int(block: dict, keys: Sequence[str]) -> int:
    """First integer-valued key from ``keys`` present in ``block``, else 0."""
    for key in keys:
        value = block.get(key)
        if isinstance(value, bool):  # bool is an int subclass — reject it
            continue
        if isinstance(value, int):
            return value
    return 0
