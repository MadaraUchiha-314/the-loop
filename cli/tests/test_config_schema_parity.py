"""The packaged schemas are the authored schemas (issue-222, T7).

``.the-loop/*.schema.json`` is the **authored** home: the file an editor's modeline points
at, the file ``scripts/validate_config.py`` runs against, the file ``manifest.schemasDir``
declares (issue-220). ``cli/the_loop/schemas/`` is a copy inside the distributed package,
because the control-plane service must serve and validate against a schema from a bare
``pip install the-loopy-one``, where no plugin checkout exists — the argument
``graph/model.py::shipped_graph_path`` already makes for the process graphs.

Two copies of one file is a staleness bug waiting to happen, so this asserts **byte**
parity rather than data parity: ``cp`` is then the only correct way to move a schema
change, and a re-serialization that silently changed formatting fails here.

Skipped when the plugin tree is absent (a source distribution shipping ``cli/`` alone),
as ``test_graph_parity.py`` is.
"""

from pathlib import Path

import pytest

from the_loop import configschema

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORED = REPO_ROOT / ".the-loop"

SCHEMAS = ("cli-config", "collaborators")

pytestmark = pytest.mark.skipif(
    not AUTHORED.is_dir(), reason="plugin tree not present (source distribution)"
)


@pytest.mark.parametrize("name", SCHEMAS)
def test_the_packaged_schema_is_the_authored_schema(name):
    """
    Feature: the-loop's schemas ship with the runtime that needs them
      Scenario: the package copy drifts from the authored schema
        Given .the-loop/<name>.schema.json, the authored contract
        When it is compared with the copy under cli/the_loop/schemas/
        Then the two are byte-identical

    Requirement: docs/specs/issue-222/design.md §Where the schema comes from
    """
    authored = (AUTHORED / f"{name}.schema.json").read_bytes()
    packaged = configschema.schema_path(name).read_bytes()
    assert authored == packaged, (
        f"cli/the_loop/schemas/{name}.schema.json and .the-loop/{name}.schema.json have "
        "diverged. The one under .the-loop/ is authored; copy it over the packaged one."
    )


def test_the_packaged_schemas_are_inside_the_package():
    """A copy outside ``the_loop/`` would not travel in the wheel, which is the whole
    reason the copy exists."""
    package = Path(configschema.__file__).resolve().parent
    for name in SCHEMAS:
        assert package in configschema.schema_path(name).parents
