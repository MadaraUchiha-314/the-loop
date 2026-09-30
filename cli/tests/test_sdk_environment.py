"""Unit tests for the environment contract (issue-212, T1/T10, R5)."""

import pytest

from the_loop.sdk import REQUIREMENTS, check_environment
from the_loop.sdk import environment as env_mod


ROUTING_ON = {"routing": {"enabled": True}}


def _by_binary(report, binary):
    return next(check for check in report["checks"] if check["binary"] == binary)


def test_a_config_that_routes_nothing_requires_no_binary():
    """R5.2: `required` is answered for *this* configuration, not in the abstract.

    `routing.enabled` defaults to false — verify-and-log only — so a service that merely
    reads work items and events needs no harness, no tmux and no git.
    """
    report = check_environment({})
    assert [check["binary"] for check in report["checks"] if check["required"]] == []
    assert report["ok"] is True


def test_routing_requires_the_harness_tmux_and_git():
    """R5.1: turning routing on is what makes the three binaries load-bearing.

    `gh` left the table with issue-442: GitHub is a token now, not a binary.
    """
    report = check_environment(ROUTING_ON)
    required = {check["binary"] for check in report["checks"] if check["required"]}
    assert required == {"claude", "tmux", "git"}


def test_the_harness_binary_follows_defaultharness():
    """Only the configured harness is required; the other is reported as optional."""
    report = check_environment(
        {"routing": {"enabled": True, "defaultHarness": "cursor"}}
    )
    assert _by_binary(report, "cursor-agent")["required"] is True
    assert _by_binary(report, "claude")["required"] is False


def test_the_web_terminal_is_what_requires_ttyd():
    assert _by_binary(check_environment(ROUTING_ON), "ttyd")["required"] is False
    report = check_environment({"routing": {"webTerminal": {"enabled": True}}})
    assert _by_binary(report, "ttyd")["required"] is True


def test_the_operators_git_override_is_honoured():
    """R5.4: resolve by the name the runtime uses, not by the default."""
    config = {"routing": {"workspace": {"gitBinary": "/opt/git/bin/git"}}}
    report = check_environment(config)
    assert _by_binary(report, "/opt/git/bin/git")["configKey"] == (
        "routing.workspace.gitBinary"
    )


def test_github_is_a_credential_not_a_binary(monkeypatch):
    """issue-442: no requirement row names `gh`; the token is checked elsewhere."""
    assert all(req.default_binary != "gh" for req in REQUIREMENTS)
    from the_loop.poller import check_github_credentials

    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    (message,) = check_github_credentials()
    assert "GH_TOKEN" in message
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert check_github_credentials() == []


def test_a_missing_required_binary_makes_the_report_not_ok(monkeypatch):
    """R5.3: not-ok names the gap; an absent *optional* binary keeps the report ok."""
    monkeypatch.setattr(env_mod.shutil, "which", lambda binary: None)
    assert check_environment(ROUTING_ON)["ok"] is False
    assert check_environment({})["ok"] is True


def test_a_present_binary_reports_its_resolved_path(monkeypatch):
    monkeypatch.setattr(env_mod.shutil, "which", lambda binary: f"/opt/bin/{binary}")
    report = check_environment(ROUTING_ON)
    assert report["ok"] is True
    assert _by_binary(report, "tmux") == {
        "binary": "tmux",
        "present": True,
        "path": "/opt/bin/tmux",
        "required": True,
        "capability": _by_binary(report, "tmux")["capability"],
        "configKey": "",
    }


def test_the_preflight_never_executes_what_it_finds(monkeypatch):
    """Abuse case 5: a preflight that runs `--version` on a hostile PATH is the exploit.

    Fails the test if anything in the module reaches for a subprocess primitive.
    """
    import subprocess

    def forbidden(
        *args, **kwargs
    ):  # pragma: no cover — the assertion is that it is not
        raise AssertionError("check_environment executed a binary")

    for name in ("run", "Popen", "call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr("os.system", forbidden)
    check_environment(ROUTING_ON)


@pytest.mark.parametrize("requirement", REQUIREMENTS, ids=lambda r: r.default_binary)
def test_every_requirement_states_a_capability(requirement):
    """A binary named with no clause about what breaks without it is not a contract."""
    assert requirement.capability.strip()
    assert callable(requirement.required)
