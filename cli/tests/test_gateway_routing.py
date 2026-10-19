"""Unit tests for consumer resolution and the adapters' shared halves (issue-496, T1 —
R2.2, R2.3, R5.1, R5.2, R5.4, R5.5, R5.7, R5.8, R5.10, R7.3).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from the_loop.gateway import config as gwconfig
from the_loop.gateway.adapters import common
from the_loop.gateway.routing import consumers_for
from the_loop.gateway.store import SqliteStore


@pytest.fixture()
def store(tmp_path):
    s = SqliteStore(tmp_path / "gw.db")
    yield s
    s.close()


@pytest.fixture()
def config(tmp_path) -> gwconfig.GatewayConfig:
    path = tmp_path / "gateway-config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "repositories": ["o/r"],
                "jira": {"poll": {"site": "acme.atlassian.net"}, "projects": ["PROJ"]},
                "slack": {"rooms": [{"channel": "CROOM", "workItem": "github:o/r#5"}]},
            }
        )
    )
    return gwconfig.load_gateway_config(path)


# -- consumers_for (R5.2) ------------------------------------------------------------------------


def test_claimants_come_first_including_the_linked_subjects(store):
    store.claim("loop-github-o-r-14", "laptop-a", "driver")
    store.claim("loop-github-o-r-77", "laptop-b", "reviewer")
    store.touch("laptop-c", "p", 60)
    store.register_actors("laptop-c", {"github": ["octocat"]}, peer="p")
    routing = consumers_for(
        "loop-github-o-r-77", ["loop-github-o-r-14"], ("github", "octocat"), store
    )
    assert routing.consumers == ("laptop-b", "laptop-a") and routing.by == "claim"


def test_a_registered_actor_when_no_claim(store):
    store.touch("laptop-c", "p", 60)
    store.register_actors("laptop-c", {"github": ["octocat"]}, peer="p")
    routing = consumers_for("loop-github-o-r-14", [], ("github", "octocat"), store)
    assert routing.consumers == ("laptop-c",) and routing.by == "actor"


def test_nothing_matches_means_hold(store):
    routing = consumers_for("loop-github-o-r-14", [], ("github", "nobody"), store)
    assert routing.consumers == () and routing.by == "hold"
    assert consumers_for("loop-x", [], None, store).by == "hold"


# -- resolve_ref: GitHub (R5.1, R5.4, R5.8, R5.10) ------------------------------------------------


def _gh(kind: str, **body) -> dict:
    return {"repository": {"full_name": "o/r"}, "sender": {"login": "octocat"}, **body}


def test_an_issue_number_resolves_on_a_declared_repository(store, config):
    resolved = common.resolve_ref(
        "github",
        "issue_comment",
        _gh("issue_comment", issue={"number": 14}),
        store,
        config,
    )
    assert resolved.work_item == "github:o/r#14"
    assert resolved.subject == "loop-github-o-r-14" and resolved.linked == ()


def test_an_undeclared_repository_is_unbound(store, config):
    payload = {"repository": {"full_name": "someone/else"}, "issue": {"number": 1}}
    with pytest.raises(common.Unbound) as info:
        common.resolve_ref("github", "issues", payload, store, config)
    assert info.value.reason == "undeclared-repository"


def test_a_pull_request_without_a_binding_resolves_to_its_own_subject(store, config):
    resolved = common.resolve_ref(
        "github",
        "pull_request",
        _gh("pull_request", pull_request={"number": 77}),
        store,
        config,
    )
    assert resolved.work_item == "github:o/r#77" and resolved.linked == ()


def test_a_bound_pull_request_also_links_the_ticket_subject(store, config):
    store.bind("github", "o/r#77", "github:o/r#14", "github-o-r-14")
    resolved = common.resolve_ref(
        "github",
        "pull_request_review",
        _gh("pull_request_review", pull_request={"number": 77}),
        store,
        config,
    )
    assert resolved.subject == "loop-github-o-r-77"
    assert resolved.linked == ("loop-github-o-r-14",)
    # a comment on the PR (issue_comment carrying `pull_request`) links the same way
    comment = _gh("issue_comment", issue={"number": 77, "pull_request": {"url": "…"}})
    assert common.resolve_ref(
        "github", "issue_comment", comment, store, config
    ).linked == ("loop-github-o-r-14",)


def test_a_check_run_resolves_through_its_pull_requests_else_is_unbound(store, config):
    ok = _gh(
        "check_run", check_run={"pull_requests": [{"number": 77}], "head_sha": "abc"}
    )
    assert (
        common.resolve_ref("github", "check_run", ok, store, config).work_item
        == "github:o/r#77"
    )
    with pytest.raises(common.Unbound):
        common.resolve_ref(
            "github",
            "status",
            _gh("status", sha="deadbeef", state="success"),
            store,
            config,
        )


def test_a_payload_that_is_not_an_object_is_invalid(store, config):
    with pytest.raises(common.Unbound) as info:
        common.resolve_ref("github", "issues", [1, 2], store, config)
    assert info.value.reason == "invalid-payload"


# -- resolve_ref: Jira ---------------------------------------------------------------------------


def test_a_mapped_jira_key_resolves_and_an_unmapped_project_is_unbound(store, config):
    payload = {
        "issue": {
            "key": "PROJ-7",
            "self": "https://acme.atlassian.net/rest/api/3/issue/1",
        }
    }
    resolved = common.resolve_ref("jira", "comment_created", payload, store, config)
    assert resolved.work_item == "jira:acme.atlassian.net/PROJ-7"
    assert resolved.subject == "loop-jira-acme.atlassian.net-PROJ-7"
    with pytest.raises(common.Unbound):
        common.resolve_ref(
            "jira", "comment_created", {"issue": {"key": "OTHER-1"}}, store, config
        )


# -- resolve_ref: Slack (R5.7, R5.10) ---------------------------------------------------------------


def test_a_bound_thread_resolves_a_room_falls_back_and_an_unknown_thread_is_held(
    store, config
):
    store.bind("slack", "C1:1700.1", "github:o/r#14", "github-o-r-14")
    bound = {
        "event": {
            "type": "message",
            "channel": "C1",
            "thread_ts": "1700.1",
            "ts": "1700.9",
        }
    }
    assert (
        common.resolve_ref("slack", "events_api", bound, store, config).work_item
        == "github:o/r#14"
    )
    room = {"event": {"type": "message", "channel": "CROOM", "ts": "1.1"}}
    assert (
        common.resolve_ref("slack", "events_api", room, store, config).work_item
        == "github:o/r#5"
    )
    unknown = {
        "event": {"type": "message", "channel": "C9", "thread_ts": "2.2", "ts": "2.3"}
    }
    held = common.resolve_ref("slack", "events_api", unknown, store, config)
    assert held.subject == "unassigned" and held.work_item is None
    assert held.held_key == "C9:2.2" and held.startable
    with pytest.raises(common.Unbound) as info:
        common.resolve_ref(
            "slack",
            "slash_commands",
            {"channel_id": "C9", "command": "/x"},
            store,
            config,
        )
    assert info.value.reason == "unbound"


def test_an_interactive_payload_locates_its_thread(store, config):
    store.bind("slack", "C1:1700.1", "github:o/r#14", "github-o-r-14")
    payload = {
        "type": "block_actions",
        "container": {"channel_id": "C1", "thread_ts": "1700.1"},
    }
    assert (
        common.resolve_ref("slack", "interactive", payload, store, config).work_item
        == "github:o/r#14"
    )


# -- actor_of (R5.5) ---------------------------------------------------------------------------------


def test_the_actor_is_the_comment_author_then_the_sender():
    assert (
        common.actor_of(
            "github",
            "issue_comment",
            {"comment": {"user": {"login": "a"}}, "sender": {"login": "b"}},
        )
        == "a"
    )
    assert common.actor_of("github", "issues", {"sender": {"login": "b"}}) == "b"
    assert common.actor_of("slack", "events_api", {"event": {"user": "U1"}}) == "U1"
    assert common.actor_of("slack", "interactive", {"user": {"id": "U2"}}) == "U2"
    assert common.actor_of("slack", "slash_commands", {"user_id": "U3"}) == "U3"
    assert (
        common.actor_of(
            "jira", "comment_created", {"comment": {"author": {"accountId": "j1"}}}
        )
        == "j1"
    )
    assert common.actor_of("github", "issues", {}) is None


# -- dedup_key (R7.3) --------------------------------------------------------------------------------


def test_a_github_comment_by_webhook_and_by_poll_give_one_key():
    payload = _gh("issue_comment", issue={"number": 14}, comment={"id": 6257})
    by_webhook = common.dedup_key("github", "issue_comment", payload, "d-uuid")
    by_poll = common.dedup_key("github", "issue_comment", payload, "poll-comment-6257")
    assert by_webhook == by_poll == "gh-comment-6257"


def test_slack_socket_and_http_copies_give_one_key():
    payload = {"event_id": "Ev01", "event": {"type": "message"}}
    assert (
        common.dedup_key("slack", "events_api", payload, "socket-env-1") == "slack-Ev01"
    )
    assert (
        common.dedup_key("slack", "events_api", payload, "http-req-9") == "slack-Ev01"
    )
    assert (
        common.dedup_key("slack", "interactive", {"trigger_id": "T1"}, "x")
        == "slack-trigger-T1"
    )


def test_issue_actions_ci_and_closure_keys():
    opened = _gh("issues", action="opened", issue={"number": 14, "updated_at": "t1"})
    assert (
        common.dedup_key("github", "issues", opened, "x")
        == "gh-issues-opened-o/r#14-t1"
    )
    closed = _gh("issues", action="closed", issue={"number": 14, "state": "closed"})
    assert common.dedup_key("github", "issues", closed, "x") == "gh-close-o/r#14-closed"
    ci = _gh(
        "check_run",
        check_run={"name": "lint", "conclusion": "failure", "head_sha": "abc"},
    )
    assert (
        common.dedup_key("github", "check_run", ci, "x") == "gh-ci-o/r@abc-lint-failure"
    )
    assert common.dedup_key("github", "ping", _gh("ping"), "d-1") == "github:d-1"
    jira = {
        "comment": {"id": "42"},
        "issue": {"self": "https://acme.atlassian.net/rest/x"},
    }
    assert (
        common.dedup_key("jira", "comment_created", jira, "x")
        == "jira-comment-acme.atlassian.net-42"
    )


def test_the_slug_matches_the_sessions_convention():
    assert common.slug_of("github:o/r#14") == "github-o-r-14"
    assert Path(__file__).is_file()


def test_the_dedup_key_tells_distinct_label_assignee_and_closure_events_apart():
    """
    Feature: one event, one row
      Scenario: the dedup key tells distinct label, assignee and closure events apart
        Given two `labeled` deliveries of one issue in the same second (two labels in
              one UI action), two `assigned` deliveries likewise, and a close → reopen →
              close sequence
        When their dedup keys are computed
        Then each distinct event has its own key, and the same delivery twice has one

    Requirement: docs/specs/issue-496/requirements.md#requirement-7 (R7.3)
                 (self-review R2)
    """
    from the_loop.gateway.adapters.common import dedup_key

    def labeled(name: str) -> dict:
        return {
            "action": "labeled",
            "issue": {"number": 14, "updated_at": "2026-10-19T10:00:00Z"},
            "label": {"name": name},
            "repository": {"full_name": "o/r"},
        }

    a = dedup_key("github", "issues", labeled("the-loop: approved"), "d-1")
    b = dedup_key("github", "issues", labeled("the-loop: auto-execute"), "d-2")
    assert a != b
    assert a == dedup_key("github", "issues", labeled("the-loop: approved"), "d-3")

    def assigned(login: str) -> dict:
        return {
            "action": "assigned",
            "issue": {"number": 14, "updated_at": "2026-10-19T10:00:00Z"},
            "assignee": {"login": login},
            "repository": {"full_name": "o/r"},
        }

    assert dedup_key("github", "issues", assigned("octocat"), "d-4") != dedup_key(
        "github", "issues", assigned("hubot"), "d-5"
    )

    def closed(when: str) -> dict:
        return {
            "action": "closed",
            "issue": {"number": 14, "state": "closed", "closed_at": when},
            "repository": {"full_name": "o/r"},
        }

    first = dedup_key("github", "issues", closed("2026-10-19T10:00:00Z"), "d-6")
    again = dedup_key("github", "issues", closed("2026-10-19T11:00:00Z"), "d-7")
    assert first != again
    assert first == dedup_key("github", "issues", closed("2026-10-19T10:00:00Z"), "d-8")


def test_a_comment_edit_is_its_own_event_while_its_creation_shares_one_key():
    """
    Feature: one event, one row
      Scenario: a comment edit is its own event while its creation shares one key
        Given a comment's `created` delivery by webhook and by poll, then its `edited`
              delivery (an attestation box ticked) and a later edit
        When their dedup keys are computed
        Then the two creations are one key, each edit is its own, and so is a deletion
              (critic C2)
    """
    from the_loop.gateway.adapters.common import dedup_key

    def comment(action: str, updated: str) -> dict:
        return {
            "action": action,
            "issue": {"number": 14},
            "comment": {"id": 6257, "updated_at": updated},
            "repository": {"full_name": "o/r"},
        }

    created = dedup_key("github", "issue_comment", comment("created", "t0"), "w-1")
    polled = dedup_key(
        "github", "issue_comment", comment("", "t0"), "poll-comment-6257"
    )
    assert created == polled == "gh-comment-6257"
    first_edit = dedup_key("github", "issue_comment", comment("edited", "t1"), "w-2")
    second_edit = dedup_key("github", "issue_comment", comment("edited", "t2"), "w-3")
    deleted = dedup_key("github", "issue_comment", comment("deleted", "t3"), "w-4")
    assert len({created, first_edit, second_edit, deleted}) == 4
    assert first_edit == dedup_key(
        "github", "issue_comment", comment("edited", "t1"), "w-5"
    )
