"""Unit tests for the packaged schema loader and validator (issue-222, T2).

A hand-written validator is only as trustworthy as the tests that keep it honest, so this
module holds the two that make the trade in `configschema`'s docstring defensible:

* the **keyword guard** — the-loop's schemas may not grow a construct the validator does
  not implement without this failing;
* the **differential test** — over a corpus of valid and invalid configs, this validator
  and the real ``jsonschema`` (a dev dependency, so CI has it) must agree on which
  documents are valid.
"""

import warnings
from pathlib import Path

import pytest
import yaml

from the_loop import configschema

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = REPO_ROOT / "skills" / "the-loop" / "templates" / "cli-config.yaml"

jsonschema = pytest.importorskip("jsonschema")


def _template() -> dict:
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


#: Documents that must validate, and documents that must not, with what is wrong.
VALID = [
    {},
    {"version": "0.4.0"},
    {"routing": {"enabled": True, "authorizedUsers": ["octocat"]}},
    {"polling": {"intervalSeconds": 30, "sources": []}},
    {"routing": {"tmux": {"sessionPerPr": True}}},
    {"routing": {"tmux": {"sessionPerPr": "always"}}},
    {
        "service": {
            "port": 8080,
            "cors": {"allowOrigins": ["*"], "allowCredentials": False},
        }
    },
    {
        "collaborators": [
            {"handle": "@octocat", "kind": "individual", "roles": ["engineer"]}
        ]
    },
]
INVALID = [
    ({"nope": 1}, "unknown top-level key"),
    ({"routing": {"nope": 1}}, "unknown nested key"),
    ({"polling": {"intervalSeconds": "soon"}}, "wrong type"),
    ({"routing": {"enabled": "yes"}}, "string where a boolean belongs"),
    ({"routing": {"defaultHarness": "emacs"}}, "outside the enum"),
    ({"webhooks": {"ghWebhook": {"port": 0}}}, "below the minimum"),
    ({"webhooks": {"ghWebhook": {"port": 99999}}}, "above the maximum"),
    ({"routing": {"authorizedUsers": "octocat"}}, "string where an array belongs"),
    (
        {"routing": {"tmux": {"sessionPerPr": "sometimes"}}},
        "a session-per-pr mode that does not exist",
    ),
    (
        {"routing": {"tmux": {"sessionPerPr": 1}}},
        "a number where a mode or a boolean belongs",
    ),
    (
        {"collaborators": [{"handle": "@octocat", "kind": "nonsense"}]},
        "bad enum in a $ref'd shape",
    ),
]


def test_the_packaged_schema_loads_with_no_repository_checkout():
    """
    Feature: the schema resolves from the installed package
      Scenario: a bare pip install serves and validates
        Given no plugin checkout and no network
        When the CLI config schema is loaded
        Then it is a complete object schema with its $refs already resolved

    Requirement: docs/specs/issue-222/requirements.md R1.3, NFR4
    """
    schema = configschema.load_schema("cli-config")
    assert schema["type"] == "object"
    assert "routing" in schema["properties"]
    collaborator = schema["properties"]["collaborators"]["items"]
    assert (
        "handle" in collaborator["properties"]
    )  # the $ref was resolved, not passed on
    assert "$ref" not in yaml.safe_dump(schema)


def test_an_unknown_schema_name_is_a_packaging_error():
    with pytest.raises(configschema.SchemaNotFound):
        configschema.load_schema("not-a-schema")


def test_the_shipped_template_validates():
    assert configschema.validate(_template()) == []


@pytest.mark.parametrize("document", VALID, ids=lambda d: str(sorted(d))[:40])
def test_valid_documents_report_nothing(document):
    assert configschema.validate(document) == []


@pytest.mark.parametrize("document,why", INVALID, ids=[why for _, why in INVALID])
def test_invalid_documents_are_named_by_key_path(document, why):
    """
    Feature: a refused save says which key is wrong
      Scenario: a patch would make the config invalid
        Given a document violating the schema
        When it is validated
        Then the violation is reported with its dotted key path

    Requirement: docs/specs/issue-222/requirements.md R3.1
    """
    errors = configschema.validate(document)
    assert errors, why
    assert all(":" in error for error in errors)


@pytest.mark.parametrize(
    "accepted", [True, False, "never", "cross-repository", "always"]
)
def test_session_per_pr_accepts_both_booleans_and_all_three_modes(accepted):
    """issue-258 R3.3 — the key grew names without dropping the booleans, so a
    config file written before this change still validates."""
    assert (
        configschema.validate({"routing": {"tmux": {"sessionPerPr": accepted}}}) == []
    )


def test_the_schemas_use_no_keyword_the_validator_ignores():
    """
    Feature: the validator keeps up with the schema
      Scenario: a schema grows a construct the validator does not implement
        Given the-loop's two packaged schemas
        When every keyword they use is collected
        Then each one is declared in configschema.SUPPORTED

    Requirement: docs/specs/issue-222/design.md §Why not depend on jsonschema
    """
    used = set()
    for name in ("cli-config", "collaborators"):
        _keywords(_raw(name), used)
    unsupported = used - configschema.SUPPORTED
    assert not unsupported, (
        f"the schemas use {sorted(unsupported)}, which configschema does not know. "
        "Implement it in validate() and add it to CONSTRAINING, or — if it only "
        "documents the shape — add it to SUPPORTED."
    )


def test_this_validator_agrees_with_jsonschema():
    """
    Feature: the hand-written validator is not a comforting stub
      Scenario: the same documents are judged by both implementations
        Given a corpus of valid and invalid configs and the shipped template
        When each is validated by configschema and by jsonschema
        Then the two agree on every verdict

    Requirement: docs/specs/issue-222/design.md §Why not depend on jsonschema
    """
    schema = _raw("cli-config")
    store = {_raw("collaborators")["$id"]: _raw("collaborators")}
    with warnings.catch_warnings():  # RefResolver is deprecated; it is still the API
        warnings.simplefilter(
            "ignore", DeprecationWarning
        )  # scripts/validate_config.py uses
        resolver = jsonschema.RefResolver(  # the same shim, for the same reason
            base_uri=schema.get("$id", ""), referrer=schema, store=store
        )
    corpus = [(document, True) for document in [*VALID, _template()]]
    corpus += [(document, False) for document, _ in INVALID]
    for document, expected in corpus:
        ours = not configschema.validate(document)
        try:
            jsonschema.validate(document, schema, resolver=resolver)
            theirs = True
        except jsonschema.ValidationError:
            theirs = False
        assert ours == theirs == expected, document


def _raw(name: str) -> dict:
    import json

    return json.loads(configschema.schema_path(name).read_text(encoding="utf-8"))


def _keywords(node, out: set, in_names: bool = False) -> None:
    """Collect schema keywords, skipping the levels whose keys are *names*."""
    if isinstance(node, list):
        for entry in node:
            _keywords(entry, out)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if in_names:
            _keywords(value, out)
            continue
        out.add(key)
        _keywords(value, out, in_names=key in ("properties", "$defs"))
