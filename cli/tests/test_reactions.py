"""Unit tests for dispatch-lifecycle emoji reactions (issue-84).

Pure pieces only: config parsing, target resolution and the ``gh api``
invocation the reactor builds (driven by a fake runner — no real ``gh``).
Dispatcher-level scenarios live in ``test_reactions_integration.py``.
"""

import subprocess

import pytest

from the_loop import reactions as reactions_mod
from the_loop.reactions import (
    STATE_COMPLETED,
    STATE_ERROR,
    STATE_STARTED,
    GitHubReactor,
    ReactionConfig,
    target_from_event,
)
from the_loop.sessions import WorkItemRef
from the_loop.webhook.router import RoutedEvent

REF = "github:octo/repo#15"


def routed(event="issue_comment", payload=None, work_items=None):
    if work_items is None:
        work_items = [WorkItemRef.parse(REF)]
    return RoutedEvent(
        event=event,
        action="created",
        delivery_id="d-1",
        work_items=work_items,
        payload=payload or {},
    )


def comment_payload(comment, event_repo="octo/repo"):
    return {"repository": {"full_name": event_repo}, "comment": comment}


# -- ReactionConfig -------------------------------------------------------------


def test_reaction_config_defaults_are_off_and_closest_palette():
    config = ReactionConfig.from_mapping({})
    assert config.enabled is False  # opt-in: the daemon's first GitHub write
    assert (config.started, config.completed, config.error) == (
        "eyes",
        "hooray",
        "confused",
    )
    assert config.gh_binary == "gh"


def test_reaction_config_from_mapping_reads_camel_case_keys():
    config = ReactionConfig.from_mapping(
        {
            "enabled": True,
            "started": "rocket",
            "completed": "+1",
            "error": "",
            "ghBinary": "/opt/gh",
        }
    )
    assert config.enabled and config.gh_binary == "/opt/gh"
    assert config.content_for(STATE_STARTED) == "rocket"
    assert config.content_for(STATE_COMPLETED) == "+1"
    assert config.content_for(STATE_ERROR) == ""  # explicitly skipped
    assert config.content_for("nonsense") == ""


# -- target_from_event ----------------------------------------------------------


def test_target_prefers_webhook_comment_node_id():
    event = routed(payload=comment_payload({"id": 123, "node_id": "IC_kwDOabc"}))
    target = target_from_event(event)
    assert target is not None and target.node_id == "IC_kwDOabc"
    assert target.rest_path == ""


def test_target_numeric_comment_id_uses_issue_comment_rest_endpoint():
    event = routed(payload=comment_payload({"id": 123}))
    target = target_from_event(event)
    assert target is not None
    assert target.rest_path == "repos/octo/repo/issues/comments/123/reactions"


def test_target_review_comment_uses_pulls_rest_endpoint():
    event = routed(
        event="pull_request_review_comment",
        payload=comment_payload({"id": 99}),
    )
    target = target_from_event(event)
    assert target is not None
    assert target.rest_path == "repos/octo/repo/pulls/comments/99/reactions"


def test_target_poll_comment_carries_graphql_node_id_in_id():
    # The poll path synthesizes comment.id from gh's GraphQL comment shape
    # (GhClient._comment_from_json) — a node id, not a numeric REST id.
    event = routed(payload=comment_payload({"id": "IC_kwDOnode="}))
    target = target_from_event(event)
    assert target is not None and target.node_id == "IC_kwDOnode="


def test_target_falls_back_to_issue_then_pull_request():
    issue = routed(
        event="issues",
        payload={"repository": {"full_name": "octo/repo"}, "issue": {"number": 15}},
    )
    pr = routed(
        event="pull_request",
        payload={
            "repository": {"full_name": "octo/repo"},
            "pull_request": {"number": 7},
        },
    )
    issue_target = target_from_event(issue)
    pr_target = target_from_event(pr)
    assert issue_target is not None
    assert issue_target.rest_path == "repos/octo/repo/issues/15/reactions"
    assert pr_target is not None
    assert pr_target.rest_path == "repos/octo/repo/issues/7/reactions"


@pytest.mark.parametrize(
    "event",
    [
        # CI event: no comment, no issue/PR entity in the payload.
        routed(
            event="workflow_run",
            payload={
                "repository": {"full_name": "octo/repo"},
                "workflow_run": {"head_branch": "issue-15"},
            },
        ),
        # No repository at all.
        routed(payload={"comment": {"id": 1}}),
        # Repo segments that fail defensive validation.
        routed(payload=comment_payload({"id": 1}, event_repo="octo/re po")),
        # Comment id that is neither numeric nor a plausible node id.
        routed(payload=comment_payload({"id": "abc$;rm -rf"})),
        # Non-GitHub provider (a future Jira poll source): platform no-op.
        routed(
            payload=comment_payload({"id": 1}),
            work_items=[
                WorkItemRef(provider="jira", owner="octo", repo="repo", number=15)
            ],
        ),
    ],
)
def test_target_is_none_for_unreactable_events(event):
    assert target_from_event(event) is None


# -- GitHubReactor --------------------------------------------------------------


class FakeRunner:
    """Records gh invocations; returns a scripted CompletedProcess."""

    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.commands = []

    def __call__(self, cmd, capture_output=True, text=True, timeout=None):
        self.commands.append(list(cmd))
        return subprocess.CompletedProcess(
            cmd, self.returncode, stdout="", stderr=self.stderr
        )


def enabled_reactor(runner, monkeypatch, **overrides):
    monkeypatch.setattr(reactions_mod.shutil, "which", lambda _: "/usr/bin/gh")
    config = ReactionConfig(enabled=True, **overrides)
    return GitHubReactor(config=config, runner=runner)


def test_reactor_posts_rest_reaction_for_numeric_comment(monkeypatch):
    runner = FakeRunner()
    reactor = enabled_reactor(runner, monkeypatch)
    assert reactor.react(routed(payload=comment_payload({"id": 123})), STATE_STARTED)
    assert runner.commands == [
        [
            "gh",
            "api",
            "--method",
            "POST",
            "repos/octo/repo/issues/comments/123/reactions",
            "-f",
            "content=eyes",
        ]
    ]


def test_reactor_posts_graphql_reaction_for_node_id(monkeypatch):
    runner = FakeRunner()
    reactor = enabled_reactor(runner, monkeypatch)
    event = routed(payload=comment_payload({"id": "IC_kwDOabc"}))
    assert reactor.react(event, STATE_COMPLETED)
    (cmd,) = runner.commands
    assert cmd[:3] == ["gh", "api", "graphql"]
    assert "subjectId=IC_kwDOabc" in cmd
    assert "content=HOORAY" in cmd  # GraphQL enum spelling of `hooray`


def test_reactor_disabled_or_skipped_state_is_a_noop(monkeypatch):
    runner = FakeRunner()
    event = routed(payload=comment_payload({"id": 123}))
    off = GitHubReactor(config=ReactionConfig(enabled=False), runner=runner)
    assert not off.react(event, STATE_STARTED)
    skipped = enabled_reactor(runner, monkeypatch, error="")
    assert not skipped.react(event, STATE_ERROR)
    assert runner.commands == []


def test_reactor_unknown_content_is_skipped_with_warning(monkeypatch, caplog):
    runner = FakeRunner()
    reactor = enabled_reactor(runner, monkeypatch, started="sparkles")
    with caplog.at_level("WARNING"):
        assert not reactor.react(
            routed(payload=comment_payload({"id": 123})), STATE_STARTED
        )
    assert runner.commands == []
    assert "unknown reaction" in caplog.text


def test_reactor_missing_gh_noops_and_warns_once(monkeypatch, caplog):
    runner = FakeRunner()
    monkeypatch.setattr(reactions_mod.shutil, "which", lambda _: None)
    reactor = GitHubReactor(config=ReactionConfig(enabled=True), runner=runner)
    event = routed(payload=comment_payload({"id": 123}))
    with caplog.at_level("WARNING"):
        assert not reactor.react(event, STATE_STARTED)
        assert not reactor.react(event, STATE_COMPLETED)
    assert runner.commands == []
    assert caplog.text.count("not found on PATH") == 1  # warn once, not per event


def test_reactor_gh_failure_returns_false_without_raising(monkeypatch):
    runner = FakeRunner(returncode=1, stderr="HTTP 404")
    reactor = enabled_reactor(runner, monkeypatch)
    assert not reactor.react(routed(payload=comment_payload({"id": 123})), STATE_ERROR)


def test_reactor_runner_exception_returns_false(monkeypatch):
    def boom(cmd, capture_output=True, text=True, timeout=None):
        raise OSError("gh vanished")

    monkeypatch.setattr(reactions_mod.shutil, "which", lambda _: "/usr/bin/gh")
    reactor = GitHubReactor(config=ReactionConfig(enabled=True), runner=boom)
    assert not reactor.react(
        routed(payload=comment_payload({"id": 123})), STATE_STARTED
    )


def test_reactor_unreactable_event_is_a_noop(monkeypatch):
    runner = FakeRunner()
    reactor = enabled_reactor(runner, monkeypatch)
    ci_event = routed(
        event="workflow_run",
        payload={"repository": {"full_name": "octo/repo"}},
    )
    assert not reactor.react(ci_event, STATE_STARTED)
    assert runner.commands == []
