"""Resolve and load the-loop's CLI config — independent of any repo checkout.

The CLI daemon (``gh-webhook``/``poll``/``sessions``/``events``) is expected to
work across multiple repos and is not tied to a single one (issue-63,
decision-032), so its settings (``webhooks``/``polling``/``eventLog``) do not
live in a repo's ``.the-loop/harness-config.yaml`` — that is the HARNESS (plugin) config
``/the-loop:*`` commands and the skill read. The CLI config file is named
``cli-config.yaml`` everywhere it's resolved, in priority order:

1. ``--config``/``-c`` (an explicit CLI flag; see ``cli.py``'s pre-scan).
2. ``$THE_LOOP_CLI_CONFIG`` (an explicit env var — same priority as ``--config``;
   whichever is set wins, the flag taking precedence if both are).
3. ``./.the-loop/cli-config.yaml`` (repo-relative) — an operator can choose to
   track their CLI config in a specific repo (e.g. a "dev box" repo) instead of
   their home directory; the daemon picks it up automatically when started from
   that checkout.
4. ``~/.the-loop/cli-config.yaml`` — the final, always-available fallback, not
   tied to any repo.

Best-effort about the *file*: a missing (or, leniently, unparseable) config
degrades to ``{}`` — callers fall back to their own built-in defaults — rather
than failing to start. The *parser* is not best-effort: PyYAML is a required
runtime dependency (issue-97, decision-038), because a CLI that cannot read its
own YAML config has nothing to fall back to but silence.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Union

import yaml

logger = logging.getLogger("the-loop.cli-config")

CLI_CONFIG_ENV = "THE_LOOP_CLI_CONFIG"
CLI_CONFIG_FILENAME = "cli-config.yaml"

# Set from --config (cli.py's pre-scan), highest priority in
# default_cli_config_path(). A module-level override rather than a threaded
# parameter: the CLI is a short-lived, single-invocation process, and several
# already-imported command modules cache the resolved path at parser-build
# time — see cli.py's _refresh_cli_config_paths().
_override: Optional[Path] = None


def set_override(path: Optional[Union[str, Path]]) -> None:
    """Set (or clear, with ``None``) the ``--config`` override."""
    global _override
    _override = Path(path) if path else None


def default_cli_config_path() -> Path:
    """Resolve the CLI config path — see the module docstring for priority."""
    if _override is not None:
        return _override
    env = os.environ.get(CLI_CONFIG_ENV)
    if env:
        return Path(env)
    cwd_candidate = Path(".the-loop") / CLI_CONFIG_FILENAME
    if cwd_candidate.is_file():
        return cwd_candidate
    return Path.home() / ".the-loop" / CLI_CONFIG_FILENAME


def _load_cli_config_raw(path: Path, strict: bool = False) -> dict:
    """Parse the whole CLI config file at ``path``.

    ``strict=False`` (defaults path): returns ``{}`` when the file is missing or
    unparseable, so a half-saved hand edit never breaks ingress.
    ``strict=True`` (hot-reload path): raises on a missing file / parse error, so
    a :class:`the_loop.reload.Reloader` keeps the previously loaded config
    instead of resetting to defaults on a transient broken save.
    """
    if not path.is_file():
        if strict:
            raise FileNotFoundError(f"{path} not found")
        return {}
    text = path.read_text()
    if strict:
        return yaml.safe_load(text) or {}  # let a YAMLError propagate
    try:
        return yaml.safe_load(text) or {}
    except Exception:  # noqa: BLE001 — a broken config must not break ingress
        logger.warning("could not parse %s; using built-in defaults", path)
        return {}


def apply_integrations(config: dict) -> dict:
    """Fan `integrations.github.cli.binary` out to the features that need it.

    issue-109 removed the three per-feature `ghBinary` keys in favour of one
    `integrations` block. The features still need a binary at call time, so the
    resolved value is injected here under a private key — declared once by the
    operator, available everywhere internally.
    """
    binary = str(
        (((config.get("integrations") or {}).get("github") or {}).get("cli") or {}).get(
            "binary", "gh"
        )
    )
    routing = ((config.get("webhooks") or {}).get("ghWebhook") or {}).get(
        "routing"
    ) or {}
    for feature in ("control", "reactions", "announce"):
        section = routing.get(feature)
        if isinstance(section, dict):
            section["_ghBinary"] = binary
    return config


def load_cli_config(path: Path, strict: bool = False) -> dict:
    """Load the CLI config, refusing one that predates a breaking change.

    The refusal is deliberate and loud (issue-109, R6a.6): a removed key is
    never silently ignored, because ignoring a value the operator set would
    change their behaviour without telling them.
    """
    data = _load_cli_config_raw(path, strict=strict)
    if data:
        from .migrations import assert_current

        assert_current(data)
        from .cli_config import apply_integrations as _apply

        _apply(data)
    return data
