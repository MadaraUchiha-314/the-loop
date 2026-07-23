"""``poll start`` CLI wiring (issue-65).

Before this fix, ``routing.webTerminal.enabled`` only launched ttyd from
``gh-webhook start`` — ``poll start`` shared the same tmux runner but had no
ttyd start/stop of its own, so the web terminal was silently absent when
polling was the ingress. These tests drive the real ``poll start`` command
(argparse included) and assert ttyd is spawned and stopped exactly as it is
for ``gh-webhook start``.

Spec: docs/specs/issue-34/design.md (poller shares the webhook routing stack).
"""

from the_loop import runner as runner_mod
from the_loop.cli import build_parser
from the_loop.commands import gh_webhook, poll
from the_loop.poller import github as gh_mod

CONFIG = """
webhooks:
  ghWebhook:
    routing:
      enabled: true
      runner: tmux
      webTerminal:
        enabled: true
        host: 127.0.0.1
        port: 7681
      authorizedUsers: ["octocat"]
polling:
  intervalSeconds: 60
  sources:
    - provider: github
      repos: ["octo/repo"]
"""


class FakePopen:
    """Stand-in for subprocess.Popen recording argv, no real process spawned."""

    instances = []

    def __init__(self, argv):
        self.argv = argv
        self.terminated = False
        FakePopen.instances.append(self)

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        pass

    def kill(self):
        pass


class FakeGhClient:
    """Stand-in for GhClient: no `gh` binary needed, no items discovered."""

    def __init__(self, binary="gh", **_kwargs):
        self.binary = binary

    def is_available(self):
        return True

    def list_labeled_issues(self, owner, repo, label):
        return []

    def list_labeled_prs(self, owner, repo, label):
        return []


def _configure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_dir = tmp_path / ".the-loop"
    config_dir.mkdir()
    # webhooks/polling live in the CLI config (issue-63, decision-032), not the
    # repo-local plugin config.
    cli_config_path = config_dir / "cli-config.yaml"
    cli_config_path.write_text(CONFIG)
    monkeypatch.setattr(gh_webhook, "_CONFIG_PATH", cli_config_path)
    monkeypatch.setattr(poll, "_CONFIG_PATH", cli_config_path)

    FakePopen.instances = []
    monkeypatch.setattr(runner_mod.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(runner_mod.shutil, "which", lambda _: "/usr/bin/x")
    monkeypatch.setattr(gh_mod.shutil, "which", lambda _: "/usr/bin/gh")
    monkeypatch.setattr(gh_mod, "GhClient", FakeGhClient)


def test_poll_start_launches_and_stops_ttyd_like_gh_webhook_start(
    tmp_path, monkeypatch
):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: `poll start` drives the same ttyd lifecycle as `gh-webhook start`
        Given routing.runner: tmux and routing.webTerminal.enabled: true
        When `poll start --once` runs a poll cycle and exits
        Then ttyd is launched for the shared tmux hub and terminated on shutdown
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)

    parser = build_parser()
    args = parser.parse_args(["poll", "start", "--once"])
    exit_code = args._action(args)

    assert exit_code == 0
    (proc,) = FakePopen.instances
    assert proc.argv[0] == "ttyd"
    assert proc.terminated is True


def test_poll_start_fails_fast_when_ttyd_missing(tmp_path, monkeypatch):
    """
    Feature: Web terminal parity across ingress paths
    Scenario: `poll start` preflights ttyd just like `gh-webhook start`
        Given routing.webTerminal.enabled: true but ttyd is not installed
        When `poll start --once` runs
        Then it fails fast instead of silently skipping the web terminal
    Requirement: github issue #65
    """
    _configure(tmp_path, monkeypatch)
    monkeypatch.setattr(
        runner_mod.shutil,
        "which",
        lambda binary: None if binary == "ttyd" else "/usr/bin/x",
    )

    parser = build_parser()
    args = parser.parse_args(["poll", "start", "--once"])
    exit_code = args._action(args)

    assert exit_code == 1
    assert FakePopen.instances == []
