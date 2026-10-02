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

import copy
import json
import logging
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

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
    "cached_input_tokens",
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
    #: How THIS harness expresses one of the-loop's normalised effort levels
    #: (``low``/``medium``/``high``, :data:`the_loop.modelchoice.EFFORT_LEVELS`).
    #: A level this harness cannot express is simply absent, and an absent level
    #: is NOT offered for this harness rather than being silently dropped
    #: (issue-358, R2.6/R2.8). Empty on both shipped adapters today: neither CLI
    #: exposes an effort flag, and a mapping is filled in from a harness's own
    #: ``--help`` and then validated by the availability probe — never invented.
    _EFFORT_ARGS: Dict[str, Tuple[str, ...]] = {}
    #: What this harness is launched with when nobody answers its pane
    #: (issue-426): the arguments that take away its interactive prompts, so an
    #: unattended session asks in text and ends its turn rather than blocking on
    #: a keypress. Appended after ``extra_args``, immediately before the
    #: positional prompt. Empty when the harness has nothing to take away.
    _UNATTENDED_ARGS: Tuple[str, ...] = ()
    #: Set per launch by :meth:`with_unattended`, never at construction: only
    #: the seams that launch a work item's session know its interaction mode.
    unattended: bool = False

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

    def effort_args(self, level: str) -> Tuple[str, ...]:
        """This harness's argv for a normalised effort level, or ``()``.

        ``()`` means "this harness cannot express that level" — the gate reads
        that as *do not offer it here*, never as *run without it*. The-loop owns
        the vocabulary precisely because harnesses spell it differently; the
        translation is each adapter's, and an adapter that has none says so by
        returning nothing rather than by having a flag guessed for it.
        """
        return tuple(self._EFFORT_ARGS.get(level, ()))

    def with_args(self, extra_args: Sequence[str]) -> "HarnessAdapter":
        """A copy of this adapter launching with ``extra_args`` instead.

        How a work item's own model and effort reach an argv (issue-358): the
        dispatcher resolves the frozen choice, merges it onto the harness's
        launch arguments, and hands the result here. A method rather than a
        ``replace()`` at each call site, so a subclass can never be rebuilt with
        half its configuration — ``trust`` and ``plugins`` are carried over, and
        the binary with them.
        """
        clone = copy.copy(self)
        clone.extra_args = [str(a) for a in extra_args]
        return clone

    def with_unattended(self, unattended: bool) -> "HarnessAdapter":
        """A copy launching with nobody at its pane, or ``self`` when unchanged.

        :meth:`with_args`'s shape: the shared adapter is never mutated, and a
        copy keeps the binary, the arguments, ``trust`` and ``plugins``. An
        adapter with no :attr:`_UNATTENDED_ARGS` is returned as it is, since
        there is nothing for the flag to change (issue-426).
        """
        if unattended == self.unattended or not self._UNATTENDED_ARGS:
            return self
        clone = copy.copy(self)
        clone.unattended = unattended
        return clone

    def _launch_args(self) -> List[str]:
        """``extra_args``, then :attr:`_UNATTENDED_ARGS` when launched unattended."""
        if self.unattended:
            return self.extra_args + list(self._UNATTENDED_ARGS)
        return list(self.extra_args)

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

    def resolve_session_id(self, cwd: str, session_id: str) -> str:
        """Resolve a launch identity to the harness's native conversation id.

        Most CLIs accept the assigned id directly. A CLI that creates its own
        id may discover it from a positively identified transcript instead.
        An empty answer means it cannot safely resume that conversation.
        """
        return session_id


def hosts_sessions(adapter: object) -> bool:
    """Whether ``adapter`` (an instance or a class) can host a work item's session.

    Derived from whether its class overrides :meth:`HarnessAdapter.interactive_argv`,
    never declared beside it, so an adapter cannot claim a capability it does not
    implement (issue-440). Only a hosting harness can be offered at `phase-selection`:
    offering one that cannot spawn would park a work item on a session that never starts.
    """
    cls = adapter if isinstance(adapter, type) else type(adapter)
    method = getattr(cls, "interactive_argv", None)
    return method is not None and method is not HarnessAdapter.interactive_argv


def usage_from_output(stdout: str) -> Usage:
    """Best-effort token/cost accounting from the CLI's JSON output (issue-37).

    Harness-agnostic: reads a top-level ``usage`` object (under any of the
    aliased keys) for token counts and a top-level cost field, tolerating a
    harness that reports neither. Never raises — telemetry is advisory.
    """
    data = parse_json_object(stdout)
    if not data:
        # JSONL event streams report accounting at turn completion. Take the
        # latest usage snapshot, never sum snapshots of the same turn.
        for event in json_objects(stdout):
            if any(isinstance(event.get(key), dict) for key in _USAGE_KEYS):
                data = event
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
        if "cached_input_tokens" in block:
            # OpenAI counts cached input inside input_tokens; our Usage totals
            # sum the disjoint categories used by the other harnesses.
            usage.input_tokens = max(0, usage.input_tokens - usage.cache_read_tokens)
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


def json_objects(stdout: str):
    """Valid objects from a JSONL stream; malformed/progress lines are inert."""
    for line in stdout.splitlines():
        data = parse_json_object(line)
        if data:
            yield data


def output_text(stdout: str) -> str:
    """The final agent message in a JSONL stream, or the original output."""
    answer = ""
    for event in json_objects(stdout):
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            answer = item["text"]
    return answer or stdout


def _first_int(block: dict, keys: Sequence[str]) -> int:
    """First integer-valued key from ``keys`` present in ``block``, else 0."""
    for key in keys:
        value = block.get(key)
        if isinstance(value, bool):  # bool is an int subclass — reject it
            continue
        if isinstance(value, int):
            return value
    return 0
