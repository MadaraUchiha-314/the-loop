"""`sessions restart` and the `status` drift line, end to end (issue-410).

The defect: a session's environment is whatever tmux handed its pane when the pane
was forked, so a credential rotation leaves the service on the new value and every
running session on the old one. The reporter's ~20 sessions kept posting to Slack
as a bot that was no longer a member of the channel, and **144 consecutive agent
questions failed over three days** before anyone could name the cause.

These tests drive the whole recovery over a real registry and a scripted tmux
runner: the selection, every outcome a session can have, the exit code each one
implies, and — the assertion the security section exists for — that no credential
**value** reaches a message, an event record or a rendered status on any path.

Spec: docs/specs/issue-410/design.md · testing plan rows T3, T4, T6.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

import pytest

from the_loop import envstate, eventlog
from the_loop.core import lifecycle as core_lifecycle
from the_loop.core import sessions as core_sessions
from the_loop.runner import TmuxResult
from the_loop.sessions import Session, SessionRegistry, WorkItemRef

NEW_TOKEN = "xoxb-bot-a-the-new-one-0123456789"
RETIRED_TOKEN = "xoxb-bot-b-the-retired-one-98765"
SECRET_VALUES = (NEW_TOKEN, RETIRED_TOKEN)


class ScriptedRunner:
    """A TmuxRunner stand-in whose panes have scriptable environments.

    ``environs`` maps a pid to what that process was started with; a pid absent
    from it is a process this host will not report on — which is the *unverified*
    path, distinct from drift. ``respawn_result`` and ``survives`` script the two
    ways a relaunch fails.
    """

    def __init__(
        self,
        pids: Optional[Dict[str, List[int]]] = None,
        environs: Optional[Dict[int, Dict[str, str]]] = None,
        respawn_result: Optional[TmuxResult] = None,
        survives: bool = True,
    ):
        self.pids = pids or {}
        self.environs = environs or {}
        self.respawn_result = respawn_result or TmuxResult(ok=True, exit_code=0)
        self.survives = survives
        self.respawned: List[str] = []
        self.handed: List[Dict[str, str]] = []
        self.env_provider = None

    def live_pane_pids(self, target: str) -> List[int]:
        return list(self.pids.get(target, []))

    def live_pane_pids_by_session(self) -> Dict[str, List[int]]:
        return {name: list(pids) for name, pids in self.pids.items()}

    def respawn_in(self, target, adapter, prompt, cwd, session_id, work_item=""):
        # Record what the pane would actually be handed. The runner's
        # `env_provider` is the only thing that puts the declared values on the
        # respawn argv, so a restart built on a runner without one relaunches
        # every session straight back onto the retired credential.
        self.respawned.append(target)
        self.handed.append(dict(self.env_provider() if self.env_provider else {}))
        return self.respawn_result

    def survived(self, target: str, delay: float) -> bool:
        return self.survives

    def process_environ(self, pid: int) -> Optional[Dict[str, str]]:
        return self.environs.get(pid)


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    """A registry, a configured env file holding the NEW token, and a runner seam."""
    registry_dir = tmp_path / "sessions"
    env_file = tmp_path / "the-loop.env"
    env_file.write_text(f"SLACK_BOT_TOKEN={NEW_TOKEN}\n", encoding="utf-8")
    config = {"env": {"file": str(env_file)}, "routing": {}}
    monkeypatch.setattr(
        core_sessions.cli_config,
        "default_cli_config_path",
        lambda: tmp_path / "cli-config.yaml",
    )
    registry = SessionRegistry(str(registry_dir))
    return {
        "config": config,
        "registry": registry,
        "registry_dir": str(registry_dir),
        "portable_dir": str(tmp_path / "portable"),
        "env_file": env_file,
    }


def add_session(deployment, number: int, session_id: str = "") -> Session:
    ref = WorkItemRef.parse(f"github:octo/repo#{number}")
    session = Session(
        work_item=ref,
        harness="claude",
        harness_session_id=session_id or f"uuid-{number}",
        cwd="/work",
        tmux_target=f"loop-github-octo-repo-{number}",
    )
    deployment["registry"].register(session)
    return session


def restart(deployment, runner, **kwargs):
    kwargs.setdefault("all_sessions", True)
    return core_sessions.restart_sessions(
        config=deployment["config"],
        registry_dir=deployment["registry_dir"],
        portable_dir=deployment["portable_dir"],
        **kwargs,
    )


@pytest.fixture
def scripted(monkeypatch):
    """Install a ScriptedRunner in place of every TmuxRunner core builds."""

    def install(runner: ScriptedRunner) -> ScriptedRunner:
        def build(*_a, **kwargs):
            # Core builds its own runner; keep whatever env_provider it passes so
            # the double can say what the pane would have received.
            runner.env_provider = kwargs.get("env_provider")
            return runner

        monkeypatch.setattr(core_sessions, "TmuxRunner", build)
        monkeypatch.setattr(envstate, "process_environ", runner.process_environ)
        return runner

    return install


def text_of(result) -> str:
    return "\n".join(m["text"] for m in result["messages"])


class TestSelection:
    def test_all_restarts_every_running_session(self, deployment, scripted):
        """
        Feature: rolling the fleet after a credential rotation
          Scenario: every running session is on the retired token
            Given three running sessions started with the retired token
            When the operator restarts them all
            Then each pane is respawned and each comes back on the new token

        Requirement: docs/specs/issue-410/requirements.md R1.1, R2.1
        """
        for number in (15, 16, 17):
            add_session(deployment, number)
        runner = scripted(
            ScriptedRunner(
                pids={f"loop-github-octo-repo-{n}": [100 + n] for n in (15, 16, 17)},
                environs={
                    100 + n: {"SLACK_BOT_TOKEN": NEW_TOKEN} for n in (15, 16, 17)
                },
            )
        )
        result = restart(deployment, runner)
        assert result["exitCode"] == 0
        assert len(runner.respawned) == 3
        assert [row["outcome"] for row in result["sessions"]] == ["restarted"] * 3

    def test_the_respawned_pane_is_handed_the_file_not_the_frozen_environment(
        self, deployment, scripted
    ):
        """
        Feature: the relaunch actually carries the rotation
          Scenario: a session is respawned after the credential was rotated
            Given an env file naming the new token
            When the session is relaunched
            Then the pane is handed that token — not whatever tmux had frozen

        Without this the command relaunches every session straight back onto the
        retired credential and then reports all of them stale: a busy no-op.

        Requirement: docs/specs/issue-410/requirements.md R1.1, R2.1
        """
        add_session(deployment, 15)
        runner = scripted(
            ScriptedRunner(
                pids={"loop-github-octo-repo-15": [115]},
                environs={115: {"SLACK_BOT_TOKEN": NEW_TOKEN}},
            )
        )
        restart(deployment, runner)
        assert runner.handed == [{"SLACK_BOT_TOKEN": NEW_TOKEN}]

    def test_a_named_work_item_leaves_the_others_running(self, deployment, scripted):
        """R1.2 — one work item, one pane touched."""
        for number in (15, 16):
            add_session(deployment, number)
        runner = scripted(
            ScriptedRunner(
                pids={f"loop-github-octo-repo-{n}": [100 + n] for n in (15, 16)},
                environs={100 + n: {"SLACK_BOT_TOKEN": NEW_TOKEN} for n in (15, 16)},
            )
        )
        result = restart(
            deployment,
            runner,
            refs=["github:octo/repo#15"],
            all_sessions=False,
        )
        assert runner.respawned == ["loop-github-octo-repo-15"]
        assert [row["ref"] for row in result["sessions"]] == ["github:octo/repo#15"]

    def test_neither_all_nor_a_ref_refuses_and_touches_nothing(
        self, deployment, scripted
    ):
        """R1.3 — never guess at a fleet-wide relaunch."""
        add_session(deployment, 15)
        runner = scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        result = restart(deployment, runner, all_sessions=False)
        assert result["exitCode"] == 2
        assert not runner.respawned
        assert "--all" in text_of(result)

    def test_both_all_and_a_ref_is_the_same_refusal(self, deployment, scripted):
        runner = scripted(ScriptedRunner())
        result = restart(deployment, runner, refs=["github:octo/repo#15"])
        assert result["exitCode"] == 2
        assert not runner.respawned

    def test_an_unregistered_work_item_is_a_skipped_row(self, deployment, scripted):
        runner = scripted(ScriptedRunner())
        result = restart(
            deployment, runner, refs=["github:octo/repo#99"], all_sessions=False
        )
        assert result["sessions"][0]["outcome"] == "skipped"
        assert "no session is registered" in result["sessions"][0]["detail"]


class TestRefusals:
    def test_no_env_file_refuses_rather_than_respawning_for_nothing(
        self, deployment, scripted
    ):
        """
        Feature: nothing to roll onto
          Scenario: the config names no env file
            Given a deployment with no `env.file`
            When the operator asks for a restart
            Then it refuses, and not one pane is replaced

        Requirement: R1.7
        """
        add_session(deployment, 15)
        deployment["config"] = {"routing": {}}
        runner = scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        result = restart(deployment, runner)
        assert result["exitCode"] == 2
        assert not runner.respawned
        assert "env.file" in text_of(result)

    def test_an_env_file_declaring_nothing_refuses_too(self, deployment, scripted):
        add_session(deployment, 15)
        deployment["env_file"].write_text("# nothing here\n", encoding="utf-8")
        runner = scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        result = restart(deployment, runner)
        assert result["exitCode"] == 2
        assert not runner.respawned


class TestOutcomes:
    def _one(self, deployment, scripted, **runner_kwargs):
        add_session(deployment, 15, **runner_kwargs.pop("session", {}))
        runner = scripted(ScriptedRunner(**runner_kwargs))
        return runner, restart(deployment, runner)

    def test_a_session_that_is_not_running_is_skipped_never_started(
        self, deployment, scripted
    ):
        """R1.6 — `restart` refreshes what is running; `start` brings one up."""
        runner, result = self._one(deployment, scripted, pids={})
        assert result["sessions"][0]["outcome"] == "skipped"
        assert "not running" in result["sessions"][0]["detail"]
        assert not runner.respawned
        assert result["exitCode"] == 0

    def test_a_session_with_no_resumable_conversation_is_left_running(
        self, deployment, scripted
    ):
        """
        Feature: a stale token is not worth a lost conversation
          Scenario: the registry records no resumable harness conversation
            Given a running session whose recorded conversation id is empty
            When the fleet is restarted
            Then that pane is skipped and left running, not replaced with a blank one

        Requirement: R1.5
        """
        runner, result = self._one(
            deployment,
            scripted,
            session={"session_id": " "},
            pids={"loop-github-octo-repo-15": [115]},
        )
        assert result["sessions"][0]["outcome"] == "skipped"
        assert not runner.respawned

    def test_a_malformed_conversation_id_never_reaches_an_argv(
        self, deployment, scripted
    ):
        runner, result = self._one(
            deployment,
            scripted,
            session={"session_id": "uuid-1; rm -rf /"},
            pids={"loop-github-octo-repo-15": [115]},
        )
        assert result["sessions"][0]["outcome"] == "skipped"
        assert not runner.respawned

    def test_a_tmux_refusal_is_a_failure_and_exits_non_zero(self, deployment, scripted):
        runner, result = self._one(
            deployment,
            scripted,
            pids={"loop-github-octo-repo-15": [115]},
            respawn_result=TmuxResult(ok=False, error="tmux respawn-pane exited 1"),
        )
        assert result["sessions"][0]["outcome"] == "failed"
        assert "respawn-pane" in result["sessions"][0]["detail"]
        assert result["exitCode"] == 1

    def test_a_relaunched_harness_that_dies_at_once_is_a_failure(
        self, deployment, scripted
    ):
        """The issue-89 rule: `claude --resume <id>` exits in well under a second
        when it cannot resume, so a pane that is gone by the probe is a corpse."""
        runner, result = self._one(
            deployment,
            scripted,
            pids={"loop-github-octo-repo-15": [115]},
            survives=False,
        )
        assert result["sessions"][0]["outcome"] == "failed"
        assert "could not be resumed" in result["sessions"][0]["detail"]
        assert result["exitCode"] == 1

    def test_a_session_still_on_the_retired_token_fails_loudly(
        self, deployment, scripted
    ):
        """
        Feature: the relaunch is proved, not assumed
          Scenario: the pane comes back still carrying the retired credential
            Given a respawn that succeeds but whose process holds the old token
            When the restart verifies it
            Then that session is named, the variable is named, and the exit is 1

        Requirement: R2.2
        """
        runner, result = self._one(
            deployment,
            scripted,
            pids={"loop-github-octo-repo-15": [115]},
            environs={115: {"SLACK_BOT_TOKEN": RETIRED_TOKEN}},
        )
        row = result["sessions"][0]
        assert row["outcome"] == "stale"
        assert row["stale"] == ["SLACK_BOT_TOKEN"]
        assert result["exitCode"] == 1
        assert "SLACK_BOT_TOKEN" in text_of(result)

    def test_an_unreadable_environment_is_unverified_and_does_not_fail_the_run(
        self, deployment, scripted
    ):
        """R2.3 — the absence of an answer is not an answer. `-e` is deterministic;
        verification is the check on it, not the mechanism."""
        runner, result = self._one(
            deployment, scripted, pids={"loop-github-octo-repo-15": [115]}
        )
        assert result["sessions"][0]["outcome"] == "unverified"
        assert result["exitCode"] == 0
        assert "could not be verified" in text_of(result)


class TestDryRun:
    def test_reports_the_selection_and_touches_nothing(self, deployment, scripted):
        """R2.4 — read what would be replaced before replacing any of it."""
        add_session(deployment, 15)
        add_session(deployment, 16)
        runner = scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        result = restart(deployment, runner, dry_run=True)
        assert not runner.respawned
        outcomes = {row["ref"]: row["outcome"] for row in result["sessions"]}
        assert outcomes["github:octo/repo#15"] == "would-restart"
        assert outcomes["github:octo/repo#16"] == "skipped"
        assert result["dryRun"] is True
        assert result["exitCode"] == 0


class TestDrift:
    def test_counts_only_what_it_observed(self, deployment, scripted):
        """
        Feature: the drift is visible before it bites
          Scenario: two of three running sessions hold the retired token
            Given three running sessions, one on the new token and two on the old
            When the drift is read
            Then two are stale out of three running

        Requirement: R3.1
        """
        for number in (15, 16, 17):
            add_session(deployment, number)
        scripted(
            ScriptedRunner(
                pids={f"loop-github-octo-repo-{n}": [100 + n] for n in (15, 16, 17)},
                environs={
                    115: {"SLACK_BOT_TOKEN": NEW_TOKEN},
                    116: {"SLACK_BOT_TOKEN": RETIRED_TOKEN},
                    117: {"SLACK_BOT_TOKEN": RETIRED_TOKEN},
                },
            )
        )
        drift = core_sessions.environment_drift(
            config=deployment["config"],
            registry_dir=deployment["registry_dir"],
            portable_dir=deployment["portable_dir"],
        )
        assert (drift["running"], drift["stale"], drift["unverified"]) == (3, 2, 0)

    def test_a_stopped_session_is_not_running_and_not_counted(
        self, deployment, scripted
    ):
        add_session(deployment, 15)
        scripted(ScriptedRunner(pids={}))
        drift = core_sessions.environment_drift(
            config=deployment["config"], registry_dir=deployment["registry_dir"]
        )
        assert drift["running"] == 0
        assert drift["sessions"][0]["verdict"] == "not-running"

    def test_no_env_file_claims_nothing_either_way(self, deployment, scripted):
        """R3.4 — with nothing to compare against, `configured` is false and no
        caller may read the zero counts as a clean fleet."""
        add_session(deployment, 15)
        scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        drift = core_sessions.environment_drift(
            config={"routing": {}}, registry_dir=deployment["registry_dir"]
        )
        assert drift["configured"] is False
        assert drift["stale"] == 0

    def test_an_unreadable_environment_is_not_drift(self, deployment, scripted):
        add_session(deployment, 15)
        scripted(ScriptedRunner(pids={"loop-github-octo-repo-15": [115]}))
        drift = core_sessions.environment_drift(
            config=deployment["config"], registry_dir=deployment["registry_dir"]
        )
        assert drift["stale"] == 0
        assert drift["unverified"] == 1


class TestStatusLine:
    def test_one_line_when_the_fleet_has_drifted(self):
        """R3.1 — it names the count, the total, and the command that fixes it."""
        line = core_lifecycle.environment_line(
            {"sessionEnvironment": {"running": 6, "stale": 2}}
        )
        assert "2 of 6" in line
        assert "the-loop sessions restart --all" in line

    def test_a_clean_deployment_gains_no_line(self):
        """R3.2 — which is what keeps the line worth reading when it appears."""
        assert (
            core_lifecycle.environment_line(
                {"sessionEnvironment": {"running": 6, "stale": 0}}
            )
            == ""
        )
        assert core_lifecycle.environment_line({}) == ""

    def test_status_never_fails_on_an_unreadable_fleet(self, monkeypatch):
        """R3.4 — a `status` that cannot read /proc is still a `status`."""

        def boom(*_a, **_k):
            raise OSError("no /proc here")

        monkeypatch.setattr(core_sessions, "environment_drift", boom)
        assert core_lifecycle._session_environment({}) == {
            "configured": False,
            "running": 0,
            "stale": 0,
            "unverified": 0,
            "sessions": [],
        }


class TestSecretsAreNeverPrinted:
    def _sinks(self, deployment, result, tmp_path: Path) -> str:
        rendered = core_lifecycle.environment_line(
            {"sessionEnvironment": {"running": 1, "stale": 1}}
        )
        log = tmp_path / "events.jsonl"
        return "\n".join(
            [
                text_of(result),
                json.dumps(result["sessions"]),
                json.dumps(result.get("fingerprints") or {}),
                rendered,
                log.read_text(encoding="utf-8") if log.exists() else "",
            ]
        )

    @pytest.mark.parametrize(
        "case",
        ["fresh", "stale", "unverified", "failed"],
    )
    def test_no_declared_value_reaches_any_output_on_any_path(
        self, deployment, scripted, tmp_path, monkeypatch, case
    ):
        """
        Feature: fixing a leak must not publish one
          Scenario: a restart on every outcome it can produce
            Given a fleet on the retired token and a file declaring the new one
            When the restart runs and lands on each outcome in turn
            Then neither credential appears in any message, row, fingerprint or
                 event record — only names and fingerprints do

        Requirement: R5.1, R5.3
        """
        eventlog.configure(str(tmp_path / "events.jsonl"), enabled=True)
        add_session(deployment, 15)
        environs = {
            "fresh": {115: {"SLACK_BOT_TOKEN": NEW_TOKEN}},
            "stale": {115: {"SLACK_BOT_TOKEN": RETIRED_TOKEN}},
            "unverified": {},
            "failed": {},
        }[case]
        runner = scripted(
            ScriptedRunner(
                pids={"loop-github-octo-repo-15": [115]},
                environs=environs,
                survives=case != "failed",
            )
        )
        result = restart(deployment, runner)
        haystack = self._sinks(deployment, result, tmp_path)
        for value in SECRET_VALUES:
            assert value not in haystack, f"{value!r} leaked on the {case} path"
        # …and the name is still sayable, which is the whole point.
        assert "SLACK_BOT_TOKEN" in haystack

    def test_a_differing_variable_is_named_with_a_fingerprint_not_a_value(
        self, deployment, scripted
    ):
        """R5.2 — 'these two processes hold different tokens', without either."""
        add_session(deployment, 15)
        runner = scripted(
            ScriptedRunner(
                pids={"loop-github-octo-repo-15": [115]},
                environs={115: {"SLACK_BOT_TOKEN": RETIRED_TOKEN}},
            )
        )
        result = restart(deployment, runner)
        assert envstate.fingerprint(NEW_TOKEN) in text_of(result)
        assert NEW_TOKEN not in text_of(result)
