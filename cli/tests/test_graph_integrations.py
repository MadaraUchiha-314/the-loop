"""Transport resolution and the provider contract (issue-109, R6)."""

from __future__ import annotations

import pytest

from the_loop.graph.integrations import (
    OperationUnsupported,
    TransportUnavailable,
    resolve,
)
from the_loop.graph.integrations.github import GitHubApi, GitHubCli, _split_ref


def test_auto_prefers_the_api_transport_when_a_token_is_present(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    provider = resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    assert provider.transport == "api"


def test_auto_falls_back_to_the_cli_when_the_binary_exists(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/gh")
    provider = resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    assert provider.transport == "cli"


def test_auto_with_nothing_available_names_both_remedies(monkeypatch):
    """R6.3 — fail closed, and tell the operator every way to fix it."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: None)
    with pytest.raises(TransportUnavailable) as exc:
        resolve("github", {"integrations": {"github": {"transport": "auto"}}})
    message = str(exc.value)
    assert "GH_TOKEN" in message and "gh" in message


def test_an_explicit_transport_is_honoured_verbatim(monkeypatch):
    """R6.4 — a configured choice never silently degrades to another."""
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setattr("shutil.which", lambda b: "/usr/bin/gh")
    provider = resolve("github", {"integrations": {"github": {"transport": "api"}}})
    assert provider.transport == "api", "explicit api must not fall back to cli"


def test_an_unknown_transport_is_refused():
    with pytest.raises(TransportUnavailable, match="unknown transport"):
        resolve("github", {"integrations": {"github": {"transport": "carrier-pigeon"}}})


def test_an_unknown_target_is_refused():
    with pytest.raises(TransportUnavailable, match="no integration registered"):
        resolve("mastodon", {})


def test_both_github_providers_declare_the_same_operations():
    """The contract: api and cli are interchangeable to a hook (R6.10)."""
    assert GitHubApi(["GH_TOKEN"]).operations == GitHubCli().operations


@pytest.mark.parametrize("provider", [GitHubApi(["GH_TOKEN"]), GitHubCli()])
def test_an_unsupported_operation_is_refused(provider):
    with pytest.raises(OperationUnsupported):
        provider.call("launch-rocket", ref="github:o/r#1")


def test_work_item_refs_parse():
    assert _split_ref("github:owner/repo#42") == ("owner", "repo", "42")
    assert _split_ref("owner/repo#7") == ("owner", "repo", "7")


def test_a_malformed_ref_is_refused():
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError, match="malformed"):
        _split_ref("nonsense")


def test_slack_is_a_named_refusal_pointing_at_channels():
    """issue-245 (PR #267 review): Slack converged on the channels layer. An
    embedder still resolving the old integration learns the replacement."""
    with pytest.raises(TransportUnavailable, match="channels.slack"):
        resolve("slack", {"integrations": {"slack": {"transport": "sdk"}}})


# -- the host (issue-311, R4) ----------------------------------------------------

import json  # noqa: E402

from the_loop.graph.integrations.github import (  # noqa: E402
    _linked_pull_refs,
    _ref_parts,
)

GHE = "ghe.corp.example"
GHE_REF = f"github:{GHE}/octo/repo#42"


def test_ref_parts_reads_a_hosted_ref():
    assert _ref_parts(GHE_REF) == (GHE, "octo", "repo", "42")
    assert _ref_parts("github:octo/repo#42") == ("", "octo", "repo", "42")
    assert _split_ref(GHE_REF) == ("octo", "repo", "42")


def test_a_ref_with_a_bad_host_is_malformed():
    from the_loop.graph.integrations.base import IntegrationError

    with pytest.raises(IntegrationError, match="malformed"):
        _split_ref("github:ghe/octo/repo#42")


class _Runs:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        return "{}"


def test_the_cli_transport_names_the_host_on_every_operation(monkeypatch):
    runs = _Runs()
    provider = GitHubCli()
    monkeypatch.setattr(provider, "_run", runs)
    provider.call("add-comment", ref=GHE_REF, body="hi")
    provider.call("set-labels", ref=GHE_REF, labels=["a"])
    provider.call("get-labels", ref=GHE_REF)
    provider.call("get-thread", ref=GHE_REF)
    provider.call("linked-pulls", ref=GHE_REF)
    provider.call("list-comments", ref=GHE_REF)
    for argv in runs.calls:
        if argv[0] == "api":
            assert argv[1:3] == ["--hostname", GHE], argv
        else:
            assert argv[argv.index("--repo") + 1] == f"{GHE}/octo/repo", argv


def test_the_cli_transport_is_unchanged_for_github_com(monkeypatch):
    runs = _Runs()
    provider = GitHubCli()
    monkeypatch.setattr(provider, "_run", runs)
    provider.call("add-comment", ref="github:octo/repo#42", body="hi")
    provider.call("get-thread", ref="github:octo/repo#42")
    assert all("--hostname" not in argv for argv in runs.calls)
    assert runs.calls[0][runs.calls[0].index("--repo") + 1] == "octo/repo"


def test_the_api_transport_derives_the_enterprise_base(monkeypatch):
    seen = []

    def fake_open(req, timeout=30):
        seen.append(req.full_url)

        class _Resp:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b"{}"

        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    monkeypatch.setenv("GH_TOKEN", "x")
    GitHubApi(["GH_TOKEN"]).call("get-thread", ref=GHE_REF)
    GitHubApi(["GH_TOKEN"]).call("get-thread", ref="github:octo/repo#42")
    GitHubApi(["GH_TOKEN"], "https://explicit.example/api/v3").call(
        "get-thread", ref=GHE_REF
    )
    assert seen == [
        f"https://{GHE}/api/v3/repos/octo/repo/issues/42",
        "https://api.github.com/repos/octo/repo/issues/42",
        "https://explicit.example/api/v3/repos/octo/repo/issues/42",
    ]


def test_linked_pulls_carry_the_host_they_were_asked_on():
    data = {
        "data": {
            "repository": {
                "issue": {
                    "closedByPullRequestsReferences": {
                        "nodes": [
                            {"number": 3, "repository": {"nameWithOwner": "octo/repo"}}
                        ]
                    }
                }
            }
        }
    }
    assert _linked_pull_refs(json.loads(json.dumps(data)), GHE) == [
        f"github:{GHE}/octo/repo#3"
    ]
    assert _linked_pull_refs(data, "") == ["github:octo/repo#3"]
