"""Unit tests for dispatch-lifecycle emoji reactions (issue-84, issue-442).

Pure pieces only: config parsing, target resolution and the call the reactor
makes on the daemon's GitHub client (driven by the in-memory double — no
network). Dispatcher-level scenarios live in ``test_reactions_integration.py``.
"""

import types
from typing import Any

import pytest
from ghfakes import FakeGitHubClient, http_error

from the_loop.ghapi import GitHubApiConfig
from the_loop.reactions import (
    KIND_ISSUE,
    KIND_ISSUE_COMMENT,
    KIND_REVIEW_COMMENT,
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


def test_reaction_config_defaults_are_on_with_closest_palette():
    config = ReactionConfig.from_mapping({})
    assert config.enabled is True  # default-on: owner decision, PR #85
    assert (config.started, config.completed, config.error) == (
        "eyes",
        "hooray",
        "confused",
    )
    assert config.github == GitHubApiConfig()


def test_reaction_config_from_mapping_reads_camel_case_keys():
    config = ReactionConfig.from_mapping(
        {
            "enabled": True,
            "started": "rocket",
            "completed": "+1",
            "error": "",
        }
    )
    assert config.enabled
    assert config.content_for(STATE_STARTED) == "rocket"
    assert config.content_for(STATE_COMPLETED) == "+1"
    assert config.content_for(STATE_ERROR) == ""  # explicitly skipped
    assert config.content_for("nonsense") == ""


# -- target_from_event ----------------------------------------------------------


def test_target_prefers_webhook_comment_node_id():
    event = routed(payload=comment_payload({"id": 123, "node_id": "IC_kwDOabc"}))
    target = target_from_event(event)
    assert target is not None and target.node_id == "IC_kwDOabc"
    assert (target.kind, target.id) == ("", 0)


def test_target_numeric_comment_id_uses_issue_comment_rest_endpoint():
    event = routed(payload=comment_payload({"id": 123}))
    target = target_from_event(event)
    assert target is not None
    assert (target.kind, target.id) == (KIND_ISSUE_COMMENT, 123)


def test_target_review_comment_uses_pulls_rest_endpoint():
    event = routed(
        event="pull_request_review_comment",
        payload=comment_payload({"id": 99}),
    )
    target = target_from_event(event)
    assert target is not None
    assert (target.kind, target.id) == (KIND_REVIEW_COMMENT, 99)


def test_target_poll_comment_carries_graphql_node_id_in_id():
    # The poll path synthesizes comment.id from the conversation read's GraphQL
    # shape (ghapi.list_issue_comments) — a node id, not a numeric REST id.
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
    assert (issue_target.kind, issue_target.id) == (KIND_ISSUE, 15)
    assert pr_target is not None
    assert (pr_target.kind, pr_target.id) == (KIND_ISSUE, 7)


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


def enabled_reactor(gh, **overrides):
    config = ReactionConfig(enabled=True, **overrides)
    return GitHubReactor(config=config, client=gh)


def test_reactor_posts_rest_reaction_for_numeric_comment():
    gh = FakeGitHubClient()
    reactor = enabled_reactor(gh)
    assert reactor.react(routed(payload=comment_payload({"id": 123})), STATE_STARTED)
    assert gh.reactions == [(KIND_ISSUE_COMMENT, 123, "eyes", "")]
    assert gh.calls[0][1]["owner"] == "octo" and gh.calls[0][1]["repo"] == "repo"


def test_reactor_posts_graphql_reaction_for_node_id():
    gh = FakeGitHubClient()
    reactor = enabled_reactor(gh)
    event = routed(payload=comment_payload({"id": "IC_kwDOabc"}))
    assert reactor.react(event, STATE_COMPLETED)
    assert gh.reactions == [("node", "IC_kwDOabc", "hooray", "")]


def test_reactor_reacts_on_the_issue_itself_for_a_presence_event():
    gh = FakeGitHubClient()
    event = routed(
        event="issues",
        payload={"repository": {"full_name": "octo/repo"}, "issue": {"number": 15}},
    )
    assert enabled_reactor(gh).react(event, STATE_STARTED)
    assert gh.reactions == [(KIND_ISSUE, 15, "eyes", "")]


def test_reactor_disabled_or_skipped_state_is_a_noop():
    gh = FakeGitHubClient()
    event = routed(payload=comment_payload({"id": 123}))
    off = GitHubReactor(config=ReactionConfig(enabled=False), client=gh)
    assert not off.react(event, STATE_STARTED)
    skipped = enabled_reactor(gh, error="")
    assert not skipped.react(event, STATE_ERROR)
    assert gh.calls == []


def test_reactor_unknown_content_is_skipped_with_warning(caplog):
    gh = FakeGitHubClient()
    reactor = enabled_reactor(gh, started="sparkles")
    with caplog.at_level("WARNING"):
        assert not reactor.react(
            routed(payload=comment_payload({"id": 123})), STATE_STARTED
        )
    assert gh.calls == []
    assert "unknown reaction" in caplog.text


def test_reactor_missing_token_noops_and_warns_once(caplog):
    gh = FakeGitHubClient(token=False)
    reactor = GitHubReactor(config=ReactionConfig(enabled=True), client=gh)
    event = routed(payload=comment_payload({"id": 123}))
    with caplog.at_level("WARNING"):
        assert not reactor.react(event, STATE_STARTED)
        assert not reactor.react(event, STATE_COMPLETED)
    assert gh.reactions == []
    assert caplog.text.count("no GitHub token") == 1  # warn once, not per event


def test_reactor_github_failure_returns_false_without_raising():
    gh = FakeGitHubClient(fail=http_error(404, "Not Found"))
    reactor = enabled_reactor(gh)
    assert not reactor.react(routed(payload=comment_payload({"id": 123})), STATE_ERROR)


def test_reactor_client_exception_returns_false():
    class Exploding(FakeGitHubClient):
        def add_reaction(self, *a, **k):
            raise OSError("socket vanished")

    reactor = GitHubReactor(config=ReactionConfig(enabled=True), client=Exploding())
    assert not reactor.react(
        routed(payload=comment_payload({"id": 123})), STATE_STARTED
    )


def test_reactor_unreactable_event_is_a_noop():
    gh = FakeGitHubClient()
    reactor = enabled_reactor(gh)
    ci_event = routed(
        event="workflow_run",
        payload={"repository": {"full_name": "octo/repo"}},
    )
    assert not reactor.react(ci_event, STATE_STARTED)
    assert gh.calls == []


def test_the_token_config_comes_from_the_integrations_block():
    """issue-109 declared GitHub once under `integrations`; issue-442 fans the
    `api` block (where the token is) in under `_github`."""
    from the_loop.cli_config import apply_integrations

    data = apply_integrations(
        {
            "integrations": {"github": {"api": {"tokenEnv": ["LOOP_TOKEN"]}}},
            "routing": {"reactions": {"enabled": True}},
        }
    )
    section = data["routing"]["reactions"]
    assert ReactionConfig.from_mapping(section).github == GitHubApiConfig(
        token_envs=("LOOP_TOKEN",)
    )


# -- the host (issue-311, R4) ----------------------------------------------------

GHE = "ghe.corp.example"
GHE_REF = f"github:{GHE}/octo/repo#15"


def test_the_target_carries_the_work_items_host():
    target = target_from_event(
        routed(
            payload=comment_payload({"id": 7}),
            work_items=[WorkItemRef.parse(GHE_REF)],
        )
    )
    assert target is not None and target.host == GHE
    default = target_from_event(routed(payload=comment_payload({"id": 7})))
    assert default is not None and default.host == ""


def test_a_hosted_reaction_is_posted_on_its_host():
    gh = FakeGitHubClient()
    reactor = enabled_reactor(gh)
    reactor.react(
        routed(
            payload=comment_payload({"id": 7}),
            work_items=[WorkItemRef.parse(GHE_REF)],
        ),
        STATE_STARTED,
    )
    reactor.react(
        routed(
            payload=comment_payload({"node_id": "IC_kwDOAbCdEf4AAAAB"}),
            work_items=[WorkItemRef.parse(GHE_REF)],
        ),
        STATE_STARTED,
    )
    assert gh.reactions == [
        (KIND_ISSUE_COMMENT, 7, "eyes", GHE),
        ("node", "IC_kwDOAbCdEf4AAAAB", "eyes", GHE),
    ]


def test_a_github_com_reaction_names_no_host():
    gh = FakeGitHubClient()
    enabled_reactor(gh).react(routed(payload=comment_payload({"id": 7})), STATE_STARTED)
    assert gh.reactions == [(KIND_ISSUE_COMMENT, 7, "eyes", "")]


# -- the settled-outcome acknowledgement table (issue-371) ----------------------


def test_every_settled_outcome_is_classified_or_deliberately_silent():
    """`ACK_STATES` covers the consumed branch and excludes the scope refusals.

    The table is the whole policy (design §"The table"), so it is asserted as
    data: what each outcome reads as, and — the security-relevant half — that an
    out-of-scope refusal has no entry at all, because a non-owner instance must
    leave no mark on another instance's work item (issue-322 R2.6).
    """
    from the_loop.webhook import dispatcher as disp

    assert disp.ACK_STATES == {
        disp.SETTLED_CONTROL_EXECUTED: STATE_COMPLETED,
        disp.SETTLED_CONTROL_REJECTED: STATE_ERROR,
        disp.SETTLED_CONTROL_AMBIGUOUS: STATE_ERROR,
        "awaiting-start": STATE_STARTED,
        "session-paused": STATE_STARTED,
        "collaborator-no-spawn": STATE_STARTED,
    }
    # Built from the same constants SETTLED_OUTCOMES is, so no key can drift.
    assert set(disp.ACK_STATES) <= set(disp.SETTLED_OUTCOMES)
    assert set(disp.SETTLED_SUPPRESSED) <= set(disp.ACK_STATES)
    assert not set(disp.SETTLED_OUT_OF_SCOPE) & set(disp.ACK_STATES)
    assert set(disp.ACK_STATES.values()) <= {
        STATE_STARTED,
        STATE_COMPLETED,
        STATE_ERROR,
    }


def test_a_reactor_that_raises_cannot_break_a_settle():
    """The decoration never costs the record (R2.1, R2.2).

    `GitHubReactor.react` never raises, but `_settle` must not *depend* on the
    caller having passed a real one: a stubbed or wrapped reactor that throws
    would otherwise take the settled delivery id down with it.
    """

    class ExplodingReactor:
        def react(self, routed, state):
            raise RuntimeError("boom")

    from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig, Deduper

    settle = Dispatcher._settle
    # A stand-in for `self`: `_settle` touches only these three attributes, and
    # building a real Dispatcher here would drag in a registry and a tmux runner
    # to prove something about two lines.
    fake: Any = types.SimpleNamespace(
        deduper=Deduper(), reactor=ExplodingReactor(), config=RoutingConfig()
    )
    event = routed(payload=comment_payload({"id": 7}))
    with pytest.raises(RuntimeError):
        settle(fake, event, "control-executed")
    # The record landed BEFORE the decoration was attempted — the ordering the
    # design requires, proven by the one thing that survives the explosion.
    assert fake.deduper.outcome(event.delivery_id) == "control-executed"
