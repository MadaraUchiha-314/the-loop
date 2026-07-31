"""Config migrations — breaking changes, made safe by being mechanical.

issue-109 removes the per-feature ``ghBinary`` keys in favour of one
``integrations`` block, because three copies of one setting is exactly the
duplication that block exists to remove. issue-128 removes ``polling.stateFile``
for a different reason: the poller's ledger became one record per work item, so
a *file* path has nothing to point at. The owner's call was to make it a
**breaking** change rather than carry a shadow override forever: *"Let's make
breaking changes. /upgrade should be able to handle it."*

A breaking change is only as good as its migration, so four properties hold:

1. **Version the schema, don't sniff for keys** — detection is exact.
2. **Fail closed and loudly.** A config still carrying a removed key makes the
   runtime refuse to start, naming the key, its replacement and the exact
   command. Silently ignoring a value the operator deliberately set would change
   their behaviour without telling them — much worse than an error.
3. **The migration is a deterministic key move**, idempotent and previewable,
   that *reports* what it changed rather than rewriting the file quietly.
4. **It is tested both ways** — old config migrates to the expected new one, and
   the runtime refuses an un-migrated one.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Tuple

__all__ = [
    "CURRENT_CONFIG_VERSION",
    "ConfigTooOld",
    "MigrationReport",
    "assert_current",
    "migrate_cli_config",
    "needs_migration",
]

#: Bumped by issue-109, then by issue-128. A config below this needs
#: `/the-loop:upgrade-the-loop`.
CURRENT_CONFIG_VERSION = "0.3.0"

_UPGRADE = "/the-loop:upgrade-the-loop"

# Where the per-feature `ghBinary` keys lived, and what replaced them.
_GH_BINARY_SITES: Tuple[Tuple[str, ...], ...] = (
    ("webhooks", "ghWebhook", "routing", "control"),
    ("webhooks", "ghWebhook", "routing", "reactions"),
    ("webhooks", "ghWebhook", "routing", "announce"),
)
_REPLACEMENT = "integrations.github.cli.binary"

# issue-128 reorganised generated state by portability: the poller's ledger is
# now one record per work item under `<state.root>/portable/`, so a *file* path
# has nowhere to point. `state.root` is the knob that replaced it.
_STATE_FILE_SITE: Tuple[str, ...] = ("polling",)
_STATE_FILE_KEY = "stateFile"
_STATE_FILE_REPLACEMENT = "state.root"


class ConfigTooOld(RuntimeError):
    """The config predates a breaking change. Always names the fix."""


@dataclass
class MigrationReport:
    """What a migration changed — reported, never applied silently."""

    changed: bool = False
    moves: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        if not self.changed:
            return "config is already current; nothing to migrate"
        lines = ["migrated the CLI config:"]
        lines += [f"  · {m}" for m in self.moves]
        lines += [f"  note: {n}" for n in self.notes]
        return "\n".join(lines)


def _dig(data: Mapping[str, Any], path: Tuple[str, ...]) -> Dict[str, Any] | None:
    node: Any = data
    for key in path:
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def _parts(version: str) -> Tuple[int, ...]:
    out = []
    for chunk in str(version).split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out or (0,))


def needs_migration(config: Mapping[str, Any]) -> bool:
    """True when this config predates the current schema, or still carries a
    removed key (belt and braces: a hand-edited file may lie about its version)."""
    if _parts(str(config.get("version", "0"))) < _parts(CURRENT_CONFIG_VERSION):
        return True
    if (_dig(config, _STATE_FILE_SITE) or {}).get(_STATE_FILE_KEY) is not None:
        return True
    return any(
        (section or {}).get("ghBinary") is not None
        for section in (_dig(config, path) for path in _GH_BINARY_SITES)
    )


def assert_current(config: Mapping[str, Any]) -> None:
    """Refuse to run on an un-migrated config, naming the exact fix (R6a.6).

    **Migrate broadly, refuse narrowly.** :func:`needs_migration` is generous —
    the upgrade command should stamp a version onto anything that lacks one. This
    gate is not, because it stops the daemon. It refuses exactly two things:

    1. A **removed key is still present.** Honouring the config would mean
       ignoring a value the operator deliberately set, silently changing their
       behaviour. That is the failure this whole mechanism exists to prevent.
    2. The config **declares** a version older than the current one. It says it
       is stale; believe it.

    An *unset* version with no removed keys is not refused. There is nothing to
    lose and nothing to move — most likely a minimal hand-written config — and a
    gate that stops a daemon over a missing bookkeeping key is a gate operators
    learn to route around.
    """
    stale = [
        ".".join(path) + ".ghBinary"
        for path in _GH_BINARY_SITES
        if (_dig(config, path) or {}).get("ghBinary") is not None
    ]
    if stale:
        raise ConfigTooOld(
            "this CLI config still declares "
            + ", ".join(stale)
            + f". That key was removed in favour of `{_REPLACEMENT}`, so transport "
            "is declared once instead of three times. It is NOT being ignored — "
            f"ignoring a value you set would change behaviour silently. Run "
            f"`{_UPGRADE}` to migrate."
        )
    if (_dig(config, _STATE_FILE_SITE) or {}).get(_STATE_FILE_KEY) is not None:
        raise ConfigTooOld(
            "this CLI config still declares `polling.stateFile`. The poller's "
            "ledger is now one record per work item under "
            "`<state.root>/portable/` (issue-128), so a file path has nowhere to "
            f"point; `{_STATE_FILE_REPLACEMENT}` moves it instead. It is NOT "
            "being ignored — a poller silently writing somewhere other than where "
            f"you pointed it is how a thread gets re-forwarded. Run `{_UPGRADE}` "
            "to migrate."
        )
    declared = config.get("version")
    if declared is not None and _parts(str(declared)) < _parts(CURRENT_CONFIG_VERSION):
        raise ConfigTooOld(
            f"this CLI config is version {declared}; "
            f"the installed the-loop needs {CURRENT_CONFIG_VERSION}. Run "
            f"`{_UPGRADE}` to migrate."
        )


def migrate_cli_config(config: Mapping[str, Any]) -> MigrationReport:
    """Move the removed keys into ``integrations``. Deterministic and idempotent.

    Running it twice produces the same file and reports no second change, which
    is what makes it safe to wire into an upgrade command that may be re-run.
    """
    data = copy.deepcopy(dict(config))
    report = MigrationReport(config=data)

    binaries: List[str] = []
    for path in _GH_BINARY_SITES:
        section = _dig(data, path)
        if section is None or "ghBinary" not in section:
            continue
        value = str(section.pop("ghBinary"))
        binaries.append(value)
        report.moves.append(f"{'.'.join(path)}.ghBinary → {_REPLACEMENT} ({value!r})")
        report.changed = True

    if binaries:
        distinct = sorted(set(binaries))
        integrations = data.setdefault("integrations", {})
        github = integrations.setdefault("github", {})
        cli = github.setdefault("cli", {})
        cli.setdefault("binary", distinct[0])
        github.setdefault("transport", "auto")
        if len(distinct) > 1:
            report.notes.append(
                "the removed keys disagreed ("
                + ", ".join(repr(b) for b in distinct)
                + f"); kept {distinct[0]!r} — one transport is declared once now, "
                "so please confirm this is the one you want"
            )

    polling = _dig(data, _STATE_FILE_SITE)
    if polling is not None and _STATE_FILE_KEY in polling:
        old = str(polling.pop(_STATE_FILE_KEY))
        report.moves.append(
            f"polling.{_STATE_FILE_KEY} ({old!r}) removed — the ledger is now "
            f"`<state.root>/portable/<work item>.json`"
        )
        report.changed = True
        if old and not old.startswith(str((data.get("state") or {}).get("root", ""))):
            report.notes.append(
                f"the old ledger at {old!r} is still READ once per work item, so "
                "no watched thread is re-baselined; delete it once `the-loop "
                "events` looks right on the new layout"
            )

    if _parts(str(data.get("version", "0"))) < _parts(CURRENT_CONFIG_VERSION):
        report.moves.append(
            f"version {data.get('version', '(unset)')!r} → {CURRENT_CONFIG_VERSION!r}"
        )
        data["version"] = CURRENT_CONFIG_VERSION
        report.changed = True

    return report
