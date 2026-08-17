"""Config migrations — breaking changes, made safe by being mechanical.

issue-109 removes the per-feature ``ghBinary`` keys in favour of one
``integrations`` block, because three copies of one setting is exactly the
duplication that block exists to remove. issue-128 removes ``polling.stateFile``
for a different reason: the poller's ledger became one record per work item, so
a *file* path has nothing to point at. issue-142 removes
``webhooks.ghWebhook.routing`` for a third: the block was never the receiver's —
the poller reads it verbatim for dispatch and ``the-loop sessions`` reads it
again — so it is promoted to a top-level ``routing``, where its scope is legible
from the config's shape rather than from a comment. The owner's call was to make
these **breaking** changes rather than carry shadow overrides forever: *"Let's
make breaking changes. /upgrade should be able to handle it."*

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

#: Bumped by issue-109, then issue-128, then issue-142, then issue-245. A config
#: below this needs `/the-loop:upgrade-the-loop`.
CURRENT_CONFIG_VERSION = "0.5.0"

_UPGRADE = "/the-loop:upgrade-the-loop"

# Where the per-feature `ghBinary` keys lived, and what replaced them. Both
# spellings of the routing block are listed: a pre-issue-142 config nests it
# under the receiver, a hand-written one may already have promoted it, and
# either way the removed key must not survive the migration.
_GH_BINARY_SITES: Tuple[Tuple[str, ...], ...] = (
    ("webhooks", "ghWebhook", "routing", "control"),
    ("webhooks", "ghWebhook", "routing", "reactions"),
    ("webhooks", "ghWebhook", "routing", "announce"),
    ("routing", "control"),
    ("routing", "reactions"),
    ("routing", "announce"),
)
_REPLACEMENT = "integrations.github.cli.binary"

# issue-142 promoted the routing block. It configures what happens to an event
# *once accepted* — which the poller does with the very same values — so nesting
# it under `webhooks` claimed a scope it never had.
_ROUTING_SITE: Tuple[str, ...] = ("webhooks", "ghWebhook")
_ROUTING_KEY = "routing"

# issue-128 reorganised generated state by portability: the poller's ledger is
# now one record per work item under `<state.root>/portable/`, so a *file* path
# has nowhere to point. `state.root` is the knob that replaced it.
_STATE_FILE_SITE: Tuple[str, ...] = ("polling",)
_STATE_FILE_KEY = "stateFile"
_STATE_FILE_REPLACEMENT = "state.root"

# issue-245 converged Slack on the channels layer (owner's call on PR #267):
# `integrations.slack` was the write-only incoming webhook the graph's `notify`
# hook fired; the bot under `channels.slack` does that job and carries replies
# back. A webhook URL cannot be turned into a bot token, so the migration
# removes the key and says what to configure instead of pretending to convert.
_SLACK_SITE: Tuple[str, ...] = ("integrations",)
_SLACK_KEY = "slack"
_SLACK_REPLACEMENT = "channels.slack"


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
    if (_dig(config, _ROUTING_SITE) or {}).get(_ROUTING_KEY) is not None:
        return True
    if (_dig(config, _SLACK_SITE) or {}).get(_SLACK_KEY) is not None:
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

    1. A **removed key is still present** (``ghBinary``, ``polling.stateFile``,
       ``webhooks.ghWebhook.routing``). Honouring the config would mean
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
    if (_dig(config, _ROUTING_SITE) or {}).get(_ROUTING_KEY) is not None:
        raise ConfigTooOld(
            "this CLI config still declares `webhooks.ghWebhook.routing`. That "
            "block governs BOTH ingresses — the poller reads it verbatim for "
            "dispatch — so it moved to a top-level `routing` (issue-142). It is "
            "NOT being ignored: `routing.authorizedUsers` decides which GitHub "
            "logins may drive your daemon, and quietly falling back to none is "
            f"not a decision this config gets to make for you. Run `{_UPGRADE}` "
            "to migrate."
        )
    if (_dig(config, _SLACK_SITE) or {}).get(_SLACK_KEY) is not None:
        raise ConfigTooOld(
            "this CLI config still declares `integrations.slack`. The "
            "incoming-webhook integration was removed (issue-245): Slack is a "
            f"conversation channel now, configured once under "
            f"`{_SLACK_REPLACEMENT}` (a bot token, which also carries replies "
            "back). It is NOT being ignored — a notification you configured "
            f"silently going nowhere is worse than an error. Run `{_UPGRADE}` "
            "to migrate."
        )
    declared = config.get("version")
    if declared is not None and _parts(str(declared)) < _parts(CURRENT_CONFIG_VERSION):
        raise ConfigTooOld(
            f"this CLI config is version {declared}; "
            f"the installed the-loop needs {CURRENT_CONFIG_VERSION}. Run "
            f"`{_UPGRADE}` to migrate."
        )


def _promote_routing(data: Dict[str, Any], report: MigrationReport) -> None:
    """Move ``webhooks.ghWebhook.routing`` to the top level (issue-142).

    A hand-edited config may declare **both** blocks. The top-level one wins,
    key by key — never a deep merge and never a list union, because unioning two
    ``authorizedUsers`` lists would silently re-admit a login the operator had
    removed from the block they were actually maintaining. Whatever the old block
    declared and the new one overrode is named in the report, both values shown,
    so nothing is dropped without being said out loud.
    """
    receiver = _dig(data, _ROUTING_SITE)
    if receiver is None or _ROUTING_KEY not in receiver:
        return
    old = receiver.pop(_ROUTING_KEY) or {}
    report.changed = True
    report.moves.append(
        f"{'.'.join(_ROUTING_SITE)}.{_ROUTING_KEY} → {_ROUTING_KEY} (top level; it "
        "governs the poller too)"
    )

    current = data.setdefault(_ROUTING_KEY, {})
    if not isinstance(current, dict):  # a scalar under `routing`: refuse to guess
        report.notes.append(
            f"the existing top-level `routing` is {current!r}, not a block; the "
            "promoted one is kept and yours is dropped — re-declare it by hand"
        )
        current = {}
        data[_ROUTING_KEY] = current
    for key, value in old.items() if isinstance(old, dict) else ():
        if key in current:
            if current[key] != value:
                report.notes.append(
                    f"`routing.{key}` was declared in both places; kept the "
                    f"top-level {current[key]!r} and dropped {value!r}"
                )
            continue
        current[key] = value

    # Don't leave `webhooks: {ghWebhook: {}}` behind — a husk that says nothing
    # and invites the question of what used to be there.
    if not receiver:
        webhooks = data.get("webhooks")
        if isinstance(webhooks, dict):
            webhooks.pop("ghWebhook", None)
            if not webhooks:
                data.pop("webhooks", None)


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

    _promote_routing(data, report)

    integrations = _dig(data, _SLACK_SITE)
    if integrations is not None and _SLACK_KEY in integrations:
        integrations.pop(_SLACK_KEY)
        report.changed = True
        report.moves.append(
            f"integrations.{_SLACK_KEY} removed — Slack converged on "
            f"`{_SLACK_REPLACEMENT}` (issue-245)"
        )
        report.notes.append(
            "the incoming-webhook transport is gone and its URL cannot become "
            "a bot token: to keep Slack notifications, configure "
            "`channels.slack` (botTokenEnv, channel, and the notification "
            "event names under `events`) — the bot also carries replies back "
            "into the session"
        )
        if not integrations:
            data.pop("integrations", None)

    if _parts(str(data.get("version", "0"))) < _parts(CURRENT_CONFIG_VERSION):
        report.moves.append(
            f"version {data.get('version', '(unset)')!r} → {CURRENT_CONFIG_VERSION!r}"
        )
        data["version"] = CURRENT_CONFIG_VERSION
        report.changed = True

    return report
