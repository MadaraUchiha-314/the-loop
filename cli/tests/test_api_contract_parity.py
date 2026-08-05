"""The OpenAPI contract in docs/api-specs/openapi/ is the source of truth (issue-161).

`docs/api-specs/openapi/the-loop.v1.yaml` is the authored contract (R3.2); the app must
serve exactly it. Comparing paths, methods and operationIds catches surface
drift (an added/renamed/removed route) without failing on cosmetic schema-title
churn between FastAPI versions.
"""

import pathlib

import yaml

from the_loop.api.app import create_app


def _surface(schema):
    return {
        (path, method, op.get("operationId"))
        for path, methods in schema["paths"].items()
        for method, op in methods.items()
    }


def test_served_schema_matches_the_authored_contract():
    """
    Feature: contract-first control-plane API
      Scenario: the served schema drifts from the authored contract
        Given the checked-in docs/api-specs/openapi/the-loop.v1.yaml
        When the app's generated OpenAPI schema is compared to it
        Then every path, method and operationId matches exactly

    Requirement: docs/specs/issue-161/requirements.md R3.2
    """
    contract_path = (
        pathlib.Path(__file__).resolve().parents[2]
        / "docs"
        / "api-specs"
        / "openapi"
        / "the-loop.v1.yaml"
    )
    contract = yaml.safe_load(contract_path.read_text())
    served = create_app({}).openapi()
    assert _surface(served) == _surface(contract)
