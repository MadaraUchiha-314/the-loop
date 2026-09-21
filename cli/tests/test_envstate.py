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
    def test_is_what_the_file_declares(self, tmp_path, monkeypatch):
        """
        Feature: a session spawned after a rotation is not born stale
          Scenario: the daemon spawns while the file names the new credential
            Given a configured env file holding the new credential
            When the spawn environment is built
            Then it carries that credential

        Requirement: R4.1
        """
        config, path = _config(tmp_path, f"SLACK_BOT_TOKEN={TOKEN}\n")
        monkeypatch.setattr(
            envstate, "declared", lambda c, p: ({"SLACK_BOT_TOKEN": TOKEN}, ())
        )
        assert envstate.spawn_environment(lambda: config) == {"SLACK_BOT_TOKEN": TOKEN}

    def test_no_env_file_carries_nothing(self, tmp_path, monkeypatch):
        """R4.2 — a deployment declaring no env file spawns exactly as before."""
        monkeypatch.setattr(envstate, "declared", lambda c, p: None)
        assert envstate.spawn_environment(lambda: {}) == {}

    def test_a_spawn_never_fails_on_the_env_file(self, monkeypatch):
        def boom():
            raise RuntimeError("the config is on fire")

        assert envstate.spawn_environment(boom) == {}
