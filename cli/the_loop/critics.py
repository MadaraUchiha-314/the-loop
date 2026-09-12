"""Critic-review invocation — one configured critic, one process, one envelope.

the-loop's review loop runs self-reviews, then **critic** reviews by a *different*
harness/model, then the human. How many rounds is the operator's ``reviews`` block
in the CLI config (:func:`load_review_policy`, ``the-loop critic policy``; moved out
of the harness config in issue-352); the procedure lives in the skill's
``reference/reviewing.md``. What was missing (issue-108) was the mechanism: how a
running harness turns ``critics[]`` into an actual process, and how it gets
that process's output back.

This module is that mechanism and nothing more. It

1. loads ``critics[]`` from the operator's CLI config (issue-352 moved the roster
   out of the repository's harness config, which the CLI no longer reads),
2. resolves ONE critic into an argv list — either the operator's explicit
   ``command``/``args`` or, for a harness the-loop already has an adapter for, that
   adapter's own one-shot argv, and
3. runs it **without a shell**, under a timeout, returning a :class:`CriticResult`
   the CLI prints as a single JSON envelope.

The review *loop* — round counts, convergence, posting findings — stays with the
harness following ``reference/reviewing.md``. Splitting it the other way would fork
the loop into two implementations that have to agree (decision-043).

Security: a ``critics[]`` entry is **executable configuration** in the operator's own
CLI config, so it is reviewed like code — and, since issue-352, no longer in a file a
pull request to the repository can edit. Nothing here ever runs implicitly —
the caller names exactly one critic — and every invocation is an argv *list* with
``shell=False``, so no placeholder value (a diff, a ticket comment, anything
untrusted quoted into the review prompt) can be parsed as a command.

Spec: docs/specs/issue-108/  ·  Decision: 043
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .harness import Usage, build_adapters
from .harness.base import parse_json_object, usage_from_output

logger = logging.getLogger("the-loop.critics")

#: The closed set of substitutions available in ``critics[].args``.
#: Closed on purpose: an unknown ``{placeholder}`` is a typo that would otherwise
#: reach the critic as literal braces and quietly review the wrong thing.
PLACEHOLDERS = ("prompt", "promptFile", "model", "workItem", "specDir", "cwd")

#: Either of these means "the critic is handed the material under review".
_PROMPT_PLACEHOLDERS = ("prompt", "promptFile")

_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")

#: Keys harness CLIs put their assistant text under, in match order.
_TEXT_KEYS = ("result", "response", "text", "output", "content", "message")

_OUTPUT_FORMATS = ("text", "json")

DEFAULT_TIMEOUT_SECONDS = 900.0


class CriticConfigError(ValueError):
    """The critic cannot be run as configured. Nothing is ever spawned first."""


@dataclass(frozen=True)
class Critic:
    """One ``critics[]`` entry.

    ``error`` carries why an entry is unusable instead of raising at load time, so
    ``the-loop critic list`` can show a broken entry beside the working ones (R4.3)
    while :func:`run_critic` still refuses it.
    """

    name: str
    harness: str = ""
    model: str = ""
    command: str = ""
    args: Sequence[str] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str = ""
    output_format: str = "text"
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    enabled: bool = True
    error: str = ""

    @property
    def attribution(self) -> str:
        """The ``[<harness>/<model>]`` prefix every finding carries (reviewing.md)."""
        return f"[{self.harness or self.name}/{self.model or 'default'}]"

    @property
    def binary(self) -> str:
        """The executable this critic resolves to, or "" when it resolves to none."""
        if self.command:
            return self.command
        adapter = build_adapters().get(self.harness)
        return adapter.binary if adapter else ""

    @property
    def available(self) -> bool:
        binary = self.binary
        return bool(binary) and shutil.which(binary) is not None


@dataclass
class CriticResult:
    """The outcome of one critic round — the JSON envelope's payload."""

    critic: str
    harness: str = ""
    model: str = ""
    attribution: str = ""
    ok: bool = False
    exit_code: int = -1
    duration_seconds: float = 0.0
    output: str = ""
    error: str = ""
    usage: Usage = field(default_factory=Usage)

    def as_dict(self) -> dict:
        return {
            "critic": self.critic,
            "harness": self.harness,
            "model": self.model,
            "attribution": self.attribution,
            "ok": self.ok,
            "exitCode": self.exit_code,
            "durationSeconds": round(self.duration_seconds, 3),
            "output": self.output,
            "error": self.error,
            "usage": {
                "inputTokens": self.usage.input_tokens,
                "outputTokens": self.usage.output_tokens,
                "cacheReadTokens": self.usage.cache_read_tokens,
                "cacheWriteTokens": self.usage.cache_write_tokens,
                "costUsd": self.usage.cost_usd,
                "present": self.usage.present,
            },
        }


# --------------------------------------------------------------------------- load


def load_critics(config_path: Optional[Path] = None) -> List[Critic]:
    """Every ``critics[]`` entry of the operator's CLI config.

    The roster moved out of the repository's harness config in issue-352
    (decision-123): a critic is a harness and a model installed on the machine
    that runs the round, so it is the operator's to declare — and executable
    configuration no longer lives in a file a pull request can edit.
    ``config_path`` defaults to the resolved CLI config (``--config``, the env var,
    the checkout's, the home directory's).

    Read **strictly**: an absent file is "no critics configured", but a file that
    exists and does not parse raises, because "no critics" and "the file naming
    them is broken" would otherwise look identical and the second is a false green.

    Raises :class:`CriticConfigError` only for problems that make the *whole*
    configuration ambiguous (unparseable file, not a list, duplicate names). A
    problem with one entry is recorded on that entry's ``error``.
    """
    from .cli_config import _load_cli_config_raw, default_cli_config_path

    path = Path(config_path) if config_path is not None else default_cli_config_path()
    if not path.is_file():
        return []
    try:
        data = _load_cli_config_raw(path, strict=True)
    except Exception as exc:  # noqa: BLE001 — any parse failure is the same to us
        raise CriticConfigError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CriticConfigError(f"{path} does not contain a YAML mapping")
    entries = data.get("critics") or []
    if not isinstance(entries, list):
        raise CriticConfigError(f"{path}: critics must be a list")

    critics = [_critic_from_entry(entry, index) for index, entry in enumerate(entries)]
    seen: Dict[str, int] = {}
    for index, critic in enumerate(critics):
        if critic.name in seen:
            raise CriticConfigError(
                f"{path}: two critics entries are both named "
                f"{critic.name!r} (#{seen[critic.name] + 1} and #{index + 1}); "
                "names identify a critic, so they must be unique"
            )
        seen[critic.name] = index
    return critics


#: The review-round policy's defaults — what an absent ``reviews`` block means, and
#: what a harness with no CLI installed follows (the skill states the same numbers).
REVIEW_POLICY_DEFAULTS: Dict[str, Any] = {
    "selfReviewCount": 3,
    "criticReviewCount": 3,
    "stopOnNoNewFindings": True,
    "escalateOnRepeatFinding": True,
}


def load_review_policy(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """The operator's ``reviews`` block, with every key defaulted.

    Moved here from the repository's harness config in issue-352 (decision-123):
    the operator who runs the rounds sets how many. Read the way :func:`load_critics`
    reads — strictly, from the resolved CLI config — and, like it, an absent file is
    simply the defaults. Unknown keys are ignored (the schema refuses them at
    validation time); a key of the wrong type raises, because a cap that is not an
    integer is a policy nobody can follow.
    """
    from .cli_config import _load_cli_config_raw, default_cli_config_path

    path = Path(config_path) if config_path is not None else default_cli_config_path()
    policy: Dict[str, Any] = dict(REVIEW_POLICY_DEFAULTS)
    if not path.is_file():
        return policy
    try:
        data = _load_cli_config_raw(path, strict=True)
    except Exception as exc:  # noqa: BLE001 — any parse failure is the same to us
        raise CriticConfigError(f"could not parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise CriticConfigError(f"{path} does not contain a YAML mapping")
    block = data.get("reviews") or {}
    if not isinstance(block, dict):
        raise CriticConfigError(f"{path}: reviews must be a mapping")
    for key, default in REVIEW_POLICY_DEFAULTS.items():
        if key not in block:
            continue
        value = block[key]
        if isinstance(default, bool):
            if not isinstance(value, bool):
                raise CriticConfigError(f"{path}: reviews.{key} must be true or false")
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CriticConfigError(
                f"{path}: reviews.{key} must be a non-negative integer"
            )
        policy[key] = value
    return policy


def find_critic(name: str, config_path: Optional[Path] = None) -> Critic:
    """The critic called ``name``, or a :class:`CriticConfigError` naming the rest."""
    critics = load_critics(config_path)
    for critic in critics:
        if critic.name == name:
            return critic
    known = ", ".join(c.name for c in critics) or "none"
    raise CriticConfigError(
        f"no critic named {name!r} in the CLI config's critics[] (configured: {known})"
    )


def _critic_from_entry(entry: object, index: int) -> Critic:
    """One config entry → a :class:`Critic`, with its problems on ``error``."""
    if not isinstance(entry, dict):
        return Critic(
            name=f"<entry #{index + 1}>", error="entry is not a mapping of keys"
        )
    name = str(entry.get("name") or "").strip()
    args = [str(a) for a in (entry.get("args") or [])]
    raw_env = entry.get("env") or {}
    env = (
        {str(k): str(v) for k, v in raw_env.items()}
        if isinstance(raw_env, dict)
        else {}
    )
    output_format = str(entry.get("outputFormat") or "text")
    raw_timeout = entry.get("timeoutSeconds")
    try:
        # `or DEFAULT` would silently rewrite a configured 0 into 900 — a value
        # that must be rejected, not defaulted.
        timeout = DEFAULT_TIMEOUT_SECONDS if raw_timeout is None else float(raw_timeout)
    except (TypeError, ValueError):
        timeout = -1.0
    critic = Critic(
        name=name or f"<unnamed entry #{index + 1}>",
        harness=str(entry.get("harness") or ""),
        model=str(entry.get("model") or ""),
        command=str(entry.get("command") or ""),
        args=tuple(args),
        env=env,
        cwd=str(entry.get("cwd") or ""),
        output_format=output_format,
        timeout_seconds=timeout,
        enabled=bool(entry.get("enabled", True)),
        error=_validate(entry, name, args, output_format, timeout, index),
    )
    return critic


def _validate(
    entry: dict,
    name: str,
    args: List[str],
    output_format: str,
    timeout: float,
    index: int,
) -> str:
    """Why this entry cannot be run, or "" when it can. Fail-closed, never spawns."""
    if not name:
        return f"entry #{index + 1} has no 'name'; a critic is run by name"
    if not isinstance(entry.get("args") or [], list):
        return "'args' must be a list of argv elements"
    if not isinstance(entry.get("env") or {}, dict):
        # Silently dropping it would run the critic without the environment the
        # operator believes they configured.
        return "'env' must be a mapping of NAME: value"
    if output_format not in _OUTPUT_FORMATS:
        return (
            f"unknown outputFormat {output_format!r}; expected one of "
            f"{', '.join(_OUTPUT_FORMATS)}"
        )
    if timeout <= 0:
        return "'timeoutSeconds' must be a positive number"
    for arg in args:
        for placeholder in _PLACEHOLDER_RE.findall(arg):
            if placeholder not in PLACEHOLDERS:
                return (
                    f"unknown placeholder {{{placeholder}}} in args; known "
                    f"placeholders are {', '.join('{%s}' % p for p in PLACEHOLDERS)}"
                )
    command = str(entry.get("command") or "")
    harness = str(entry.get("harness") or "")
    if command:
        if not _mentions_prompt(args):
            return (
                "args must pass the review material to the critic — include "
                "{prompt} or {promptFile}; without it the critic reviews nothing"
            )
    elif harness not in build_adapters():
        known = ", ".join(sorted(build_adapters()))
        return (
            f"harness {harness!r} has no built-in invocation (built-in: {known}); "
            "set 'command' (and 'args') to say how to run this critic"
        )
    return ""


def _mentions_prompt(args: Sequence[str]) -> bool:
    return any(
        placeholder in _PLACEHOLDER_RE.findall(arg)
        for arg in args
        for placeholder in _PROMPT_PLACEHOLDERS
    )


# ----------------------------------------------------------------------- resolve


def resolve_invocation(critic: Critic, values: Mapping[str, str]) -> List[str]:
    """``critic`` + this round's ``values`` → the full argv, executable first.

    Pure: it spawns nothing, which is what makes the substitution boundary cheap to
    test directly. Precedence is ``command`` > a built-in ``harness`` > refusal.
    Substitution is **element-wise** — a value is replaced inside the single argv
    element that mentions it and can never introduce a new argument, a redirect or a
    second command, because there is no shell to interpret one.
    """
    if critic.error:
        raise CriticConfigError(f"critic {critic.name!r}: {critic.error}")
    if not critic.enabled:
        raise CriticConfigError(f"critic {critic.name!r} is disabled in config")

    extra = [_substitute(arg, values) for arg in critic.args]
    if critic.command:
        return [critic.command] + extra

    adapter = build_adapters().get(critic.harness)
    if adapter is None:  # pragma: no cover - _validate rejects this first
        raise CriticConfigError(
            f"critic {critic.name!r}: harness {critic.harness!r} has no built-in "
            "invocation and no 'command' was configured"
        )
    prompt = values.get("prompt", "")
    return [adapter.binary] + adapter.oneshot_argv(prompt, critic.model) + extra


def _substitute(arg: str, values: Mapping[str, str]) -> str:
    def replace(match: "re.Match[str]") -> str:
        placeholder = match.group(1)
        if placeholder not in PLACEHOLDERS:
            raise CriticConfigError(
                f"unknown placeholder {{{placeholder}}} in args; known placeholders "
                f"are {', '.join('{%s}' % p for p in PLACEHOLDERS)}"
            )
        return values.get(placeholder, "")

    return _PLACEHOLDER_RE.sub(replace, arg)


# --------------------------------------------------------------------------- run


def run_critic(
    critic: Critic,
    values: Mapping[str, str],
    *,
    cwd: str,
    timeout: Optional[float] = None,
) -> CriticResult:
    """Run one critic round and return its envelope.

    Never raises for a critic *failure* — an absent binary, a non-zero exit and a
    timeout are all outcomes the harness has to record, so they come back as a
    result with ``ok=False``. A misconfiguration still raises
    :class:`CriticConfigError` from :func:`resolve_invocation`: there is nothing to
    record because nothing ran.
    """
    argv = resolve_invocation(critic, values)
    result = CriticResult(
        critic=critic.name,
        harness=critic.harness,
        model=critic.model,
        attribution=critic.attribution,
    )
    binary = argv[0]
    if shutil.which(binary) is None:
        result.error = (
            f"critic CLI {binary!r} not found on PATH; install it or point "
            f"critics[] entry {critic.name!r} at the right executable"
        )
        return result

    limit = timeout if timeout is not None else critic.timeout_seconds
    env = dict(os.environ)
    env.update(critic.env)
    logger.debug("running critic %s: %s (cwd=%s)", critic.name, binary, cwd)
    started = time.monotonic()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=limit,
            shell=False,  # RULE: never a shell — see this module's docstring
        )
    except subprocess.TimeoutExpired:
        result.duration_seconds = time.monotonic() - started
        result.error = f"{binary} timed out after {limit}s"
        return result
    except OSError as exc:
        result.duration_seconds = time.monotonic() - started
        result.error = f"could not run {binary}: {exc}"
        return result

    result.duration_seconds = time.monotonic() - started
    result.exit_code = proc.returncode
    result.output = _extract_output(proc.stdout, critic.output_format)
    result.usage = usage_from_output(proc.stdout)
    if proc.returncode != 0:
        result.error = (
            f"{binary} exited {proc.returncode}: "
            f"{proc.stderr.strip() or proc.stdout.strip()}"
        )
        return result
    result.ok = True
    return result


def _extract_output(stdout: str, output_format: str) -> str:
    """The reviewer's text, falling back to raw stdout rather than to nothing.

    A critic that printed prose where JSON was configured still produced a review;
    reporting an empty one would lose findings a human already paid for.
    """
    if output_format != "json":
        return stdout
    data = parse_json_object(stdout)
    for key in _TEXT_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    return stdout
