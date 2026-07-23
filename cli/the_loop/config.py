"""CLI configuration loading for the-loop.

The the-loop CLI (webhook receiver + event routing) works across many repos and is
**not** tied to a single one, so its config lives at a user/machine level, separate
from a repo's ``.the-loop/config.yaml`` (the per-repo *plugin* config). See
``docs/decisions/decision-021.md`` and issue #63.

Resolution order for the CLI config file:

1. ``$THE_LOOP_CLI_CONFIG`` — explicit path override.
2. ``$XDG_CONFIG_HOME/the-loop/config.yaml`` (``XDG_CONFIG_HOME`` defaults to
   ``~/.config``).

Everything is best-effort: PyYAML is an optional dependency, so a missing file or a
missing ``yaml`` module yields ``{}`` and the CLI falls back to built-in defaults.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("the-loop.config")

# Legacy location: before issue #63 the webhook config lived under ``webhooks`` in the
# per-repo plugin config. We still read it (with a deprecation warning) so existing
# checkouts keep working until users migrate to the CLI config.
_LEGACY_PLUGIN_CONFIG = Path(".the-loop/config.yaml")


def cli_config_path() -> Path:
    """Resolve the CLI config file path (may not exist)."""
    override = os.environ.get("THE_LOOP_CLI_CONFIG")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base / "the-loop" / "config.yaml"


def _read_yaml(path: Path) -> dict:
    """Best-effort YAML read; ``{}`` when the file or PyYAML is unavailable."""
    if not path.is_file():
        return {}
    try:
        import yaml  # optional dependency
    except ImportError:
        logger.debug("pyyaml not installed; skipping config-file read of %s", path)
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:  # noqa: BLE001
        logger.warning("could not parse %s; ignoring it", path)
        return {}


def load_cli_config() -> dict:
    """Load the user/machine-level CLI config, or ``{}`` if none is present."""
    return _read_yaml(cli_config_path())


def load_gh_webhook_config() -> dict:
    """Return ``webhooks.ghWebhook`` for the webhook receiver.

    Reads the CLI config first. If it carries no ``webhooks`` block, fall back to the
    legacy per-repo ``.the-loop/config.yaml`` location (emitting a one-time deprecation
    warning) so pre-issue-63 checkouts keep working.
    """
    cli = load_cli_config()
    webhooks = (cli.get("webhooks") or {}).get("ghWebhook")
    if webhooks is not None:
        return webhooks or {}

    legacy = _read_yaml(_LEGACY_PLUGIN_CONFIG)
    legacy_webhooks = (legacy.get("webhooks") or {}).get("ghWebhook")
    if legacy_webhooks is not None:
        logger.warning(
            "reading CLI webhook config from the legacy per-repo location %s; move the "
            "'webhooks:' block to %s (see docs/decisions/decision-021.md)",
            _LEGACY_PLUGIN_CONFIG,
            cli_config_path(),
        )
        return legacy_webhooks or {}
    return {}
