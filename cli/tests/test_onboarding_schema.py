"""The `/the-loop:init` walkthrough metadata is consistent with the schema it annotates (issue-415).

``/the-loop:init`` does not hardcode what it asks. It reads ``x-onboarding`` out of the
config schema — which groups of keys are established together, in what order, at what ask
level — so the walkthrough cannot drift from what the config actually accepts
(``skills/the-loop/reference/onboarding.md``). Issue-415 gave ``cli-config.schema.json``
such a block, which is what put every automation the-loop has inside the walkthrough for
the first time, and added an **autonomy ladder** beside it: named rungs, each a small
bundle of config values, so a user's threshold for automation is one answer rather than
six interacting keys.

Metadata that annotates a schema rots against it silently. A key gets renamed and the
group that names it becomes a question about nothing; a new config block ships and no
group covers it, so nobody is ever asked; a profile sets ``routing.autoExecute`` long
after that key became ``routing.spawnOnUnmatched``, and the rung quietly does nothing.
None of that breaks a validator — ``x-*`` keywords are ignored by design — so it breaks
nothing until a person runs init and gets a worse onboarding than the one that was
written.

Seven assertions, one per way the block can rot:

====  ==========================================================  ==================================
A1    both schemas declare the same ask-level vocabulary          two walkthroughs, two procedures
A2    every group key exists in the schema                        a group asking about a dead key
A3    every configurable block is in exactly one group            a block nobody is ever asked about
A4    every profile value names a real key, with a legal value    a rung that silently does nothing
A5    no profile value reaches outside the ingress/execution set  **a rung buying away a human gate**
A6    the first rung is the shipped defaults                      "not yet" drifting into automation
A7    every rung is complete and the recommendation resolves      a ladder with a dangling rung
====  ==========================================================  ==================================

**A5 is the load-bearing one.** Requirement 3 of ``docs/specs/issue-415/requirements.md``
says autonomy never buys away a human gate: the phase-selection checklist, the artifact
approval gates and the risk tiers are fixed rules of the skill and the process graph, not
settings. A safety property that lives only in prose is a hope, so it is expressed here as
"no profile may write outside these six top-level blocks" — which is a red build the
moment somebody tries.

Pure filesystem reads: no network, no subprocess, no fixtures. Skipped when the plugin
tree is absent (a source distribution shipping ``cli/`` alone), as
``test_config_schema_parity.py`` is.

Requirement: docs/specs/issue-415/design.md §Testing strategy
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORED = REPO_ROOT / ".the-loop"

pytestmark = pytest.mark.skipif(
    not AUTHORED.is_dir(), reason="plugin tree not present (source distribution)"
)

#: The top-level blocks a profile may write. Everything the ingress and the execution of
#: a work item need, and nothing the process graph or the risk tiers read — which is what
#: makes A5 the mechanical form of requirement 3.
PROFILE_BLOCKS = frozenset(
    {"webhooks", "polling", "routing", "service", "selfDiagnosis", "channels"}
)

#: ``version`` belongs to no group in either schema: init stamps it, it is never asked.
UNGROUPED = frozenset({"version"})

#: Every rung says what it is, what it turns on, and what still needs a human.
RUNG_KEYS = ("id", "title", "summary", "stillHuman", "values")


def _schema(name: str) -> Dict[str, Any]:
    return json.loads((AUTHORED / f"{name}.schema.json").read_text(encoding="utf-8"))


def _onboarding(name: str) -> Dict[str, Any]:
    block = _schema(name).get("x-onboarding")
    assert isinstance(block, dict), (
        f"{name}.schema.json carries no x-onboarding block — /the-loop:init has nothing "
        "to drive its walkthrough with."
    )
    return block


def _resolve(schema: Dict[str, Any], path: str) -> Optional[Dict[str, Any]]:
    """The property subschema a dotted config path names, or ``None``."""
    node: Any = schema
    for segment in path.split("."):
        if not isinstance(node, dict):
            return None
        node = (node.get("properties") or {}).get(segment)
        if node is None:
            return None
    return node if isinstance(node, dict) else None


def _ladder(name: str = "cli-config") -> List[Dict[str, Any]]:
    profiles = _onboarding(name).get("profiles")
    assert isinstance(profiles, dict), "x-onboarding.profiles is missing"
    ladder = profiles.get("ladder")
    assert isinstance(ladder, list) and ladder, (
        "x-onboarding.profiles.ladder must be a non-empty array — an array because the "
        "order IS the ladder, and JSON object order is not a contract."
    )
    return ladder


def _type_ok(subschema: Dict[str, Any], value: Any) -> bool:
    declared = subschema.get("type")
    if declared is None:
        return True
    names = declared if isinstance(declared, list) else [declared]
    checks = {
        "boolean": lambda v: isinstance(v, bool),
        "string": lambda v: isinstance(v, str),
        "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "array": lambda v: isinstance(v, list),
        "object": lambda v: isinstance(v, dict),
        "null": lambda v: v is None,
    }
    return any(checks.get(one, lambda _v: True)(value) for one in names)


def test_a1_both_schemas_speak_one_ask_level_vocabulary() -> None:
    """
    Feature: one onboarding procedure, two configs
      Scenario: both schemas speak one ask-level vocabulary
        Given harness-config.schema.json and cli-config.schema.json
        When each one's x-onboarding.askLevels is read
        Then the two declare the same set of levels

    Requirement: docs/specs/issue-415/requirements.md R1.2
    """
    harness = set(_onboarding("harness-config").get("askLevels") or {})
    cli = set(_onboarding("cli-config").get("askLevels") or {})
    assert harness == cli, (
        "the two schemas' ask levels have diverged — reference/onboarding.md defines one "
        f"procedure, so one vocabulary: harness={sorted(harness)} cli={sorted(cli)}"
    )
    assert cli == {"always", "confirm", "advanced"}, (
        "the ask levels are a fixed vocabulary: always | confirm | advanced"
    )


def test_a2_every_group_names_keys_the_schema_defines() -> None:
    """
    Feature: the walkthrough cannot drift from the config
      Scenario: every onboarding group names keys the schema defines
        Given the CLI config schema's x-onboarding groups
        When each group's keys are looked up in the schema's properties
        Then every one of them exists

    Requirement: docs/specs/issue-415/requirements.md R1.3
    """
    schema = _schema("cli-config")
    known = set(schema.get("properties") or {})
    levels = set(_onboarding("cli-config").get("askLevels") or {})
    dangling = []
    for group in _onboarding("cli-config")["groups"]:
        assert group.get("ask") in levels, (
            f"group {group.get('id')!r} has ask level {group.get('ask')!r}, "
            f"which is not one of {sorted(levels)}"
        )
        assert group.get("title") and group.get("explain"), (
            f"group {group.get('id')!r} must carry a title and an explain paragraph — "
            "educating the user is mandatory, and the schema is where that text lives"
        )
        dangling += [
            f"{group['id']}.{key}" for key in group.get("keys", []) if key not in known
        ]
    assert not dangling, (
        "x-onboarding groups name keys the schema does not define — the key was renamed "
        "or removed:\n  " + "\n  ".join(sorted(dangling))
    )


def test_a3_every_configurable_block_is_in_exactly_one_group() -> None:
    """
    Feature: the walkthrough covers the config
      Scenario: every configurable block belongs to exactly one group
        Given the CLI config schema's top-level properties
        When they are matched against the x-onboarding groups
        Then each one appears in exactly one group, version excepted

    Requirement: docs/specs/issue-415/requirements.md R1.3
    """
    properties = set(_schema("cli-config").get("properties") or {}) - UNGROUPED
    seen: Dict[str, List[str]] = {}
    for group in _onboarding("cli-config")["groups"]:
        for key in group.get("keys", []):
            seen.setdefault(key, []).append(group["id"])
    uncovered = sorted(properties - set(seen))
    duplicated = sorted(
        f"{key} ({', '.join(ids)})" for key, ids in seen.items() if len(ids) > 1
    )
    assert not uncovered, (
        "in the schema but in no onboarding group — a key nobody is ever asked about; "
        "add it to a group in .the-loop/cli-config.schema.json:\n  "
        + "\n  ".join(uncovered)
    )
    assert not duplicated, (
        "in more than one onboarding group — a question asked twice:\n  "
        + "\n  ".join(duplicated)
    )


def test_a4_every_profile_value_names_a_real_key_with_a_legal_value() -> None:
    """
    Feature: an autonomy rung actually changes something
      Scenario: every profile value names a key the schema defines
        Given each rung of the autonomy ladder
        When its values' dotted paths are resolved against the schema
        Then each resolves, and each value is legal for the key it sets

    Requirement: docs/specs/issue-415/requirements.md R2.4
    """
    schema = _schema("cli-config")
    problems: List[str] = []
    for rung in _ladder():
        for path, value in (rung.get("values") or {}).items():
            target = _resolve(schema, path)
            if target is None:
                problems.append(f"{rung['id']}: {path} resolves to nothing")
                continue
            if not _type_ok(target, value):
                problems.append(
                    f"{rung['id']}: {path} = {value!r} is not a {target.get('type')}"
                )
            if "enum" in target and value not in target["enum"]:
                problems.append(
                    f"{rung['id']}: {path} = {value!r} is outside {target['enum']}"
                )
    assert not problems, (
        "an autonomy profile sets a key that does not exist or a value the key refuses — "
        "the rung silently does nothing:\n  " + "\n  ".join(problems)
    )


def test_a5_no_profile_value_reaches_a_key_that_guards_a_human_gate() -> None:
    """
    Feature: autonomy never buys away a human gate
      Scenario: no autonomy profile reaches a key that guards a human gate
        Given each rung of the autonomy ladder
        When the top-level block of every value it sets is collected
        Then every one is in the ingress-and-execution set, and authorizedUsers is untouched

    Requirement: docs/specs/issue-415/requirements.md R3.1, R3.2
    """
    escapes: List[str] = []
    grants: List[str] = []
    for rung in _ladder():
        for path in rung.get("values") or {}:
            if path.split(".", 1)[0] not in PROFILE_BLOCKS:
                escapes.append(f"{rung['id']}: {path}")
            if path.startswith("routing.authorizedUsers"):
                grants.append(f"{rung['id']}: {path}")
    assert not escapes, (
        "an autonomy profile writes outside "
        f"{sorted(PROFILE_BLOCKS)} — a threshold the user picked must not reach the "
        "process graph, the phase gates or the risk tiers, which are fixed rules and not "
        "settings:\n  " + "\n  ".join(escapes)
    )
    assert not grants, (
        "an autonomy profile grants authority — who may drive the loop is established "
        "with the user by name, never implied by a threshold they picked:\n  "
        + "\n  ".join(grants)
    )


def test_a6_the_first_rung_is_the_shipped_defaults() -> None:
    """
    Feature: "not yet" is a supported answer
      Scenario: the first rung is the shipped defaults
        Given the least autonomous rung of the ladder
        When each value it sets is compared with that key's schema default
        Then the two are equal

    Requirement: docs/specs/issue-415/requirements.md R2.5
    """
    schema = _schema("cli-config")
    first = _ladder()[0]
    drifted = []
    for path, value in (first.get("values") or {}).items():
        target = _resolve(schema, path) or {}
        if target.get("default") != value:
            drifted.append(
                f"{path}: rung says {value!r}, schema default is {target.get('default')!r}"
            )
    assert not drifted, (
        f"the least autonomous rung ({first['id']}) is not the shipped defaults — a user "
        'answering "not yet" would be given automation they did not ask for:\n  '
        + "\n  ".join(drifted)
    )


def test_a7_every_rung_is_complete_and_the_recommendation_resolves() -> None:
    """
    Feature: a ladder a reader can place themselves on
      Scenario: every rung explains itself and what still needs a human
        Given the autonomy ladder and its recommendation
        When each rung's fields are read
        Then every rung is complete, ids are unique, and the recommendation names a rung

    Requirement: docs/specs/issue-415/requirements.md R2.1, R2.2, R2.6
    """
    ladder = _ladder()
    ids = [rung.get("id") for rung in ladder]
    assert len(ids) == len(set(ids)), f"duplicate rung ids in the ladder: {ids}"
    incomplete = [
        f"{rung.get('id')}: missing {field}"
        for rung in ladder
        for field in RUNG_KEYS
        if not rung.get(field)
    ]
    assert not incomplete, (
        "a rung the user cannot evaluate — every rung states what it is, what it turns "
        "on and what still needs a human:\n  " + "\n  ".join(incomplete)
    )
    recommended = _onboarding("cli-config")["profiles"].get("recommended")
    assert recommended in ids, (
        f"the recommended profile {recommended!r} is not a rung of the ladder {ids}"
    )
