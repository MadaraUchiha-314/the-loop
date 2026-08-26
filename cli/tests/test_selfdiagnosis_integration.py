"""
Feature: Self-diagnosis — the-loop detects its own failures and files the bug itself
  the-loop watches its own event log for harness-level failures, debugs each new
  one in an isolated agent one-shot, and posts a redacted, labeled issue on
  the-loop's own repository — opt-in, default off, and never self-arming.

Requirement: docs/specs/issue-242/requirements.md
"""

import json
import subprocess
import threading
import time

import pytest

from the_loop import eventlog
from the_loop.authz import is_self_authored
from the_loop.control import ControlConfig, parse_command
from the_loop.core import selfdiagnosis as sd
from the_loop.critics import CriticResult
from the_loop.migrations import CURRENT_CONFIG_VERSION
from the_loop.runlock import RunLock

NOW = 1786000000.0

FINDINGS = {
    "title": "Read-only tmux attach breaks comment forwarding",
    "summary": "send-keys targets the session's current client.",
    "root_cause": "tmux resolves the read-only observer, not the pane.",
    "suggested_fix": "Target the pane id; also consider `the-loop start` guidance "
    "and never give up permanently on transient errors.",
}


class FakeAgent:
    def __init__(self, ok=True, output=None):
        self.calls = []
        self.ok = ok
        self.output = output if output is not None else json.dumps(FINDINGS)

    def __call__(self, prompt, cwd):
        self.calls.append((prompt, cwd))
        if not self.ok:
            return CriticResult(critic="self-diagnosis", error="agent exploded")
        return CriticResult(critic="self-diagnosis", ok=True, output=self.output)


class FakeGh:
    def __init__(self, returncode=0):
        self.calls = []
        self.returncode = returncode

    def __call__(self, cmd, capture_output=True, text=True, timeout=None, **kwargs):
        self.calls.append(list(cmd))
        stdout = json.dumps(
            {"html_url": "https://github.com/MadaraUchiha-314/the-loop/issues/999"}
        )
        return subprocess.CompletedProcess(cmd, self.returncode, stdout, "denied")


@pytest.fixture
def gh_present(monkeypatch):
    monkeypatch.setattr(sd.shutil, "which", lambda _: "/usr/bin/gh")


def write_log(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def error_record(**overrides):
    record = {
        "ts": "2026-08-16T01:00:00.000Z",
        "source": "poll",
        "event": "dispatch.failed",
        "level": "error",
        "work_item": "github:acme/private-repo#7",
        "cwd": "/home/loopuser/work/private-repo",
        "error": "tmux send-keys exited 1: client is read-only",
        "will_retry": False,
    }
    record.update(overrides)
    return record


def config(**overrides):
    section = {"enabled": True}
    section.update(overrides)
    return sd.SelfDiagnosisConfig.from_mapping({"selfDiagnosis": section})


def scan(tmp_path, cfg=None, agent=None, gh=None, records=None, **kwargs):
    log = tmp_path / "events.jsonl"
    if not log.exists():
        write_log(log, records if records is not None else [error_record()])
    return sd.scan(
        cfg or config(),
        log_path=log,
        state_path=tmp_path / "self-diagnosis.json",
        agent=agent if agent is not None else FakeAgent(),
        runner=gh if gh is not None else FakeGh(),
        now=NOW,
        **kwargs,
    )


class TestPipeline:
    def test_a_harness_failure_becomes_one_redacted_labeled_issue(
        self, tmp_path, gh_present
    ):
        """
        Feature: Self-diagnosis pipeline
        Scenario: A harness failure in the event log becomes one redacted, labeled issue
          Given an event log carrying an error-level dispatch failure
          And self-diagnosis is enabled with an agent and gh available
          When a scan runs
          Then one issue is created on the configured repository with the
               self-diagnosed label and the self-authored marker
          And the body carries no path, work-item ref or parseable control command
          And a second scan posts nothing further for the same defect

        Requirement: docs/specs/issue-242/requirements.md#R1 #R3 #R4 #R5
        """
        agent, gh = FakeAgent(), FakeGh()
        outcomes = scan(tmp_path, agent=agent, gh=gh)
        assert [o["action"] for o in outcomes] == ["posted"]
        assert outcomes[0]["url"].endswith("/issues/999")

        argv = gh.calls[0]
        assert argv[1:4] == ["api", "--method", "POST"]
        assert argv[4] == "repos/MadaraUchiha-314/the-loop/issues"
        assert "labels[]=the-loop: self-diagnosed" in argv
        assert not any("auto-execute" in part for part in argv)

        body = next(p for p in argv if p.startswith("body=")).removeprefix("body=")
        assert is_self_authored(body)
        assert "private-repo" not in body
        assert "/home/loopuser" not in body
        assert not parse_command(body, ControlConfig(enabled=True))
        # the agent's prompt is redacted the same way as the body (R3.2)
        prompt = agent.calls[0][0]
        assert "private-repo" not in prompt
        assert "/home/loopuser" not in prompt

        assert scan(tmp_path, agent=agent, gh=gh) == []
        assert len(gh.calls) == 1

    def test_the_posted_issue_is_recorded_in_state_and_event_log(
        self, tmp_path, gh_present
    ):
        """
        Feature: Self-diagnosis pipeline
        Scenario: The posted issue is traceable from local state and the event log
          Given a successful diagnosis and post
          When the scan finishes
          Then the fingerprint maps to the issue URL in local state
          And diagnosis.detected and diagnosis.posted are in the event log

        Requirement: docs/specs/issue-242/requirements.md#R5
        """
        own_log = tmp_path / "own-events.jsonl"
        eventlog.configure("test", path=own_log)
        scan(tmp_path)
        state = json.loads((tmp_path / "self-diagnosis.json").read_text())
        (url,) = [entry["url"] for entry in state["reported"].values()]
        assert url.endswith("/issues/999")
        events = [r["event"] for r in eventlog.read_events(own_log)]
        assert "diagnosis.detected" in events
        assert "diagnosis.posted" in events

    def test_a_dry_run_prints_the_report_and_posts_nothing(self, tmp_path, gh_present):
        """
        Feature: Self-diagnosis pipeline
        Scenario: A dry run prints the redacted report and posts nothing
          Given self-diagnosis with an agent available
          When a scan runs with dry_run
          Then the outcome carries the composed title and body
          And gh is never invoked and no state is written

        Requirement: docs/specs/issue-242/requirements.md#R2.2
        """
        gh = FakeGh()
        outcomes = scan(tmp_path, gh=gh, dry_run=True)
        assert [o["action"] for o in outcomes] == ["dry-run"]
        assert outcomes[0]["title"].startswith("[self-diagnosed] ")
        assert "client is read-only" in outcomes[0]["body"]
        assert gh.calls == []
        assert not (tmp_path / "self-diagnosis.json").exists()

    def test_a_concurrent_scan_is_skipped_while_the_lock_is_held(
        self, tmp_path, gh_present
    ):
        """
        Feature: Self-diagnosis pipeline
        Scenario: A second concurrent scan is skipped while the lock is held
          Given another process holds the self-diagnosis scan lock
          When a scan runs
          Then it does nothing and reports nothing

        Requirement: docs/specs/issue-242/requirements.md#R1.6
        """
        gh = FakeGh()
        lock = RunLock(str(tmp_path / "self-diagnosis.json") + ".lock", name="other")
        assert lock.acquire()
        try:
            assert scan(tmp_path, gh=gh) == []
            assert gh.calls == []
        finally:
            lock.release()


class TestFailureAndBudget:
    def test_agent_failures_are_retried_then_abandoned(self, tmp_path, gh_present):
        """
        Feature: Self-diagnosis pipeline
        Scenario: A failing diagnosis agent is retried a bounded number of times
          Given an agent that always fails and maxRetries of 2
          When scans run repeatedly
          Then the agent is invoked exactly twice for the fingerprint
          And the fingerprint is abandoned and never retried

        Requirement: docs/specs/issue-242/requirements.md#R3.3
        """
        agent, gh = FakeAgent(ok=False), FakeGh()
        cfg = config(maxRetries=2)
        assert [o["action"] for o in scan(tmp_path, cfg, agent, gh)] == ["failed"]
        assert [o["action"] for o in scan(tmp_path, cfg, agent, gh)] == ["failed"]
        assert scan(tmp_path, cfg, agent, gh) == []
        assert len(agent.calls) == 2
        assert gh.calls == []
        state = json.loads((tmp_path / "self-diagnosis.json").read_text())
        assert len(state["abandoned"]) == 1

    def test_unparseable_agent_output_is_a_failure_not_a_post(
        self, tmp_path, gh_present
    ):
        """
        Feature: Self-diagnosis pipeline
        Scenario: Raw model output is never posted
          Given an agent whose output is not the JSON contract
          When a scan runs
          Then nothing is posted and the attempt is recorded as a failure

        Requirement: docs/specs/issue-242/requirements.md#R3.3 #R3.4
        """
        gh = FakeGh()
        outcomes = scan(tmp_path, agent=FakeAgent(output="I could not tell."), gh=gh)
        assert [o["action"] for o in outcomes] == ["failed"]
        assert gh.calls == []

    def test_the_daily_cap_defers_rather_than_drops(self, tmp_path, gh_present):
        """
        Feature: Self-diagnosis pipeline
        Scenario: The rolling daily cap defers the excess candidate
          Given two distinct failures and maxIssuesPerDay of 1
          When a scan runs
          Then one issue is posted and the other candidate is deferred
          And a scan a day later posts the deferred one

        Requirement: docs/specs/issue-242/requirements.md#R5.4
        """
        records = [
            error_record(),
            error_record(event="poll.spawn_failed", error="spawn exploded"),
        ]
        cfg = config(maxIssuesPerDay=1)
        gh = FakeGh()
        actions = sorted(
            o["action"] for o in scan(tmp_path, cfg, gh=gh, records=records)
        )
        assert actions == ["deferred", "posted"]
        assert len(gh.calls) == 1

        later = sd.scan(
            cfg,
            log_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "self-diagnosis.json",
            agent=FakeAgent(),
            runner=gh,
            now=NOW + 90000,
        )
        assert [o["action"] for o in later] == ["posted"]
        assert len(gh.calls) == 2


class TestOptInAndWatcher:
    def test_start_watcher_is_none_when_disabled(self):
        """
        Feature: Self-diagnosis opt-in
        Scenario: A deployment that never opted in runs nothing
          Given a CLI config with no selfDiagnosis section
          When a daemon asks for the watcher
          Then no thread is started

        Requirement: docs/specs/issue-242/requirements.md#R2.1
        """
        assert sd.start_watcher({}, threading.Event()) is None
        assert (
            sd.start_watcher({"selfDiagnosis": {"enabled": False}}, threading.Event())
            is None
        )

    def test_the_watcher_scans_on_its_interval_and_stops(self, tmp_path, monkeypatch):
        """
        Feature: Self-diagnosis opt-in
        Scenario: The watcher thread scans on its interval and stops with its daemon
          Given self-diagnosis enabled with a short interval
          When the watcher runs and the daemon's stop event is set
          Then scans happened while it ran and the thread ends

        Requirement: docs/specs/issue-242/requirements.md#R1.4
        """
        scans = []
        monkeypatch.setattr(sd, "scan", lambda *a, **kw: scans.append(1))
        stop = threading.Event()
        thread = sd.start_watcher(
            {"selfDiagnosis": {"enabled": True, "intervalSeconds": 0.01}},
            stop,
            log_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "self-diagnosis.json",
        )
        assert thread is not None
        deadline = time.monotonic() + 5.0
        while not scans and time.monotonic() < deadline:
            time.sleep(0.01)
        stop.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()
        assert scans

    def test_watcher_exceptions_do_not_kill_the_thread(self, tmp_path, monkeypatch):
        """
        Feature: Self-diagnosis opt-in
        Scenario: A failing scan never kills the watcher
          Given a scan that raises
          When the watcher ticks more than once
          Then the thread is still alive for the next tick

        Requirement: docs/specs/issue-242/requirements.md#R1.4
        """
        calls = []

        def boom(*a, **kw):
            calls.append(1)
            raise RuntimeError("scan exploded")

        monkeypatch.setattr(sd, "scan", boom)
        stop = threading.Event()
        thread = sd.start_watcher(
            {"selfDiagnosis": {"enabled": True, "intervalSeconds": 0.01}},
            stop,
            log_path=tmp_path / "events.jsonl",
            state_path=tmp_path / "self-diagnosis.json",
        )
        assert thread is not None
        deadline = time.monotonic() + 5.0
        while len(calls) < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(calls) >= 2
        stop.set()
        thread.join(timeout=5.0)


class TestDiagnoseCommand:
    def _config_file(self, tmp_path, extra=""):
        path = tmp_path / "cli-config.yaml"
        path.write_text(
            f'version: "{CURRENT_CONFIG_VERSION}"\n'
            f"state:\n  root: {tmp_path / 'state'}\n"
            f"eventLog:\n  enabled: true\n  path: {tmp_path / 'events.jsonl'}\n" + extra
        )
        return path

    def test_disabled_without_dry_run_is_a_refusal(self, tmp_path, capsys, monkeypatch):
        """
        Feature: the-loop diagnose
        Scenario: Running diagnose while disabled refuses with the enabling key
          Given a CLI config without selfDiagnosis.enabled
          When `the-loop diagnose` runs
          Then it refuses and names selfDiagnosis.enabled

        Requirement: docs/specs/issue-242/requirements.md#R2.2
        """
        from the_loop.commands import diagnose_cmd

        monkeypatch.setattr(
            diagnose_cmd.cli_config,
            "default_cli_config_path",
            lambda: self._config_file(tmp_path),
        )
        code = diagnose_cmd.DiagnoseCommand().run(_args(dry_run=False))
        assert code != 0
        assert "selfDiagnosis.enabled" in capsys.readouterr().err

    def test_dry_run_works_while_disabled_and_posts_nothing(
        self, tmp_path, capsys, monkeypatch
    ):
        """
        Feature: the-loop diagnose
        Scenario: A dry run previews the redacted report before opting in
          Given a disabled config and an event log with a failure
          And no agent binary on this machine
          When `the-loop diagnose --dry-run` runs
          Then it prints the redacted dossier that would be diagnosed
          And exits 0 without posting

        Requirement: docs/specs/issue-242/requirements.md#R2.2
        """
        from the_loop.commands import diagnose_cmd

        write_log(tmp_path / "events.jsonl", [error_record()])
        monkeypatch.setattr(
            diagnose_cmd.cli_config,
            "default_cli_config_path",
            lambda: self._config_file(tmp_path),
        )
        monkeypatch.setattr(sd.critics.shutil, "which", lambda _: None)
        code = diagnose_cmd.DiagnoseCommand().run(_args(dry_run=True))
        out = capsys.readouterr().out
        assert code == 0
        assert "client is read-only" in out
        assert "/home/loopuser" not in out


def _args(**kwargs):
    import argparse

    return argparse.Namespace(**kwargs)
