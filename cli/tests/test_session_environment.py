"""What a spawned session is handed, and what it must not hold (issue-482, issue-485).

Spec: docs/specs/issue-482/design.md § envstate.
"""

import logging

import pytest

from the_loop import envstate
from the_loop.envstate import SessionEnvironment


def _config(tmp_path, text=None, **env):
    if text is not None:
        (tmp_path / ".env").write_text(text)
        env.setdefault("file", ".env")
    return {"env": env} if env else {}


def test_credential_names_walk_every_token_and_secret_key_at_any_depth():
    config = {
        "integrations": {
            "github": {"api": {"tokenEnv": "THE_LOOP_GH_TOKEN"}},
            "jira": {
                "api": {"tokenEnv": ["JIRA_API_TOKEN", "JIRA_PAT"], "emailEnv": "E"},
                "webhook": {"secretEnv": "THE_LOOP_JIRA_WEBHOOK_SECRET"},
            },
        },
        "channels": {"slack": {"botTokenEnv": "BOT", "appTokenEnv": "APP"}},
        "hooks": [{"name": "h", "tokenEnv": "HOOK_TOKEN"}],
        "webhooks": {"ghWebhook": {"secretEnv": "WH"}},
    }
    names = envstate.credential_names(config)
    for name in (
        "THE_LOOP_GH_TOKEN",
        "JIRA_API_TOKEN",
        "JIRA_PAT",
        "THE_LOOP_JIRA_WEBHOOK_SECRET",
        "BOT",
        "APP",
        "HOOK_TOKEN",
        "WH",
    ):
        assert name in names
    # The email is an identity, not a credential: not refused, not forced out.
    assert "E" not in names


def test_credential_names_include_the_defaults_a_config_need_not_name():
    names = envstate.credential_names({})
    assert {"GH_TOKEN", "GITHUB_TOKEN", "THE_LOOP_SLACK_BOT_TOKEN"} <= names
    assert {"THE_LOOP_SLACK_APP_TOKEN", "THE_LOOP_GH_WEBHOOK_SECRET"} <= names


def test_abuse_482_a4_a_credential_in_the_passthrough_is_refused(caplog):
    config = {
        "env": {"sessionPassthrough": ["HTTPS_PROXY", "GH_TOKEN", "bad name"]},
    }
    with caplog.at_level(logging.WARNING, logger="the-loop.envstate"):
        names = envstate.passthrough_names(config)
    assert names == ("HTTPS_PROXY",)
    assert "GH_TOKEN" in caplog.text


def _boundary(config, tmp_path) -> SessionEnvironment:
    env = envstate.session_environment(config, tmp_path / "c.yaml")
    assert env is not None
    return env


def test_nothing_configured_is_none(tmp_path):
    assert envstate.session_environment({}, tmp_path / "c.yaml") is None


def test_by_default_nothing_from_the_env_file_is_forwarded(tmp_path):
    config = _config(tmp_path, "GH_TOKEN=gho_secret\nLANG=C\n")
    env = _boundary(config, tmp_path)
    assert env.forward == {}
    assert {"GH_TOKEN", "LANG"} <= set(env.remove)


def test_a_passthrough_name_comes_from_the_file_first_then_the_process(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("HTTPS_PROXY", "http://proc")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.delenv("MISSING", raising=False)
    config = _config(
        tmp_path,
        "HTTPS_PROXY=http://file\nGH_TOKEN=gho_secret\n",
        sessionPassthrough=["HTTPS_PROXY", "NO_PROXY", "MISSING"],
    )
    env = _boundary(config, tmp_path)
    assert env.forward == {"HTTPS_PROXY": "http://file", "NO_PROXY": "localhost"}
    assert "GH_TOKEN" in env.remove
    assert "HTTPS_PROXY" not in env.remove


def test_the_loops_own_names_are_never_removed(tmp_path):
    config = _config(tmp_path, "THE_LOOP_INSTANCE=x\nTHE_LOOP_CLI_CONFIG=y\n")
    env = _boundary(config, tmp_path)
    assert "THE_LOOP_INSTANCE" not in env.remove
    assert "THE_LOOP_CLI_CONFIG" not in env.remove


def test_an_unreadable_env_file_still_removes_the_credentials(tmp_path):
    config = {"env": {"file": "missing.env"}}
    env = _boundary(config, tmp_path)
    assert "GH_TOKEN" in env.remove


def test_spawn_environment_with_no_config_still_strips_credentials(monkeypatch):
    env = envstate.spawn_environment(lambda: {})
    assert env.forward == {}
    assert "GH_TOKEN" in env.remove


def test_spawn_environment_never_raises(monkeypatch):
    def boom():
        raise RuntimeError("config gone")

    env = envstate.spawn_environment(boom)
    assert env.forward == {}
    assert "GH_TOKEN" in env.remove


def test_compare_reports_a_differing_forward_and_a_present_removed_name():
    env = SessionEnvironment(forward={"LANG": "C"}, remove=("GH_TOKEN", "JIRA"))
    assert envstate.compare(env, {"LANG": "C"}) == ()
    assert envstate.compare(env, {"LANG": "fr"}) == ("LANG",)
    assert envstate.compare(env, {"LANG": "C", "GH_TOKEN": "x"}) == ("GH_TOKEN",)
    # A blanked credential is still held.
    assert envstate.compare(env, {"LANG": "C", "JIRA": ""}) == ("JIRA",)


def test_compare_still_takes_a_plain_mapping():
    assert envstate.compare({"A": "1"}, {"A": "2"}) == ("A",)


@pytest.mark.parametrize("value", ["", None, 3])
def test_a_malformed_passthrough_is_empty(value):
    assert envstate.passthrough_names({"env": {"sessionPassthrough": value}}) == ()


def test_a_credential_key_holding_something_that_is_not_a_name_is_ignored():
    """It could never be a variable — and reaching `env -u` it would fail the spawn."""
    names = envstate.credential_names({"x": {"tokenEnv": ["A=B", "-i", "GOOD"]}})
    assert "GOOD" in names
    assert "A=B" not in names and "-i" not in names
