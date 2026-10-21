"""The three init commands keep to their split (issue-514).

``/the-loop:init`` used to walk every config the-loop has: the repository's harness
config, the operator's CLI config, and a gateway's. Issue-514 split it three ways —
``/init`` for the repository, ``/init-cli`` for the daemon, ``/init-gateway`` for a
gateway host — so a repository that only *uses* the-loop is never asked about a daemon.

The commands are agent prose, so what holds the split is the text itself:

====  ============================================================  ===============================
C1    every shipped command is listed in the reference and skill    a command nobody can find
C2    ``/init`` names no daemon or gateway file, and no credential  the split quietly undone
C3    each init command offers ``--dry-run`` and ``--defaults``     three commands, three contracts
====  ============================================================  ===============================

C1 is general on purpose: the next command added is held to it too. C2 exempts the one
section of ``commands/init.md`` that points at the other two commands.

Pure filesystem reads. Skipped when the plugin tree is absent (a source distribution
shipping ``cli/`` alone).

Requirement: docs/specs/issue-514/design.md §Testing strategy
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMANDS = REPO_ROOT / "commands"
SKILL = REPO_ROOT / "skills" / "the-loop" / "SKILL.md"
REFERENCE = REPO_ROOT / "docs" / "reference" / "commands.md"

pytestmark = pytest.mark.skipif(
    not COMMANDS.is_dir(), reason="plugin tree not present (source distribution)"
)

INIT_COMMANDS = ("init", "init-cli", "init-gateway")

#: The heading of the one section of ``commands/init.md`` allowed to name the daemon's
#: and the gateway's files: the hand-off to the commands that own them.
HAND_OFF = "## Not set up here"

#: What ``/init`` must not touch (R1.2, R1.3) — the daemon's and the gateway's files and
#: the arming labels. Credential variables are matched separately, by shape.
DAEMON_TERMS = (
    "cli-config.yaml",
    "cli-config.schema.json",
    "gateway-config",
    "slack-app-manifest",
    "autoExecuteLabels",
    "autonomy profile",
    "deployment shape",
)

#: A credential variable's config key: ``tokenEnv``, ``secretEnv``, ``botTokenEnv``…
CREDENTIAL_KEY = re.compile(r"\b[a-z][A-Za-z]*Env\b")


def _stems() -> List[str]:
    return sorted(p.stem for p in COMMANDS.glob("*.md"))


def _lists(text: str, stem: str) -> bool:
    """Does ``text`` name ``/the-loop:<stem>`` as a whole command?

    A substring test would let ``/the-loop:init-cli`` stand in for ``/the-loop:init``,
    so the name must not run on into more of a command name (critic round 1).
    """
    return re.search(rf"/the-loop:{re.escape(stem)}(?![\w-])", text) is not None


def _section(text: str, heading: str) -> str:
    """The body under ``heading``, up to the next heading of the same level."""
    level = heading.split(" ", 1)[0]
    start = text.index(heading)
    following = re.search(rf"^{level} ", text[start + len(heading) :], re.M)
    end = start + len(heading) + following.start() if following else len(text)
    return text[start:end]


def _without_section(text: str, heading: str) -> str:
    if heading not in text:
        return text
    return text.replace(_section(text, heading), "")


def test_every_command_is_listed_in_the_reference_and_the_skill() -> None:
    """
    Feature: the commands a user can run are the commands the docs name
    Scenario: every shipped slash command is listed in the command reference and the skill
      Given every commands/*.md file the plugin ships
      When the command reference and the skill's Commands section are read
      Then each one names /the-loop:<command>

    Requirement: docs/specs/issue-514/requirements.md R2.1, R3.1, R5.1
    """
    reference = REFERENCE.read_text(encoding="utf-8")
    skill = _section(SKILL.read_text(encoding="utf-8"), "## Commands")
    missing = {
        where: [s for s in _stems() if not _lists(text, s)]
        for where, text in (
            ("docs/reference/commands.md", reference),
            ("SKILL.md § Commands", skill),
        )
    }
    assert not any(missing.values()), f"commands not listed: {missing}"
    for name in INIT_COMMANDS:
        assert name in _stems(), f"commands/{name}.md is not shipped"


def test_init_sets_up_no_daemon() -> None:
    """
    Feature: /init initializes the repository only
    Scenario: /init sets up no daemon
      Given commands/init.md without its hand-off section
      When it is searched for the daemon's and the gateway's files and for credentials
      Then it names none of them
      And the hand-off section names /the-loop:init-cli and /the-loop:init-gateway

    Requirement: docs/specs/issue-514/requirements.md R1.2, R1.3, R1.6
    """
    text = (COMMANDS / "init.md").read_text(encoding="utf-8")
    assert HAND_OFF in text, f"commands/init.md has no {HAND_OFF!r} section"
    hand_off = _section(text, HAND_OFF)
    assert "/the-loop:init-cli" in hand_off and "/the-loop:init-gateway" in hand_off
    body = _without_section(text, HAND_OFF)
    found = [term for term in DAEMON_TERMS if term in body]
    found += sorted(set(CREDENTIAL_KEY.findall(body)))
    assert not found, f"commands/init.md still sets up the daemon: {found}"


@pytest.mark.parametrize("name", INIT_COMMANDS)
def test_each_init_command_offers_both_modes(name: str) -> None:
    """
    Feature: the three init commands share one contract
    Scenario: each init command offers both modes
      Given commands/<name>.md for init, init-cli and init-gateway
      Then its argument hint is "[--dry-run] [--defaults]"
      And it has a Modes section naming both

    Requirement: docs/specs/issue-514/requirements.md R4.1
    """
    text = (COMMANDS / f"{name}.md").read_text(encoding="utf-8")
    assert 'argument-hint: "[--dry-run] [--defaults]"' in text
    modes = _section(text, "## Modes")
    assert "--dry-run" in modes and "--defaults" in modes
