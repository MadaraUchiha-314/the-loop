"""Enable the-loop's own plugin in the harness before a spawn (issue-143).

Everything a spawned session knows about the loop — the ``the-loop`` skill, the
``/the-loop:*`` commands, the SessionStart hook that states the operating rules —
arrives through **the plugin**. Nothing in the spawn path installed it: the-loop
pre-seeded workspace trust and the bypass disclaimer (:mod:`the_loop.trust`) so
the session *starts*, then handed it a work-on prompt for machinery that was not
loaded. On a machine where nobody ran ``/plugin marketplace add`` by hand, the
session worked the ticket as a plain agent — no phase labels, no spec chain, no
gates.

Claude Code records a plugin in its **user settings file** with two keys, and
writing them is exactly what ``/plugin marketplace add`` + ``/plugin install``
do::

    {
      "extraKnownMarketplaces": {
        "the-loop": {"source": {"source": "github", "repo": "<owner>/<repo>"}}
      },
      "enabledPlugins": {"the-loop@the-loop": true}
    }

Same file, same discipline and the same writer as :mod:`the_loop.trust`: only
those two keys, merged into whatever is already there, temp file + atomic
replace, nothing written when the desired state already holds, and a file that
does not parse is reported rather than overwritten.

Two rules are specific to this module:

* **An existing value is never changed.** A marketplace named ``the-loop`` that
  already points somewhere (a fork, a local checkout) stays pointing there, and
  an ``enabledPlugins`` entry that is already ``false`` stays ``false`` — that is
  an operator's decision, not a stale value to correct.
* **Only ``owner/repo`` is written.** The repository comes from the operator's
  own config, never from an event payload or a cloned repo, and it is validated
  before it lands in the settings file.

The settings file is user-global, so this enables the-loop in the operator's own
interactive sessions too — the same asymmetry
``harnessTrust.acceptBypassPermissions`` carries, stated out loud in the schema
and the config docs. ``routing.harnessPlugins.enabled: false`` is the opt-out.

Spec: docs/specs/issue-143/design.md (decision-054).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .trust import ClaudeTrustStore, TrustResult, update_json

__all__ = [
    "DEFAULT_MARKETPLACE_REPO",
    "MARKETPLACE_NAME",
    "PLUGIN_KEY",
    "PLUGIN_NAME",
    "ClaudePluginStore",
    "PluginConfig",
]

#: Names from the shipped manifests — ``.claude-plugin/{marketplace,plugin}.json`` and
#: ``.cursor-plugin/{marketplace,plugin}.json``, which carry the same two names, so these
#: constants are correct for either harness (issue-157). A fork keeps them; only the
#: repository it is served from changes.
MARKETPLACE_NAME = "the-loop"
PLUGIN_NAME = "the-loop"
PLUGIN_KEY = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"

#: Where the plugin is served from unless the operator points elsewhere.
DEFAULT_MARKETPLACE_REPO = "MadaraUchiha-314/the-loop"

# GitHub owner/repo, and nothing else — no URL, no path, no shell metacharacters.
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")

_MARKETPLACES_KEY = "extraKnownMarketplaces"
_PLUGINS_KEY = "enabledPlugins"


@dataclass
class PluginConfig:
    """Mirror of ``routing.harnessPlugins`` (see config schema)."""

    enabled: bool = True
    #: ``owner/repo`` the marketplace is registered from; empty registers nothing
    #: and only enables the plugin, for an operator who adds the marketplace
    #: themselves.
    marketplace_repo: str = DEFAULT_MARKETPLACE_REPO

    @classmethod
    def from_mapping(cls, data: dict) -> "PluginConfig":
        data = data or {}
        repo = data.get("marketplaceRepo")
        return cls(
            enabled=bool(data.get("enabled", True)),
            marketplace_repo=(
                DEFAULT_MARKETPLACE_REPO if repo is None else str(repo).strip()
            ),
        )


class ClaudePluginStore:
    """Where Claude Code records enabled plugins, and how to set it.

    Path resolution is *delegated* to :class:`~the_loop.trust.ClaudeTrustStore`
    (which already reads ``$CLAUDE_CONFIG_DIR`` off the shipped CLI) rather than
    re-derived, so the two pre-spawn steps can never disagree about which file
    the harness reads. Tests inject a store with a fake HOME.
    """

    def __init__(
        self,
        store: Optional[ClaudeTrustStore] = None,
        settings_file: Optional[Path] = None,
    ):
        self._store = store or ClaudeTrustStore()
        # An explicit file overrides the resolved user-settings path, which is what
        # lets `the-loop install --scope project` (issue-152) write a repository's own
        # `.claude/settings.json` through this same writer instead of growing a second
        # one. The spawn path never passes it: the daemon's scope is the user file.
        self._settings_file = Path(settings_file) if settings_file else None

    def settings_path(self) -> Path:
        """The settings file this store writes.

        ``<config dir>/settings.json`` (the user file) unless an explicit
        ``settings_file`` was injected.
        """
        if self._settings_file is not None:
            return self._settings_file
        return self._store.settings_path()

    def enable(self, marketplace_repo: str = DEFAULT_MARKETPLACE_REPO) -> TrustResult:
        """Register the marketplace and enable the plugin, if not already set.

        Returns the no-op :class:`~the_loop.trust.TrustResult` (``ok``, empty
        ``applied``) when both keys already hold a value — the common case on
        every spawn after the first, and what keeps the daemon from rewriting the
        operator's settings file under an interactive session that has it open.
        """
        repo = str(marketplace_repo or "").strip()
        if repo and not _REPO_RE.match(repo):
            return TrustResult(
                ok=False,
                error=(
                    f"harnessPlugins.marketplaceRepo {repo!r} is not of the form "
                    "owner/repo; not writing it to "
                    f"{self.settings_path()}"
                ),
            )
        path = self.settings_path()
        problem = ""

        def mutate(data: dict) -> bool:
            nonlocal problem
            changed = False
            if repo:
                markets = data.get(_MARKETPLACES_KEY, {})
                if not isinstance(markets, dict):
                    problem = (
                        f"{path}: {_MARKETPLACES_KEY} is not a JSON object; "
                        "leaving it untouched"
                    )
                    return False
                if MARKETPLACE_NAME not in markets:
                    markets[MARKETPLACE_NAME] = {
                        "source": {"source": "github", "repo": repo}
                    }
                    data[_MARKETPLACES_KEY] = markets
                    changed = True
            plugins = data.get(_PLUGINS_KEY, {})
            if not isinstance(plugins, dict):
                problem = (
                    f"{path}: {_PLUGINS_KEY} is not a JSON object; leaving it untouched"
                )
                return False
            if PLUGIN_KEY not in plugins:
                # Present-but-false is an operator's decision, not a stale value.
                plugins[PLUGIN_KEY] = True
                data[_PLUGINS_KEY] = plugins
                changed = True
            return changed

        result = update_json(path, mutate)
        if problem:
            return TrustResult(ok=False, error=problem)
        if result.applied:
            result = TrustResult(applied=[f"enabled the {PLUGIN_KEY} plugin in {path}"])
        return result
