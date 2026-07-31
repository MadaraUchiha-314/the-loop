"""Assembling a :class:`Runtime` from the configs on disk.

Extracted from ``commands/graph_cmd.py`` when the ingress gained a second call
site (issue-113). It matters that there is only one of these: the runtime's
``config`` is what carries ``authorizedUsers`` to ``classify-feedback``, and a
second, subtly different assembly is how a gate ends up reading an empty
authorized-user list and failing closed forever on one path while working on the
other.

Both configs are read best-effort — a missing or malformed one yields defaults
rather than an error, because ``the-loop check`` must work in a repo that has
never seen the CLI config, and the daemon must work in a checkout that has no
harness config.

The harness half is read through :mod:`the_loop.harness_config`, the CLI's only
reader of that file (issue-121, decision-044). ``load_harness_config`` stays
exported here because it is this package's established name for it.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .. import harness_config
from ..harness_config import load as load_harness_config

logger = logging.getLogger("the-loop.graph")

__all__ = ["build_runtime", "load_harness_config"]


def build_runtime(
    root: Path,
    spec_root: Optional[str] = None,
    authorized_users: Optional[Sequence[str]] = None,
):
    """A runtime for ``root``, configured from the harness and CLI configs.

    Both overrides exist, for **different** reasons — a distinction worth keeping
    apart, because stating one reason for both is what produced issue-123:

    * ``authorized_users`` is a **CLI-config** value. The daemon has already parsed its
      own CLI config, honouring ``--config``, so re-reading the default path here could
      disagree with the config the process is actually running. It passes what it parsed.
    * ``spec_root`` is a **harness-config** value, read from ``root`` itself. There is no
      ``--config`` ambiguity to protect against, so the repository's own
      ``workflow.specDir`` is the answer unless a caller deliberately overrides it —
      ``webhooks.ghWebhook.routing.graph.specDir``, for a checkout that carries no harness
      config. Until issue-123 that key was never unset, so this fall-through was
      unreachable on the daemon path and no watched repository's value was ever honoured.
    """
    from .runtime import Runtime

    harness = load_harness_config(root)
    workflow = harness.get("workflow") or {}
    config: Dict[str, Any] = {
        "phaseLabelPrefix": workflow.get("phaseLabelPrefix", "loop:"),
        "notifications": harness.get("notifications") or {},
        "authorizedUsers": list(authorized_users or []),
        "integrations": {},
    }
    try:
        from .. import cli_config

        cli_cfg = cli_config.load_cli_config(cli_config.default_cli_config_path()) or {}
    except Exception:  # noqa: BLE001 — the CLI config is optional for `check`
        cli_cfg = {}
    if isinstance(cli_cfg, dict):
        config["integrations"] = cli_cfg.get("integrations") or {}
        if authorized_users is None:
            routing = ((cli_cfg.get("webhooks") or {}).get("ghWebhook") or {}).get(
                "routing"
            ) or {}
            config["authorizedUsers"] = routing.get("authorizedUsers") or []
    return Runtime(
        root,
        spec_root=str(spec_root or harness_config.spec_dir(harness)),
        config=config,
    )
