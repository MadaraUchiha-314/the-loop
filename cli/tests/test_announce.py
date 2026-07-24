"""Unit tests for the session announcement comment (issue-86).

Pure pieces only: config parsing, the markdown body, the no-op ladder and the
``gh api`` invocation the announcer builds (driven by a fake runner — no real
``gh``). Dispatcher-level scenarios live in ``test_tmux_runner_integration.py``.
"""

import subprocess

import pytest

from the_loop import announce as announce_mod
from the_loop.announce import AnnounceConfig, SessionAnnouncer, announcement_body
from the_loop.sessions import Session, WorkItemRef

REF = "github:octo/repo#15"
TARGET = "loop-github-octo-repo-15"


def make_session(**overrides) -> Session:
    session = Session(
        work_item=WorkItemRef.parse(REF),
        harness="claude",
        harness_session_id="9f1c-secret-session-id",
        cwd="/home/operator/work/checkouts/repo",
        runner="tmux",
        tmux_target=TARGET,
    )
    for key, value in overrides.items():
        setattr(session, key, value)
    return session


class FakeRun:
    """Record ``gh`` invocations without running one."""

    def __init__(self, returncode=0, raises=None):
        self.calls = []
        self.returncode = returncode
        self.raises = raises

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.calls.append(list(cmd))
        if self.raises is not None:
            raise self.raises
        return subprocess.CompletedProcess(
            cmd, self.returncode, stdout="", stderr="boom"
        )


@pytest.fixture
def gh_present(monkeypatch):
    monkeypatch.setattr(announce_mod.shutil, "which", lambda _: "/usr/bin/gh")


# -- AnnounceConfig -------------------------------------------------------------


def test_announce_config_defaults_are_on():
    config = AnnounceConfig.from_mapping({})
    assert config.enabled is True  # the point of issue-86 is that it reaches you
    assert config.gh_binary == "gh"


def test_announce_config_reads_camel_case_keys():
    config = AnnounceConfig.from_mapping({"enabled": False, "ghBinary": "/opt/gh"})
    assert config.enabled is False
    assert config.gh_binary == "/opt/gh"


# -- announcement_body ----------------------------------------------------------


def test_body_carries_the_attach_commands():
    body = announcement_body(make_session())
    assert f"tmux attach -t {TARGET}" in body
    assert f"the-loop sessions attach --work-item {REF} --read-only" in body
    assert "`claude`" in body


def test_body_leaks_no_paths_or_session_ids():
    # AC3.6: the comment is public — it must carry nothing about the operator's
    # machine beyond the session name the work-item ref already implies.
    body = announcement_body(make_session())
    assert "/home/operator" not in body
    assert "9f1c-secret-session-id" not in body


def test_body_explains_the_commands_survive_a_respawn():
    # A respawn reuses the same loop-<slug> name and posts no second comment
    # (owner decision, PR #87), so the body says the commands keep working.
    assert "respawn" in announcement_body(make_session())


# -- the no-op ladder -----------------------------------------------------------


def test_disabled_is_a_noop(gh_present):
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(enabled=False), runner=fake)
    assert announcer.announce(make_session()) is False
    assert fake.calls == []


def test_process_runner_sessions_are_not_announced(gh_present):
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    session = make_session(runner="process", tmux_target="")
    assert announcer.announce(session) is False
    assert fake.calls == []


def test_non_github_work_items_are_a_noop(gh_present):
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    session = make_session(work_item=WorkItemRef.parse("jira:acme/proj#4"))
    assert announcer.announce(session) is False
    assert fake.calls == []


def test_malformed_repo_coordinates_are_a_noop(gh_present):
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    session = make_session(
        work_item=WorkItemRef(provider="github", owner="octo", repo="re po", number=1)
    )
    assert announcer.announce(session) is False
    assert fake.calls == []


def test_missing_gh_warns_once(monkeypatch, caplog):
    monkeypatch.setattr(announce_mod.shutil, "which", lambda _: None)
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    with caplog.at_level("WARNING", logger="the-loop.announce"):
        assert announcer.announce(make_session()) is False
        assert announcer.announce(make_session()) is False
    assert fake.calls == []
    assert len([r for r in caplog.records if "gh CLI" in r.message]) == 1


# -- the gh invocation ----------------------------------------------------------


def test_posts_a_comment_on_the_work_item(gh_present):
    fake = FakeRun()
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    assert announcer.announce(make_session()) is True
    (cmd,) = fake.calls
    assert cmd[:4] == ["gh", "api", "--method", "POST"]
    # The issues endpoint serves PR conversations too.
    assert cmd[4] == "repos/octo/repo/issues/15/comments"
    body = cmd[cmd.index("-f") + 1]
    assert body.startswith("body=")
    assert f"tmux attach -t {TARGET}" in body


def test_gh_failure_is_a_logged_noop(gh_present):
    announcer = SessionAnnouncer(AnnounceConfig(), runner=FakeRun(returncode=1))
    assert announcer.announce(make_session()) is False


def test_gh_timeout_never_raises(gh_present):
    fake = FakeRun(raises=subprocess.TimeoutExpired(cmd="gh", timeout=30))
    announcer = SessionAnnouncer(AnnounceConfig(), runner=fake)
    assert announcer.announce(make_session()) is False


def test_gh_oserror_never_raises(gh_present):
    announcer = SessionAnnouncer(AnnounceConfig(), runner=FakeRun(raises=OSError("x")))
    assert announcer.announce(make_session()) is False
