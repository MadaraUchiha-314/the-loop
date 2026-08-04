"""Integration tests: routed event → dispatcher → real harness config on disk.

Feature: Pre-trust a spawned session's workspace
Requirement: docs/specs/issue-90/requirements.md

Each scenario drives the real ``Dispatcher`` worker with a real
``ClaudeCodeAdapter`` pointed at a fake HOME, so they prove what actually lands
in the harness's config — and, crucially, that it lands **before** the harness
is started rather than after.
"""

import json
import os
import time

import pytest

from the_loop.control import ControlConfig
from the_loop import eventlog
from the_loop.harness.base import DispatchResult
from the_loop.harness.claude_code import ClaudeCodeAdapter
from the_loop.runner import TmuxResult, TmuxRunner
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.trust import TrustConfig
from the_loop.workspace import Workspace
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig
from the_loop.webhook.router import RoutedEvent, extract_work_items

REF = "github:octo/repo#15"
LABEL = "the-loop: auto-execute"


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(home)))
    return home


@pytest.fixture
def workdir(tmp_path):
    """A brand-new per-work-item checkout, exactly like the workspace makes."""
    path = tmp_path / "workspace" / ".worktrees" / "github.com" / "octo" / "repo" / "s"
    path.mkdir(parents=True)
    return path


class RecordingClaudeAdapter(ClaudeCodeAdapter):
    """Real preparation, faked process launch — and it records the ordering.

    ``spawn`` snapshots whether the trust key was already on disk when the
    harness was (notionally) started: that snapshot is what turns "the key
    exists afterwards" into "the key existed *before* the dialog could appear".
    """

    def __init__(self, config_path, **kwargs):
        super().__init__(**kwargs)
        self._config_path = config_path
        self.spawns = []
        self.trusted_at_spawn = []

    def is_available(self):
        return True

    def spawn(self, work_item, prompt, cwd, timeout=None):
        self.spawns.append((work_item.ref, cwd))
        self.trusted_at_spawn.append(trusted_dirs(self._config_path))
        return DispatchResult(ok=True, session_id="spawned-1")

    def resume(self, session, prompt, timeout=None):
        return DispatchResult(ok=True, session_id=session.harness_session_id)


class DeadTmux(TmuxRunner):
    """A tmux runner whose sessions are always gone, forcing the respawn path.

    ``spawn`` snapshots the trusted directories the same way the adapter does,
    so the respawn gets the identical before-the-harness-starts assertion.
    """

    def __init__(self, config_path):
        super().__init__()
        self._config_path = config_path
        self.spawns = []
        self.trusted_at_spawn = []

    def deliver(self, session, prompt, timeout=None):
        return TmuxResult(ok=False, session_missing=True, error="gone")

    def spawn(
        self, work_item, adapter, prompt, cwd, session_id, timeout=None, resume=False
    ):
        # `resume` (issue-89): a respawn first tries to CONTINUE the dead
        # session's conversation, and that resume attempt starts a harness
        # process too — so the snapshot has to be taken here either way, which
        # is what pins the trust write ahead of both respawn paths.
        self.spawns.append(cwd)
        self.trusted_at_spawn.append(trusted_dirs(self._config_path))
        return TmuxResult(ok=True)


def trusted_dirs(config_path):
    """Directories currently marked trusted in the harness config."""
    if not config_path.exists():
        return []
    try:
        data = json.loads(config_path.read_text())
    except json.JSONDecodeError:
        return []
    return [
        key
        for key, entry in (data.get("projects") or {}).items()
        if isinstance(entry, dict) and entry.get("hasTrustDialogAccepted") is True
    ]


class StubWorkspace(Workspace):
    """A real workspace root, without the clone — `prepare` hands back `checkout`.

    `_trust_root()` reads `self.workspace.root`, so the root has to be genuine;
    the git work behind it is issue-76's and already covered by its own tests.
    """

    def __init__(self, root, checkout):
        super().__init__(root)
        self._checkout = checkout

    def prepare(self, target, slug, *, branch=None, timeout=None):
        return self._checkout


def make_dispatcher(tmp_path, adapter, workspace=None, **config_overrides):
    # Pre-issue-106 spawn behaviour (the start gate has its own tests).
    config_overrides.setdefault("control", ControlConfig(require_start_command=False))
    config = RoutingConfig(spawn_on_unmatched="labeled", **config_overrides)
    return Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": adapter},
        config=config,
        workspace=workspace,
    )


def routed_labeled_issue(delivery="l-1"):
    payload = {
        "action": "labeled",
        "label": {"name": LABEL},
        "repository": {"full_name": "octo/repo"},
        "issue": {"number": 15},
    }
    return RoutedEvent(
        event="issues",
        action="labeled",
        delivery_id=delivery,
        work_items=extract_work_items("issues", payload),
        payload=payload,
        labeled=True,
    )


def test_spawned_workspace_is_trusted_before_the_harness_starts(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: An auto-execute label spawns a session into a fresh checkout
      Given a work item whose checkout directory the harness has never seen
      And routing.harnessTrust is enabled with its defaults
      When a labeled issues event spawns a session there
      Then that exact directory is marked trusted in the harness config
      And it was already trusted at the moment the harness was started
      And no ancestor directory was trusted
    Requirement: docs/specs/issue-90/requirements.md#requirement-1
    """
    adapter = RecordingClaudeAdapter(fake_home / ".claude.json")
    dispatcher = make_dispatcher(tmp_path, adapter, spawn_workdir=str(workdir))

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    assert trusted_dirs(fake_home / ".claude.json") == [str(workdir)]
    # the ordering assertion: trusted *before* the harness process was started
    assert adapter.trusted_at_spawn == [[str(workdir)]]


def test_respawned_tmux_session_workspace_is_trusted_too(tmp_path, fake_home, workdir):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: A tmux session found dead is respawned
      Given a registered tmux-mode session whose tmux session is gone
      When an event is delivered to it and the dispatcher respawns it
      Then the respawned session's working directory is trusted first
      And that holds for EVERY harness start the respawn makes — both the
        issue-89 conversation-resume attempt and the fresh-conversation
        fallback it degrades to
    Requirement: docs/specs/issue-90/requirements.md#requirement-1
    """

    tmux = DeadTmux(fake_home / ".claude.json")
    adapter = RecordingClaudeAdapter(fake_home / ".claude.json")
    dispatcher = Dispatcher(
        registry=SessionRegistry(tmp_path / "sessions"),
        adapters={"claude": adapter},
        config=RoutingConfig(
            runner="tmux", control=ControlConfig(require_start_command=False)
        ),
        tmux_runner=tmux,
    )
    dispatcher.registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(workdir),
            runner="tmux",
            tmux_target="loop-github--octo-repo-15",
        )
    )

    dispatcher.handle(routed_labeled_issue(delivery="r-1"))
    assert wait_until(lambda: len(tmux.spawns) >= 1)
    dispatcher.stop()  # drains the worker, so every spawn is recorded below

    # A respawn starts the harness once to try resuming the conversation and,
    # if that fails, again for a fresh one. Assert on ALL of them: a regression
    # that trusted only before the fallback would still stall the resume path.
    assert tmux.spawns and set(tmux.spawns) == {str(workdir)}
    assert tmux.trusted_at_spawn == [[str(workdir)]] * len(tmux.spawns)


def test_bypass_disclaimer_is_accepted_when_the_operator_configured_it(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: harnessArgs ask for bypass-permissions mode
      Given routing.harnessArgs.claude contains --dangerously-skip-permissions
      When a session is spawned
      Then the bypass-permissions disclaimer acceptance is recorded in the
        harness's user settings, so the configured flag actually takes effect
    Requirement: docs/specs/issue-90/requirements.md#requirement-2
    """
    adapter = RecordingClaudeAdapter(
        fake_home / ".claude.json", extra_args=["--dangerously-skip-permissions"]
    )
    dispatcher = make_dispatcher(tmp_path, adapter, spawn_workdir=str(workdir))

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    settings = json.loads((fake_home / ".claude" / "settings.json").read_text())
    assert settings["skipDangerousModePermissionPrompt"] is True


def test_a_failing_preparation_does_not_fail_the_dispatch(tmp_path, fake_home, workdir):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: The harness config cannot be written
      Given the harness config file exists but is not valid JSON
      When a labeled issues event spawns a session
      Then the spawn still happens and the session is registered
      And a workspace.trust_failed record is written to the event log
    Requirement: docs/specs/issue-90/requirements.md#requirement-3
    """
    (fake_home / ".claude.json").write_text("{ not json")
    log = tmp_path / "events.jsonl"
    eventlog.configure("gh-webhook", path=log, enabled=True)

    adapter = RecordingClaudeAdapter(fake_home / ".claude.json")
    dispatcher = make_dispatcher(tmp_path, adapter, spawn_workdir=str(workdir))

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    assert dispatcher.registry.find_by_work_item(REF) is not None
    types = [json.loads(line)["event"] for line in log.read_text().splitlines()]
    assert "workspace.trust_failed" in types
    assert "session.spawned" in types
    assert (fake_home / ".claude.json").read_text() == "{ not json"


def test_workspace_root_scope_trusts_the_root_covering_every_checkout(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: A workspace root is configured and the scope is the default
      Given routing.workspace.root is set and contains the spawn directory
      And routing.harnessTrust.scope is workspace-root (the default)
      When a labeled issues event spawns a session
      Then the workspace ROOT is marked trusted, covering every checkout under
        it — including folders the-loop never spawned into
      And the spawn directory is marked trusted in its own right, because the
        gate that decides whether the dialog appears for a repo carrying
        .claude/settings.json grants reads the exact key with no ancestor walk
      And that was already true at the moment the harness was started
      And the spawn directory still gets its own onboarding key, which the
        harness does not inherit from an ancestor
    Requirement: docs/specs/issue-136/bugfix.md#requirement-1
    """
    root = tmp_path / "workspace"
    adapter = RecordingClaudeAdapter(fake_home / ".claude.json")
    dispatcher = make_dispatcher(
        tmp_path,
        adapter,
        spawn_workdir=str(workdir),
        workspace=StubWorkspace(root, workdir),
    )

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    projects = json.loads((fake_home / ".claude.json").read_text())["projects"]
    assert projects[str(root)]["hasTrustDialogAccepted"] is True
    assert projects[str(workdir)]["hasTrustDialogAccepted"] is True
    assert projects[str(workdir)]["hasCompletedProjectOnboarding"] is True
    # a sibling checkout the-loop never spawned into is covered by the root
    assert str(root) in trusted_dirs(fake_home / ".claude.json")
    # the ordering assertion: the checkout was trusted *before* the harness ran,
    # which is the whole point — a dialog is not something a daemon can answer
    assert [sorted(snap) for snap in adapter.trusted_at_spawn] == [
        sorted([str(root), str(workdir)])
    ]


def test_directory_scope_keeps_trust_on_the_checkout_alone(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: The operator opts into least-privilege trust
      Given a workspace root is configured
      And routing.harnessTrust.scope is directory
      When a labeled issues event spawns a session
      Then only the exact spawn directory is trusted, not the root
    Requirement: docs/specs/issue-90/requirements.md#requirement-1
    """
    root = tmp_path / "workspace"
    adapter = RecordingClaudeAdapter(
        fake_home / ".claude.json", trust=TrustConfig(scope="directory")
    )
    dispatcher = make_dispatcher(
        tmp_path,
        adapter,
        spawn_workdir=str(workdir),
        workspace=StubWorkspace(root, workdir),
        harness_trust=TrustConfig(scope="directory"),
    )

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    assert trusted_dirs(fake_home / ".claude.json") == [str(workdir)]


def test_a_too_broad_workspace_root_degrades_to_the_checkout(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: The configured workspace root is the home directory itself
      Given routing.workspace.root is $HOME
      And the scope is workspace-root
      When a labeled issues event spawns a session
      Then the home directory is NOT blanket-trusted
      And trust falls back to the exact spawn directory
    Requirement: docs/specs/issue-90/requirements.md#requirement-1
    """
    adapter = RecordingClaudeAdapter(fake_home / ".claude.json")
    dispatcher = make_dispatcher(
        tmp_path,
        adapter,
        spawn_workdir=str(workdir),
        workspace=StubWorkspace(fake_home, workdir),
    )

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    trusted = trusted_dirs(fake_home / ".claude.json")
    assert str(fake_home) not in trusted
    assert trusted == [str(workdir)]


def test_an_exploding_adapter_hook_does_not_wedge_the_work_item(
    tmp_path, fake_home, workdir
):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: The preparation hook itself raises
      Given an adapter whose prepare_environment raises
      When a labeled issues event spawns a session
      Then the spawn still happens
      And the failure is recorded as workspace.trust_failed
    Requirement: docs/specs/issue-90/requirements.md#requirement-3
    """

    class ExplodingAdapter(RecordingClaudeAdapter):
        def prepare_environment(self, cwd, root=None):
            raise RuntimeError("kaboom")

    log = tmp_path / "events.jsonl"
    eventlog.configure("gh-webhook", path=log, enabled=True)

    adapter = ExplodingAdapter(fake_home / ".claude.json")
    dispatcher = make_dispatcher(tmp_path, adapter, spawn_workdir=str(workdir))

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    records = [json.loads(line) for line in log.read_text().splitlines()]
    failed = next(r for r in records if r["event"] == "workspace.trust_failed")
    assert "kaboom" in failed["error"]
    assert any(r["event"] == "session.spawned" for r in records)


def test_disabled_trust_leaves_the_harness_config_alone(tmp_path, fake_home, workdir):
    """
    Feature: Pre-trust a spawned session's workspace
    Scenario: The operator opted out
      Given routing.harnessTrust.enabled is false
      When a labeled issues event spawns a session
      Then the spawn happens exactly as before
      And nothing is written to the harness config
    Requirement: docs/specs/issue-90/requirements.md#requirement-3
    """
    adapter = RecordingClaudeAdapter(
        fake_home / ".claude.json", trust=TrustConfig(enabled=False)
    )
    dispatcher = make_dispatcher(tmp_path, adapter, spawn_workdir=str(workdir))

    dispatcher.handle(routed_labeled_issue())
    assert wait_until(lambda: len(adapter.spawns) == 1)
    dispatcher.stop()

    assert list(fake_home.iterdir()) == []
