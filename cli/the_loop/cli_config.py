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
    routing = config.get("routing") or {}
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


class ConfigHolder:
    """The CLI config a long-lived process serves *now*, kept level with the file.

    The daemons have had this since issue-63: :class:`~the_loop.reload.Reloader`
    content-hashes the config path and rebuilds on change. The control-plane service did
    not — it closed over whatever it was handed at boot — so a config edited through its
    own API left it answering from the old one until somebody restarted it (issue-222).

    It lives here rather than beside the routes that drive it because the SDK holds one
    too (issue-212), and the SDK must be importable without FastAPI (NFR2). Refresh is
    driven **once per request** rather than per read: one ``sha256`` of a ~10 KB file per
    call, and no watcher thread. The rebuilt value replaces an attribute rather than
    mutating the dict in place, so a reader already running in another thread keeps a
    consistent document. A file that becomes unparseable keeps the previous value — that
    is ``Reloader``'s documented behaviour, and it is the right one: somebody is mid-edit,
    not asking for defaults.
    """

    def __init__(self, initial: Optional[dict], path: Union[str, Path]) -> None:
        from .reload import Reloader

        self.path = Path(path)
        self.current: dict = dict(initial or {})
        # Baselined to the file as it is now, so an unchanged file never rebuilds and a
        # holder built from an explicit dict keeps serving that dict.
        self._reloader = Reloader(self.path, self._build)

    def _build(self) -> dict:
        return load_cli_config(self.path, strict=True)

    def refresh(self) -> None:
        fresh = self._reloader.poll_for_change()
        if fresh is not None:
            self.current = fresh


def load_routing_config(path: Optional[Union[str, Path]] = None) -> dict:
    """The top-level ``routing`` block — the policy **both** ingresses run on.

    One accessor, because there is one block: the receiver, the poller and
    ``the-loop sessions`` all dispatch on the same values. It lived under
    ``webhooks.ghWebhook`` until issue-142, which meant the poller read its own
    dispatch policy by importing the webhook command's module — a coupling that
    told the reader the block belonged to the receiver, which it never did.

    The path is resolved per call rather than cached at import, so a ``--config``
    override set by :mod:`the_loop.cli`'s pre-scan is always honoured. Missing or
    unparseable config degrades to ``{}``, and an empty policy fails closed:
    ``authorizedUsers`` is then empty, so no human-authored event is acted on.
    """
    resolved = Path(path) if path is not None else default_cli_config_path()
    return load_cli_config(resolved, strict=False).get("routing") or {}
