"""Unit tests for `envstate` — the declared environment, and what a process holds.

issue-410: a session's environment is frozen at spawn, so a credential rotation
leaves the service on the new value and every running session on the old one.
This module is the knowledge that makes the drift sayable; these tests pin the
three properties it must have — the file is re-read rather than remembered, a
value is never spoken, and reading another process never raises.

Spec: docs/specs/issue-410/design.md · testing plan row T1.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from the_loop import envstate

TOKEN = "xoxb-the-new-one-0123456789"
RETIRED = "xoxb-the-retired-one-987654"


@pytest.fixture
def sleeper():
    """A child process started with the RETIRED credential in its environment.

    A real process because that is the only way to pin the property this module
    depends on: `/proc/<pid>/environ` reports what a process was **started**
    with, not what it has `setenv`-ed since — which is exactly the question a
    frozen session poses.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        env={**os.environ, "THE_LOOP_TEST_MARKER": RETIRED},
    )
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=10)


def _config(tmp_path: Path, body: str) -> tuple[dict, Path]:
    """A CLI config naming an env file beside it, and the config's own path."""
    env_file = tmp_path / "the-loop.env"
    env_file.write_text(body, encoding="utf-8")
    return ({"env": {"file": "the-loop.env"}}, tmp_path / "cli-config.yaml")


class TestDeclared:
    def test_reads_the_file_now_not_what_this_process_loaded(
        self, tmp_path, monkeypatch
    ):
        """
        Feature: a rotation takes effect
          Scenario: the env file is rewritten while the process holds the old value
            Given a process whose environment carries the retired credential
            When the env file is rewritten with the new one
            Then `declared` reports the new one

        Requirement: docs/specs/issue-410/requirements.md R1.1
        """
        config, path = _config(tmp_path, f"SLACK_BOT_TOKEN={RETIRED}\n")
        monkeypatch.setenv("SLACK_BOT_TOKEN", RETIRED)
        (tmp_path / "the-loop.env").write_text(
            f"SLACK_BOT_TOKEN={TOKEN}\n", encoding="utf-8"
        )

        result = envstate.declared(config, path)
        assert result is not None
        values, invalid = result

        assert values == {"SLACK_BOT_TOKEN": TOKEN}
        assert invalid == ()
        # The point of the whole module: os.environ is not consulted.
        assert os.environ["SLACK_BOT_TOKEN"] == RETIRED

    def test_a_config_naming_no_env_file_is_none_not_empty(self, tmp_path):
        """
        Feature: nothing to roll onto
          Scenario: the config names no env file
            Given a CLI config with no `env.file`
            When the declared environment is read
            Then the answer is None — distinct from a file that declares nothing

        Requirement: R1.7
        """
        assert envstate.declared({}, tmp_path / "cli-config.yaml") is None
        assert envstate.declared({"env": {}}, tmp_path / "cli-config.yaml") is None

    def test_a_file_that_declares_nothing_is_an_empty_mapping(self, tmp_path):
        config, path = _config(tmp_path, "# only a comment\n")
        assert envstate.declared(config, path) == ({}, ())

    def test_a_malformed_line_is_reported_by_number_never_by_text(
        self, tmp_path, caplog
    ):
        """A malformed line's *text* may itself be a secret (envfile's rule)."""
        config, path = _config(tmp_path, f"GOOD={TOKEN}\nnot an assignment {RETIRED}\n")
        with caplog.at_level("WARNING"):
            result = envstate.declared(config, path)
        assert result is not None
        values, invalid = result
        assert values == {"GOOD": TOKEN}
        assert invalid == (2,)
        assert RETIRED not in caplog.text

    def test_an_unreadable_file_declares_nothing_and_does_not_raise(self, tmp_path):
        config = {"env": {"file": "absent.env"}}
        assert envstate.declared(config, tmp_path / "cli-config.yaml") == ({}, ())


class TestFingerprint:
    def test_the_same_value_fingerprints_alike_and_a_different_one_does_not(self):
        """
        Feature: saying "these processes differ" without saying either value
          Scenario: two processes hold different tokens
            Given the retired credential and the new one
            When each is fingerprinted
            Then the fingerprints differ, and each is stable across calls

        Requirement: R5.2
        """
        assert envstate.fingerprint(TOKEN) == envstate.fingerprint(TOKEN)
        assert envstate.fingerprint(TOKEN) != envstate.fingerprint(RETIRED)

    def test_nothing_of_the_value_survives(self):
        printed = envstate.fingerprint(TOKEN)
        assert len(printed) == envstate.FINGERPRINT_LENGTH
        assert TOKEN not in printed
        # Not even a prefix: four characters of a token is four characters leaked.
        assert not any(TOKEN[:n] in printed for n in range(4, len(TOKEN)))


class TestCompare:
    def test_equal_mappings_differ_in_nothing(self):
        declared = {"A": "1", "B": "2"}
        assert envstate.compare(declared, {"A": "1", "B": "2", "PATH": "/bin"}) == ()

    def test_names_only_what_differs_in_name_order(self):
        """
        Feature: naming the drift
          Scenario: one declared variable holds a retired value and one is missing
            Given a process carrying the retired token and no webhook secret
            When it is compared with the file
            Then exactly those two names come back, sorted

        Requirement: R2.1
        """
        declared = {"SLACK_BOT_TOKEN": TOKEN, "GH_SECRET": "s", "SAME": "x"}
        actual = {"SLACK_BOT_TOKEN": RETIRED, "SAME": "x"}
        assert envstate.compare(declared, actual) == ("GH_SECRET", "SLACK_BOT_TOKEN")

    def test_a_name_the_file_does_not_declare_is_not_the_loops_business(self):
        assert envstate.compare({"A": "1"}, {"A": "1", "EDITOR": "vi"}) == ()


class TestProcessEnviron:
    def test_reads_the_environment_a_process_was_started_with(self, sleeper):
        """
        Feature: reading what a running session actually holds
          Scenario: a process was started carrying the retired credential
            Given a child process spawned with the retired token in its environment
            When its environment is read back by pid
            Then the retired token is what comes back

        The environment a process was **started with** is the question: a harness
        reads its credentials once, at startup, which is the whole of why a
        rotation does not reach it.

        Requirement: R2.1
        """
        found = envstate.process_environ(sleeper.pid)
        assert found is not None
        assert found["THE_LOOP_TEST_MARKER"] == RETIRED

    def test_a_pid_that_cannot_be_read_is_none_never_an_exception(self):
        """
        Feature: an absent answer is not an answer
          Scenario: the pid has exited
            Given a pid no process holds
            When its environment is read
            Then the answer is None — callers report *unverified*, not drift

        Requirement: R2.3
        """
        assert envstate.process_environ(0) is None
        assert envstate.process_environ(-1) is None
        # 2**22 is above every default pid_max; nothing holds it.
        assert envstate.process_environ(2**22) is None

    def test_the_verdict_names_the_rotation_that_did_not_reach_the_process(
        self, sleeper
    ):
        """issue-410 in one assertion: the file says the new token, the running
        process was started with the old one, and that is `stale`."""
        assert envstate.environ_matches_declared(
            {"THE_LOOP_TEST_MARKER": RETIRED}, sleeper.pid
        ) == ("fresh", ())
        assert envstate.environ_matches_declared(
            {"THE_LOOP_TEST_MARKER": TOKEN}, sleeper.pid
        ) == ("stale", ("THE_LOOP_TEST_MARKER",))

    def test_an_unreadable_process_is_unverified(self):
        assert envstate.environ_matches_declared({"A": "1"}, 2**22) == (
            "unverified",
            (),
        )


class TestSpawnEnvironment:
    def test_a_passthrough_name_is_what_the_file_declares(self, tmp_path, monkeypatch):
        """
        Feature: a session spawned after a change is not born stale
          Scenario: the daemon spawns while the file names the new passthrough value
            Given a configured env file and a passthrough naming one of its variables
            When the spawn environment is built
            Then it forwards that value, re-read now

        Requirement: R4.1; docs/specs/issue-482/requirements.md R4.4
        """
        config, path = _config(tmp_path, f"SLACK_BOT_TOKEN={TOKEN}\n")
        config["env"]["sessionPassthrough"] = ["SLACK_BOT_TOKEN"]
        monkeypatch.setattr(
            envstate, "declared", lambda c, p: ({"SLACK_BOT_TOKEN": TOKEN}, ())
        )
        env = envstate.spawn_environment(lambda: config)
        assert env.forward == {"SLACK_BOT_TOKEN": TOKEN}
        assert "SLACK_BOT_TOKEN" not in env.remove

    def test_issue_482_the_file_is_not_forwarded_by_default(
        self, tmp_path, monkeypatch
    ):
        """A file's names are kept out of a pane unless the passthrough admits them."""
        config, path = _config(tmp_path, f"SLACK_BOT_TOKEN={TOKEN}\n")
        monkeypatch.setattr(
            envstate, "declared", lambda c, p: ({"SLACK_BOT_TOKEN": TOKEN}, ())
        )
        env = envstate.spawn_environment(lambda: config)
        assert env.forward == {}
        assert "SLACK_BOT_TOKEN" in env.remove

    def test_no_env_file_forwards_nothing_and_still_strips_credentials(
        self, tmp_path, monkeypatch
    ):
        """R4.2, revised by issue-482: no file forwards nothing, and a token the
        daemon was started with is still kept out of the pane."""
        monkeypatch.setattr(envstate, "declared", lambda c, p: None)
        env = envstate.spawn_environment(lambda: {})
        assert env.forward == {}
        assert "GH_TOKEN" in env.remove

    def test_a_spawn_never_fails_on_the_env_file(self, monkeypatch):
        def boom():
            raise RuntimeError("the config is on fire")

        env = envstate.spawn_environment(boom)
        assert env.forward == {}
        assert "GH_TOKEN" in env.remove


# -- issue-533: env.sessionCredentials -----------------------------------------

SESSION_TOKEN = "session-scoped-token-0123456789"
DAEMON_TOKEN = "daemon-own-token-9876543210"


def _creds_config(tmp_path, entries, file_text=None, **env_extra):
    env: dict = {"sessionCredentials": entries}
    if file_text is not None:
        path = tmp_path / ".env"
        path.write_text(file_text)
        env["file"] = str(path)
    return {"env": env, **env_extra}


def _boundary(config, tmp_path):
    return envstate.session_environment(config, tmp_path / "cli-config.yaml")


def test_issue_533_no_session_credentials_is_todays_boundary(tmp_path, monkeypatch):
    """R1.2: without the key, the boundary is exactly what issue-482 built."""
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    path = tmp_path / ".env"
    path.write_text("JIRA_API_TOKEN=x\n")
    config = {"env": {"file": str(path)}}
    before = envstate.session_environment(config, tmp_path / "c.yaml")
    assert before.credentials == ()
    assert before.inherit == {}
    assert before.for_work_item("github:octo/repo#1") == before
    assert "SESSION_GH_TOKEN" not in before.remove


def test_issue_533_an_entry_is_inherited_from_its_source(tmp_path, monkeypatch):
    """R1.1, R1.5, R2.1: `from` is read daemon-side, `name` is what the pane sees."""
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    monkeypatch.setenv("GH_TOKEN", DAEMON_TOKEN)
    config = _creds_config(tmp_path, [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}])
    env = _boundary(config, tmp_path)
    assert env is not None
    # Before a work item is resolved nothing is inherited: fail closed.
    assert env.inherit == {}
    assert {"GH_TOKEN", "SESSION_GH_TOKEN"} <= set(env.remove)
    resolved = env.for_work_item("github:octo/repo#1")
    assert resolved.inherit == {"GH_TOKEN": SESSION_TOKEN}
    assert "GH_TOKEN" not in resolved.remove
    # The source variable never reaches a pane under its own name.
    assert "SESSION_GH_TOKEN" in resolved.remove
    assert SESSION_TOKEN not in repr(resolved)


def test_issue_533_from_defaults_to_name_and_the_file_wins(tmp_path, monkeypatch):
    """R1.5: the env file (re-read now) wins over the daemon's environment."""
    monkeypatch.setenv("SESSION_TOKEN_X", "from-the-environment-123")
    config = _creds_config(
        tmp_path, [{"name": "SESSION_TOKEN_X"}], file_text="SESSION_TOKEN_X=from-file-1\n"
    )
    resolved = _boundary(config, tmp_path).for_work_item("")
    assert resolved.inherit == {"SESSION_TOKEN_X": "from-file-1"}
    (tmp_path / ".env").write_text("SESSION_TOKEN_X=from-file-2\n")
    assert _boundary(config, tmp_path).for_work_item("").inherit == {
        "SESSION_TOKEN_X": "from-file-2"
    }


def test_issue_533_an_unset_source_is_skipped_with_a_warning(
    tmp_path, monkeypatch, caplog
):
    """R1.4, R2.2: the spawn proceeds without it, and the name stays stripped."""
    monkeypatch.delenv("SESSION_GH_TOKEN", raising=False)
    config = _creds_config(tmp_path, [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}])
    with caplog.at_level("WARNING", logger="the-loop.envstate"):
        resolved = _boundary(config, tmp_path).for_work_item("github:octo/repo#1")
    assert resolved.inherit == {}
    assert "GH_TOKEN" in resolved.remove
    assert "SESSION_GH_TOKEN" in caplog.text and "GH_TOKEN" in caplog.text


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "1BAD"},
        {"name": "GH_TOKEN", "from": "not a name"},
        {"from": "SESSION_GH_TOKEN"},
        "GH_TOKEN",
        {"name": "THE_LOOP_INSTANCE"},
    ],
)
def test_issue_533_a_malformed_entry_is_skipped(tmp_path, monkeypatch, caplog, entry):
    """R1.3: a bad entry warns and is skipped; the others still apply."""
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    monkeypatch.setenv("OTHER_TOKEN_SRC", "another-value-123456")
    config = _creds_config(tmp_path, [entry, {"name": "OTHER", "from": "OTHER_TOKEN_SRC"}])
    with caplog.at_level("WARNING", logger="the-loop.envstate"):
        resolved = _boundary(config, tmp_path).for_work_item("")
    assert resolved.inherit == {"OTHER": "another-value-123456"}
    assert "env.sessionCredentials" in caplog.text
    assert SESSION_TOKEN not in caplog.text


def test_issue_533_a_duplicate_name_keeps_the_first(tmp_path, monkeypatch, caplog):
    """R1.8."""
    monkeypatch.setenv("SRC_A", "first-value-1234567")
    monkeypatch.setenv("SRC_B", "second-value-1234567")
    config = _creds_config(
        tmp_path, [{"name": "TOK", "from": "SRC_A"}, {"name": "TOK", "from": "SRC_B"}]
    )
    with caplog.at_level("WARNING", logger="the-loop.envstate"):
        resolved = _boundary(config, tmp_path).for_work_item("")
    assert resolved.inherit == {"TOK": "first-value-1234567"}
    assert "TOK" in caplog.text and "second-value" not in caplog.text


def test_issue_533_a_daemon_credential_source_warns(tmp_path, monkeypatch, caplog):
    """R1.6, A6: honoured, but the operator is told to use a narrower token."""
    monkeypatch.setenv("THE_LOOP_GH_TOKEN", DAEMON_TOKEN)
    config = _creds_config(
        tmp_path,
        [{"name": "GH_TOKEN", "from": "THE_LOOP_GH_TOKEN"}],
        integrations={"github": {"api": {"tokenEnv": "THE_LOOP_GH_TOKEN"}}},
    )
    with caplog.at_level("WARNING", logger="the-loop.envstate"):
        resolved = _boundary(config, tmp_path).for_work_item("")
    assert resolved.inherit == {"GH_TOKEN": DAEMON_TOKEN}
    assert "THE_LOOP_GH_TOKEN" in caplog.text and "least-privilege" in caplog.text
    assert DAEMON_TOKEN not in caplog.text


@pytest.mark.parametrize(
    "ref, inherited",
    [
        ("github:octo/repo#1", True),
        ("github:OCTO/Repo#9", True),
        ("github:octo/other#1", False),
        ("github:ghe.example/octo/repo#1", False),
        ("jira:example.atlassian.net/ABC-1", False),
        ("", False),
    ],
)
def test_issue_533_repositories_scope_the_credential(
    tmp_path, monkeypatch, ref, inherited
):
    """R1.7, A7: out of scope, the name stays removed."""
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    config = _creds_config(
        tmp_path,
        [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN", "repositories": ["octo/repo"]}],
    )
    resolved = _boundary(config, tmp_path).for_work_item(ref)
    assert (resolved.inherit == {"GH_TOKEN": SESSION_TOKEN}) is inherited
    assert ("GH_TOKEN" in resolved.remove) is not inherited


def test_issue_533_repositories_with_a_host(tmp_path, monkeypatch):
    monkeypatch.setenv("SRC", SESSION_TOKEN)
    config = _creds_config(
        tmp_path, [{"name": "T", "from": "SRC", "repositories": ["ghe.example/octo/repo"]}]
    )
    env = _boundary(config, tmp_path)
    assert env.for_work_item("github:ghe.example/octo/repo#2").inherit == {"T": SESSION_TOKEN}
    assert env.for_work_item("github:octo/repo#2").inherit == {}


def test_issue_533_passthrough_still_refuses_a_credential(tmp_path, monkeypatch):
    """R1.9, A5: sessionCredentials is the only way in."""
    monkeypatch.setenv("GH_TOKEN", DAEMON_TOKEN)
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    config = _creds_config(tmp_path, [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}])
    config["env"]["sessionPassthrough"] = ["GH_TOKEN"]
    resolved = _boundary(config, tmp_path).for_work_item("")
    assert "GH_TOKEN" not in resolved.forward
    assert resolved.inherit == {"GH_TOKEN": SESSION_TOKEN}


def test_issue_533_compare_checks_an_inherited_value(tmp_path, monkeypatch):
    """R4.1: missing or different reads as drift; the current value is clean."""
    monkeypatch.setenv("SESSION_GH_TOKEN", SESSION_TOKEN)
    config = _creds_config(tmp_path, [{"name": "GH_TOKEN", "from": "SESSION_GH_TOKEN"}])
    wanted = _boundary(config, tmp_path).for_work_item("")
    assert envstate.compare(wanted, {"GH_TOKEN": SESSION_TOKEN}) == ()
    assert envstate.compare(wanted, {"GH_TOKEN": "old-value"}) == ("GH_TOKEN",)
    assert envstate.compare(wanted, {}) == ("GH_TOKEN",)
    # The source name held by the pane is itself a defect.
    assert envstate.compare(
        wanted, {"GH_TOKEN": SESSION_TOKEN, "SESSION_GH_TOKEN": SESSION_TOKEN}
    ) == ("SESSION_GH_TOKEN",)


def test_issue_533_session_credentials_alone_configure_the_boundary(
    tmp_path, monkeypatch
):
    """Drift is "configured" with only sessionCredentials set."""
    monkeypatch.setenv("SRC", SESSION_TOKEN)
    config = {"env": {"sessionCredentials": [{"name": "T", "from": "SRC"}]}}
    assert envstate.session_environment(config, tmp_path / "c.yaml") is not None
