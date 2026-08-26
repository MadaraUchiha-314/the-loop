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
    {"channels": {"slack": {"enabled": True, "authorizedUsers": ["U123"]}}},
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
        {"collaborators": [{"handle": "@octocat", "roles": ["engineer"]}]},
        "a block retired in issue-304 — nothing ever read it",
    ),
    (
        {"notifications": {"enabled": True, "events": {"session-died": ["engineer"]}}},
        "the other block retired in issue-304",
    ),
]

#: The collaborators file is validated against its own schema, so its corpus is its own.
COLLABORATORS_VALID = [
    {"collaborators": []},
    {
        "version": "0.2.0",
        "collaborators": [
            {"handle": "@octocat", "kind": "individual", "roles": ["engineer"]}
        ],
    },
]
COLLABORATORS_INVALID = [
    ({"collaborators": [{"handle": "@octocat", "kind": "nonsense"}]}, "bad enum"),
    (
        {
            "collaborators": [
                {
                    "handle": "@octocat",
                    "roles": ["engineer"],
                    "notifications": {
                        "enabled": True,
                        "channels": [
                            {"type": "slack", "config": {"channel-list": ["#x"]}}
                        ],
                    },
                }
            ]
        },
        "the per-collaborator notification shape retired in issue-304",
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
    assert "$ref" not in yaml.safe_dump(schema)
    # issue-304 retired the CLI config's one cross-schema $ref, so the resolution the
    # docstring promises is exercised on the schema that still has refs to resolve.
    collaborator = configschema.load_schema("collaborators")["properties"][
        "collaborators"
    ]["items"]
    assert "handle" in collaborator["properties"]  # resolved, not passed on


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
    collaborators = _raw("collaborators")
    corpus = [(document, schema, True) for document in [*VALID, _template()]]
    corpus += [(document, schema, False) for document, _ in INVALID]
    # The collaborators schema carries every $ref left in the tree since issue-304
    # retired the CLI config's one cross-schema reference, so it is judged here too.
    corpus += [(document, collaborators, True) for document in COLLABORATORS_VALID]
    corpus += [
        (document, collaborators, False) for document, _ in COLLABORATORS_INVALID
    ]
    for document, against, expected in corpus:
        ours = not configschema.validate(
            document, configschema.load_schema(_name_of(against))
        )
        try:
            jsonschema.validate(document, against, resolver=resolver)
            theirs = True
        except jsonschema.ValidationError:
            theirs = False
        assert ours == theirs == expected, document


def _name_of(schema: dict) -> str:
    return (
        "collaborators"
        if "collaborators.schema.json" in schema["$id"]
        else "cli-config"
    )


@pytest.mark.parametrize(
    "document", COLLABORATORS_VALID, ids=lambda d: str(sorted(d))[:40]
)
def test_a_collaborator_file_of_people_and_roles_validates(document):
    """issue-304 R1.3 — handle/kind/roles are untouched: the skill still resolves a
    phase's reviewers and approvers from them."""
    assert (
        configschema.validate(document, configschema.load_schema("collaborators")) == []
    )


@pytest.mark.parametrize(
    "document,why", COLLABORATORS_INVALID, ids=[why for _, why in COLLABORATORS_INVALID]
)
def test_a_collaborator_file_is_refused_by_key_path(document, why):
    errors = configschema.validate(document, configschema.load_schema("collaborators"))
    assert errors, why


def test_a_retired_collaborator_notification_block_names_its_replacement():
    """
    Feature: a removed key says where the thing it configured went
      Scenario: a collaborators.yaml still declares per-person notification channels
        Given a collaborator carrying a `notifications` block
        When the file is validated
        Then the refusal names the key path, `channels.slack`, and `the-loop migrate-config`

    Requirement: docs/specs/issue-304/requirements.md R1.2
    """
    document = COLLABORATORS_INVALID[1][0]
    errors = configschema.validate(document, configschema.load_schema("collaborators"))
    assert len(errors) == 1
    (error,) = errors
    assert error.startswith("collaborators[0].notifications: unknown key")
    assert "channels.slack" in error
    assert "the-loop migrate-config" in error


@pytest.mark.parametrize("key", ["collaborators", "notifications"])
def test_a_retired_cli_config_block_names_its_replacement(key):
    """
    Feature: a removed key says where the thing it configured went
      Scenario: a cli-config.yaml still declares a block nothing ever read
        Given a config carrying `collaborators` or `notifications`
        When it is validated
        Then the refusal names the key, `channels.slack`, and `the-loop migrate-config`

    Requirement: docs/specs/issue-304/requirements.md R2.1, R2.2
    """
    errors = configschema.validate({key: [] if key == "collaborators" else {}})
    assert len(errors) == 1
    (error,) = errors
    assert error.startswith(f"{key}: unknown key")
    assert "channels.slack" in error
    assert "the-loop migrate-config" in error


def test_an_ordinary_typo_gets_no_invented_guidance():
    """RETIRED answers for keys the-loop actually removed; a typo is just unknown."""
    assert configschema.validate({"nope": 1}) == ["nope: unknown key"]


def test_both_identity_allow_lists_survive_the_removal():
    """
    Feature: identity is declared in exactly two places
      Scenario: the retired notification blocks are gone
        Given a config naming a GitHub login and a Slack member id
        When it is validated
        Then both allow-lists are accepted, and both are still schema leaves

    Requirement: docs/specs/issue-304/requirements.md R2.3, R2.4 (threat model T1)
    """
    schema = configschema.load_schema("cli-config")
    assert schema["properties"]["routing"]["properties"]["authorizedUsers"]
    assert schema["properties"]["channels"]["properties"]["slack"]["properties"][
        "authorizedUsers"
    ]
    assert (
        configschema.validate(
            {
                "routing": {"authorizedUsers": ["octocat"]},
                "channels": {"slack": {"authorizedUsers": ["U024BE7LH"]}},
            }
        )
        == []
    )


def test_every_retired_key_is_absent_from_the_schema_it_names():
    """A row in RETIRED for a key the schema still accepts would never fire."""
    cli = configschema.load_schema("cli-config")["properties"]
    collaborator = configschema.load_schema("collaborators")["properties"][
        "collaborators"
    ]["items"]["properties"]
    assert "collaborators" not in cli
    assert "notifications" not in cli
    assert "notifications" not in collaborator
    assert set(configschema.RETIRED) == {
        "collaborators",
        "notifications",
        "collaborators[].notifications",
    }


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
