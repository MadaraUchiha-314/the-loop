"""The OpenAPI contract in docs/api-specs/openapi/ is the source of truth (issue-161).

`docs/api-specs/openapi/the-loop.v1.yaml` is the authored contract (R3.2); the app must
serve exactly it. Comparing paths, methods and operationIds catches surface
drift (an added/renamed/removed route) without failing on cosmetic schema-title
churn between FastAPI versions.

Since issue-212 there is a second consumer of the same surface — the SDK hands the router
to somebody else's application — so a third assertion checks the *router's* operations
match too. They are the same object, so the assertion is cheap; what it buys is that the
day someone reintroduces a route by decorating the app instead of the router, the build
says so.
"""

import pathlib

import yaml
from fastapi.routing import APIRoute

from the_loop.api.app import create_app
from the_loop.api.routes import build_router
from the_loop.cli_config import ConfigHolder


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


def test_the_router_carries_exactly_the_apps_operations(tmp_path):
    """
    Feature: one surface, two consumers
      Scenario: the embeddable router and the standalone app serve the same operations
        Given the router the SDK mounts into a host application
        When its operation ids are compared to the standalone app's
        Then they are identical

    Requirement: docs/specs/issue-212/requirements.md R2.1, R2.7
    """
    router = build_router(ConfigHolder({}, tmp_path / "cli-config.yaml"))
    from_router = {
        route.operation_id for route in router.routes if isinstance(route, APIRoute)
    }
    served = create_app({}).openapi()
    from_app = {
        op.get("operationId")
        for methods in served["paths"].values()
        for op in methods.values()
    }
    assert from_router == from_app
