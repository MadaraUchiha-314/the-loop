"""The schemas are the plugin's, not the project's (issue-220).

``/the-loop:init`` used to copy up to 118 KB of the-loop's own JSON schemas into every
repository it initialized — ``harness-config.schema.json`` (57 KB),
``collaborators.schema.json`` (5 KB) and, for operators tracking the CLI config in the
repo, ``cli-config.schema.json`` (56 KB). They are the plugin's contract, the plugin
already ships them, and a copy only goes stale. Issue-220 retired the copies the same way
issue-36 retired the template copies: the manifest stops calling them project files and
starts declaring where they live in the plugin.

That arrangement is spread across four files that no single reader looks at together:

=========================================  =====================================================
``.the-loop/manifest.yaml``                declares ``schemasDir`` and deprecates the copies
``.the-loop/*.schema.json``                the schemas themselves
``skills/the-loop/templates/*.yaml``       the configs ``/init`` scaffolds
``cli/the_loop/harness-config.default.yaml``  the config the CLI writes when adopting a repo
=========================================  =====================================================

Four assertions, one per way the arrangement can rot:

==  =====================================================  ================================
S1  ``schemasDir`` resolves and holds all three schemas    a schema moved or was renamed
S2  no ``meta`` entry names a schema                       ``/init`` was told to copy again
S3  all three copies are ``deprecated``                    ``/upgrade`` stops cleaning up
S4  every scaffolded config points at a real schema        a modeline lost its target
==  =====================================================  ================================

S4 is also the reason the modeline is asserted to be on the **first line**:
``yaml-language-server`` honours the directive only there, so a modeline that drifts down
the file is a comment that does nothing — visibly present, silently useless.

Pure filesystem reads: no network, no subprocess. Skipped when the plugin tree is absent,
as ``test_graph_parity.py`` is, so a source distribution shipping ``cli/`` alone passes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".the-loop" / "manifest.yaml"
TEMPLATES = REPO_ROOT / "skills" / "the-loop" / "templates"

pytestmark = pytest.mark.skipif(
    not MANIFEST.is_file() or not TEMPLATES.is_dir(),
    reason="plugin tree not present (source distribution)",
)

#: The three schemas the plugin owns. Every one of them was, until issue-220, copied into
#: the project by ``/the-loop:init``.
SCHEMAS = (
    "harness-config.schema.json",
    "collaborators.schema.json",
    "cli-config.schema.json",
)

#: Every config file the-loop scaffolds into a project, and the schema that validates it.
#: The packaged default is byte-identical to its template
#: (``test_harness_config.test_the_packaged_default_is_the_shipped_template``) but is
#: listed separately: it is written by a different code path (adoption, issue-193) and a
#: future divergence must fail here rather than silently ship a config with no modeline.
SCAFFOLDED: Dict[str, str] = {
    "skills/the-loop/templates/harness-config.yaml": "harness-config.schema.json",
    "skills/the-loop/templates/collaborators.yaml": "collaborators.schema.json",
    "skills/the-loop/templates/cli-config.yaml": "cli-config.schema.json",
    "cli/the_loop/harness-config.default.yaml": "harness-config.schema.json",
}

#: The editor directive. ``yaml-language-server`` reads it from the first line only.
MODELINE_PREFIX = "# yaml-language-server: $schema="


def _manifest() -> Dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _paths(entries) -> List[str]:
    return [str(entry.get("path", "")) for entry in (entries or [])]


def test_the_manifest_declares_where_the_schemas_live() -> None:
    """S1 — R2.1, R2.2.

    Feature: the-loop's schemas ship with the plugin
      Scenario: the manifest's schemasDir resolves to the shipped schemas
        Given the manifest declares schemasDir relative to ${CLAUDE_PLUGIN_ROOT}
        When a command resolves a schema through it
        Then all three of the-loop's schemas are found there
        Requirement: docs/specs/issue-220/requirements.md#requirement-2
    """
    declared = _manifest().get("schemasDir")
    assert declared, (
        "`.the-loop/manifest.yaml` must declare `schemasDir` — the one place a command "
        "or a tool resolves the-loop's schemas from, mirroring `templatesDir` (issue-220)"
    )
    directory = REPO_ROOT / declared
    assert directory.is_dir(), (
        f"manifest.schemasDir points at {directory}, which is not a directory"
    )
    missing = [name for name in SCHEMAS if not (directory / name).is_file()]
    assert not missing, (
        f"manifest.schemasDir ({declared}) is missing {missing}. The plugin ships the "
        "schemas; a consuming project no longer has a copy to fall back on."
    )


def test_no_schema_is_tracked_as_a_project_file() -> None:
    """S2 — R2.3.

    Feature: the-loop's schemas ship with the plugin
      Scenario: the manifest claims no schema as a project file
        Given `meta` enumerates what the-loop creates inside a project
        When the schemas are the plugin's own
        Then no `meta` entry names a *.schema.json path
        Requirement: docs/specs/issue-220/requirements.md#requirement-2
    """
    tracked = [
        path
        for path in _paths(_manifest().get("meta"))
        if path.endswith(".schema.json")
    ]
    assert not tracked, (
        f"`meta` still tracks {tracked}. Anything listed there is created in the "
        "operator's repository; the schemas are internal to the-loop (issue-220) and are "
        "resolved from `${CLAUDE_PLUGIN_ROOT}` via `schemasDir` instead."
    )


def test_every_retired_schema_copy_is_deprecated() -> None:
    """S3 — R3.1.

    Feature: the-loop's schemas ship with the plugin
      Scenario: every retired schema copy is listed as deprecated
        Given projects initialized by older versions carry a copy of each schema
        When `/the-loop:upgrade-the-loop` walks `manifest.deprecated`
        Then it finds all three copies and can remove them
        Requirement: docs/specs/issue-220/requirements.md#requirement-3
    """
    deprecated = set(_paths(_manifest().get("deprecated")))
    missing = [
        f".the-loop/{name}" for name in SCHEMAS if f".the-loop/{name}" not in deprecated
    ]
    assert not missing, (
        f"{missing} are not listed under `manifest.deprecated`, so `/upgrade` leaves the "
        "stale copies in every project that has one — the cleanup this work item exists "
        "to deliver (issue-220)."
    )


@pytest.mark.parametrize("relative_path,schema", sorted(SCAFFOLDED.items()))
def test_every_scaffolded_config_points_at_a_schema_that_exists(
    relative_path: str, schema: str
) -> None:
    """S4 — R4.1, R4.2, R2.4.

    Feature: the-loop's schemas ship with the plugin
      Scenario: every scaffolded config points at a schema that exists
        Given a config file the-loop writes into a project
        When an editor opens it with no schema copy on disk
        Then its first line names the published schema that validates it
        Requirement: docs/specs/issue-220/requirements.md#requirement-4
    """
    path = REPO_ROOT / relative_path
    first_line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    assert first_line.startswith(MODELINE_PREFIX), (
        f"{relative_path} must open with `{MODELINE_PREFIX}<url>`. It is the operator's "
        "only editor validation now that the-loop no longer copies the schema into the "
        "project, and yaml-language-server honours the directive on the first line only."
    )
    url = first_line[len(MODELINE_PREFIX) :]
    assert url.rsplit("/", 1)[-1] == schema, (
        f"{relative_path} points its editor at {url!r}, which does not name {schema}"
    )
    assert (REPO_ROOT / _manifest()["schemasDir"] / schema).is_file(), (
        f"{relative_path} points at {schema}, which the plugin does not ship"
    )
