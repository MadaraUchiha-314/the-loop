"""What the-loop expects to find on the host, stated once (issue-212 R5).

the-loop drives other people's programs: it spawns a harness CLI in tmux, it reads and
writes tickets through ``gh``, it clones with ``git``. Which of those a given deployment
actually needs depends on that deployment's CLI config — a service that only reads work
items and events needs none of them; one with routing enabled needs four.

That dependency was knowable only by reading the source, which is a poor way to discover
that a container image is missing ``gh`` on the day it goes to production. This module is
the table, in code:

* :data:`REQUIREMENTS` — one record per binary: what it is called, which config key can
  rename it, which capability it serves, and the predicate deciding whether *this*
  configuration needs it.
* :func:`check_environment` — that table, resolved against ``PATH``.

Two properties are deliberate. It **resolves, never executes** (``shutil.which`` and
nothing more): a preflight that runs ``--version`` on whatever a hostile ``PATH`` yields
is a way to become the vulnerability it is checking for. And it is a **report, never a
gate**: a missing binary keeps failing exactly where it fails today, reported by the code
that needed it — nothing here blocks a call.

The same table is the source for ``docs/sdk/environment.md``; a parity test asserts every
binary here appears on that page.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


def _dig(config: Optional[dict], path: str, default: Any = None) -> Any:
    """Read a dotted path out of a config document, tolerating absent branches."""
    node: Any = config or {}
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        node = node.get(part)
    return default if node is None else node


def _routing_on(config: Optional[dict]) -> bool:
    """Whether this deployment dispatches events into harness sessions at all.

    ``routing.enabled`` defaults to **false** (routing off = verify and log only), so a
    config that has not opted in needs no harness, no tmux and no git.
    """
    return bool(_dig(config, "routing.enabled", False))


def _ingress_on(config: Optional[dict]) -> bool:
    return bool(
        _dig(config, "polling.enabled", False)
        or _dig(config, "webhooks.ghWebhook.enabled", False)
    )


@dataclass(frozen=True)
class Requirement:
    """One external binary the-loop may invoke, and when it may invoke it."""

    #: The name looked up on ``PATH`` when ``config_key`` names nothing else.
    default_binary: str
    #: Dotted CLI-config path that can rename the binary; ``""`` when it is fixed.
    config_key: str
    #: What stops working without it — one clause, written for an operator.
    capability: str
    #: Does *this* configuration need it? Absent-means-no, never absent-means-maybe.
    required: Callable[[Optional[dict]], bool]

    def resolve(self, config: Optional[dict]) -> str:
        if not self.config_key:
            return self.default_binary
        return str(_dig(config, self.config_key, self.default_binary))


#: The contract, in declaration order — the order the report and the docs both use.
REQUIREMENTS: List[Requirement] = [
    Requirement(
        default_binary="gh",
        config_key="integrations.github.cli.binary",
        capability=(
            "GitHub ticket reads and writes: comments and the paper trail, reactions, "
            "announcements, polling, and the process graph's GitHub integration"
        ),
        # Anything that touches a ticket goes through `gh`: the dispatcher's paper
        # trail, the poller's issue reads, the graph's transition comments.
        required=lambda config: _routing_on(config) or _ingress_on(config),
    ),
    Requirement(
        default_binary="claude",
        config_key="",
        capability=(
            "spawning, resuming and one-shot critic runs of Claude Code sessions"
        ),
        required=lambda config: (
            _routing_on(config)
            and str(_dig(config, "routing.defaultHarness", "claude")) == "claude"
        ),
    ),
    Requirement(
        default_binary="cursor-agent",
        config_key="",
        capability="spawning and one-shot critic runs of Cursor sessions",
        required=lambda config: (
            _routing_on(config)
            and str(_dig(config, "routing.defaultHarness", "claude")) == "cursor"
        ),
    ),
    Requirement(
        default_binary="tmux",
        config_key="",
        capability=(
            "hosting harness sessions — the only runner since issue-156, and what makes "
            "a session attachable"
        ),
        required=_routing_on,
    ),
    Requirement(
        default_binary="git",
        config_key="routing.workspace.gitBinary",
        capability="cloning and worktree checkouts for spawned sessions",
        required=_routing_on,
    ),
    Requirement(
        default_binary="ttyd",
        config_key="",
        capability="serving tmux sessions to a browser (the web terminal)",
        required=lambda config: bool(
            _dig(config, "routing.webTerminal.enabled", False)
        ),
    ),
]


def check_environment(config: Optional[dict] = None) -> Dict[str, Any]:
    """Resolve every :data:`REQUIREMENTS` entry against ``PATH``.

    Returns ``{"ok": bool, "checks": [...]}``. ``ok`` is false only when a binary this
    configuration *requires* is absent — an optional one missing is a fact worth
    reporting, not a failure (R5.3).
    """
    checks: List[Dict[str, Any]] = []
    for requirement in REQUIREMENTS:
        binary = requirement.resolve(config)
        resolved = shutil.which(binary)
        checks.append(
            {
                "binary": binary,
                "present": resolved is not None,
                "path": resolved or "",
                "required": bool(requirement.required(config)),
                "capability": requirement.capability,
                "configKey": requirement.config_key,
            }
        )
    ok = not any(check["required"] and not check["present"] for check in checks)
    return {"ok": ok, "checks": checks}
