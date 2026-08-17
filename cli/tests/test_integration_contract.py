"""One suite, every provider — so `api` and `cli` are verified interchangeable.

The point of a declared capability set is that a hook can swap transports
without changing behaviour. That is a claim, so it gets a test (R6.10).
"""

from __future__ import annotations

import pytest

from the_loop.graph.integrations.base import OperationUnsupported
from the_loop.graph.integrations.github import GitHubApi, GitHubCli

GITHUB_PROVIDERS = [GitHubApi(["GH_TOKEN"]), GitHubCli("gh")]
ALL_PROVIDERS = list(GITHUB_PROVIDERS)


@pytest.mark.parametrize(
    "provider", ALL_PROVIDERS, ids=lambda p: f"{p.name}/{p.transport}"
)
def test_every_provider_declares_a_name_transport_and_operations(provider):
    assert provider.name and provider.transport
    assert isinstance(provider.operations, frozenset) and provider.operations


@pytest.mark.parametrize(
    "provider", ALL_PROVIDERS, ids=lambda p: f"{p.name}/{p.transport}"
)
def test_every_provider_refuses_an_operation_it_does_not_declare(provider):
    with pytest.raises(OperationUnsupported):
        provider.call("not-a-real-operation")


def test_the_github_transports_are_interchangeable():
    """Identical capability sets — a hook cannot tell them apart."""
    api, cli = GITHUB_PROVIDERS
    assert api.operations == cli.operations
    assert api.name == cli.name
    assert api.transport != cli.transport
