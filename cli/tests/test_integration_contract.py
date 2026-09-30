"""One suite, every provider — the declared capability set is a contract.

Until issue-442 two GitHub transports (`api`, `cli`) were verified
interchangeable here (R6.10). There is one provider now; the contract it keeps
is the same one: a name, a transport, a declared operation set, and a refusal
for anything outside it.
"""

from __future__ import annotations

import pytest
from ghfakes import FakeGitHubClient

from the_loop.graph.integrations.base import OperationUnsupported
from the_loop.graph.integrations.github import OPERATIONS, GitHubProvider

ALL_PROVIDERS = [GitHubProvider(client=FakeGitHubClient())]


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


def test_the_github_provider_declares_the_operations_the_hooks_use():
    """The set the shipped graph hooks call — identical before and after issue-442."""
    assert GitHubProvider(client=FakeGitHubClient()).operations == OPERATIONS
    assert {"add-comment", "set-labels", "remove-label", "get-labels"} <= OPERATIONS
