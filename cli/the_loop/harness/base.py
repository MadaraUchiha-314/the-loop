"""Adapter contract: harness-specific argv + environment knowledge (issue-15, R4).

An adapter owns everything harness-specific the routing core must not know:
the argv that hosts its harness's *interactive* TUI in a tmux session
(``interactive_argv`` / ``interactive_resume_argv`` — the only way the daemon
runs sessions since the headless process runner was removed, issue-156), the
argv for ONE non-interactive run (``oneshot_argv`` — the critic-review surface,
issue-108), and what its harness needs *on disk* to start unattended in a
given directory (``prepare_environment``, issue-90). Extra args come from
``routing.harnessArgs`` — the dispatcher never widens permissions itself.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from typing import List, Optional, Sequence

from ..harness_plugins import PluginConfig
from ..trust import TrustConfig, TrustResult

logger = logging.getLogger("the-loop.harness")


class UnsupportedRunnerError(Exception):
    """The adapter cannot host an interactive (tmux-hosted) session (issue-32)."""


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


class HarnessAdapter:
    """Contract: host this harness interactively in tmux / run it one-shot.

    Subclasses set ``name``/``default_binary`` and implement ``_oneshot_argv``
    (critics) plus, where the harness supports it, the ``interactive_*``
    methods (tmux hosting). SDK-based implementations remain possible behind
    this same contract (R4.5) but are out of scope (decision-016).
    """

    name: str = ""
    default_binary: str = ""
    #: This harness's flag for selecting a model (``--model``, ``-m``, …). Empty
    #: when the harness has none, in which case a requested model is ignored
    #: rather than guessed at.
    model_flag: str = ""

    def __init__(
        self,
        binary: Optional[str] = None,
        extra_args: Optional[Sequence[str]] = None,
        trust: Optional[TrustConfig] = None,
        plugins: Optional[PluginConfig] = None,
    ):
        self.binary = binary or self.default_binary
        self.extra_args = list(extra_args or [])
        self.trust = trust or TrustConfig()
        self.plugins = plugins or PluginConfig()

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None

    def prepare_environment(self, cwd: str, root: Optional[str] = None) -> TrustResult:
        """Put whatever this harness needs on disk to start unattended in ``cwd``.

        Called by the dispatcher before every spawn/respawn (issue-90). ``root``
        is the workspace root the dispatcher resolved for ``scope:
        workspace-root``, or None to scope everything to ``cwd``. Also where
        the-loop's own plugin is enabled, so the session has the loop's skill,
        commands and hooks loaded rather than being told to run a loop it does
        not have (issue-143). The default is a no-op — a harness with no such
        configuration surface (cursor-agent today) is not an error, it simply
        has nothing to prepare.
        """
        return TrustResult()

    def _oneshot_argv(self, prompt: str) -> List[str]:
        raise NotImplementedError

    def oneshot_argv(self, prompt: str, model: str = "") -> List[str]:
        """Argv for ONE non-interactive run of this harness, JSON out.

        Exactly what a critic-review round needs (issue-108) — and, since the
        process runner's removal (issue-156), the only non-interactive
        invocation the-loop makes. Kept here rather than in a critic-side
        lookup table so "how do you run harness X once" has a single owner:
        add an adapter and it is usable as a critic for free.
        """
        argv = self._oneshot_argv(prompt)
        if model and self.model_flag:
            argv = argv + [self.model_flag, model]
        return argv

    def interactive_argv(self, prompt: str, session_id: str) -> List[str]:
        """Argv hosting this harness's interactive TUI with a pre-assigned
        session id (tmux runner, issue-32). Adapters without a pre-assignable
        id keep this raising so tmux-mode spawns fail cleanly (R2.2)."""
        raise UnsupportedRunnerError(
            f"the {self.name or self.binary} harness does not support the tmux "
            "runner (no pre-assignable session id in interactive mode)"
        )

    def interactive_resume_argv(self, prompt: str, session_id: str) -> List[str]:
        """Argv **resuming** an existing conversation in this harness's TUI.

        Used when a dead tmux session is respawned, so the fresh TUI continues
        the conversation the work item was already in rather than starting
        blank (issue-89). Adapters that cannot resume interactively keep this
        raising; the dispatcher reads that as "spawn a fresh session instead",
        never as a failure.
        """
        raise UnsupportedRunnerError(
            f"the {self.name or self.binary} harness cannot resume a "
            "conversation in interactive mode"
        )


def usage_from_output(stdout: str) -> Usage:
    """Best-effort token/cost accounting from the CLI's JSON output (issue-37).

    Harness-agnostic: reads a top-level ``usage`` object (under any of the
    aliased keys) for token counts and a top-level cost field, tolerating a
    harness that reports neither. Never raises — telemetry is advisory.
    """
    data = parse_json_object(stdout)
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


def parse_json_object(stdout: str) -> dict:
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
