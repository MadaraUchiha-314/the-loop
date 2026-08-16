"""Integration tests: the excerpt at the seam both ingresses share (issue-243).

Spec: docs/specs/issue-243/ (requirements R4, R5; testing plan T4, T5).

Two things unit tests cannot see, because both are about *other* components
agreeing with this one:

1. **Ingress parity.** A comment left on a pull request must read the same to a
   session whether it arrived by webhook or by poll. The poller synthesises its
   own payloads (``GitHubPollProvider.comment_event``), so "one distillation
   function" is a claim about two producers, not one.
2. **The gates still read the payload.** The excerpt no longer shows the fields
   authorization, self-comment detection, control parsing and reaction targeting
   judge by. If any of them had been reading the rendered prompt, this change
   would have silently disarmed it.

Feature: A forwarded event carries the instruction, not GitHub's metadata
Requirement: docs/specs/issue-243/requirements.md#R4
"""

from __future__ import annotations

import json
import time

from conftest import FakeTmux, StubInteractiveAdapter
from the_loop.authz import is_authorized, is_self_authored, mark_self_authored
from the_loop.control import ControlConfig, parse_command
from the_loop.poller.base import Comment, WorkItem
from the_loop.poller.github import GitHubPollProvider
from the_loop.reactions import target_from_event
from the_loop.sessions import Session, SessionRegistry, WorkItemRef
from the_loop.webhook.dispatcher import Dispatcher, RoutingConfig, event_excerpt
from the_loop.webhook.router import RoutedEvent, event_actor, event_body

REF = "github:octo/repo#15"
TARGET = "loop-github-octo-repo-15"
INSTRUCTION = "please rerun the migration test"


def wait_until(predicate, timeout=5.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def webhook_comment_payload(body: str = INSTRUCTION, author: str = "reviewer") -> dict:
    """What GitHub itself POSTs for a comment on pull request #15."""
    user = {
        "login": author,
        "id": 42,
        "avatar_url": "https://avatars.githubusercontent.com/u/42?v=4",
        "url": f"https://api.github.com/users/{author}",
        "html_url": f"https://github.com/{author}",
        "type": "User",
        "site_admin": False,
    }
    return {
        "action": "created",
        "issue": {
            "number": 15,
            "title": "the work item",
            "state": "open",
            "html_url": "https://github.com/octo/repo/issues/15",
            "user": {"login": "opener", "id": 1},
            "labels": [{"name": "the-loop: auto-execute", "color": "0e8a16"}],
            "body": "the whole issue body",
            "reactions": {"url": "https://api.github.com/x", "total_count": 0},
        },
        "comment": {
            "id": 98765,
            "node_id": "IC_kwDOAAA",
            "url": "https://api.github.com/repos/octo/repo/issues/comments/98765",
            "html_url": "https://github.com/octo/repo/issues/15#issuecomment-98765",
            "user": user,
            "created_at": "2026-08-16T16:02:10Z",
            "author_association": "MEMBER",
            "body": body,
            "reactions": {"url": "https://api.github.com/y", "total_count": 0},
        },
        "repository": {
            "full_name": "octo/repo",
            "html_url": "https://github.com/octo/repo",
        },
        "sender": user,
    }


def polled_comment_event(body: str = INSTRUCTION, author: str = "reviewer"):
    """The same comment, as the poller synthesises it from `gh` output."""
    provider = GitHubPollProvider(repos=[], label="the-loop: auto-execute")
    item = WorkItem(
        provider="github",
        owner="octo",
        repo="repo",
        number=15,
        kind="issue",
        title="the work item",
        url="https://github.com/octo/repo/issues/15",
        author="opener",
        labels=["the-loop: auto-execute"],
    )
    comment = Comment(
        id="IC_kwDOAAA",
        body=body,
        author=author,
        created_at="2026-08-16T16:02:10Z",
        url="https://github.com/octo/repo/issues/15#issuecomment-98765",
    )
    refs = [WorkItemRef(provider="github", owner="octo", repo="repo", number=15)]
    return provider.comment_event(item, comment, refs)


# -- T4: the two ingresses render the same comment (R4) -----------------------


def test_the_poller_and_the_webhook_render_the_same_comment_identically():
    """
    Feature: A forwarded event carries the instruction, not GitHub's metadata
    Requirement: docs/specs/issue-243/requirements.md#R4

    Scenario: the poller and the webhook render the same comment identically
      Given the same comment on the same work item
      And one delivery arrives as a GitHub webhook payload
      And the other is synthesised by the poller from `gh` output
      When each is distilled for its session's prompt
      Then both carry the same body, the same address and the same author
      And neither carries GitHub's metadata
    """
    pushed = event_excerpt("issue_comment", webhook_comment_payload())
    polled_event = polled_comment_event()
    polled = event_excerpt(polled_event.event, polled_event.payload)

    assert json.loads(pushed) == json.loads(polled)
    assert json.loads(pushed) == {
        "comment": {
            "body": INSTRUCTION,
            "html_url": "https://github.com/octo/repo/issues/15#issuecomment-98765",
            "author": "reviewer",
        }
    }
    for text in (pushed, polled):
        assert "api.github.com" not in text
        assert "avatar_url" not in text


def test_a_polled_review_and_inline_comment_distil_like_their_webhook_twins():
    """
    Feature: A forwarded event carries the instruction, not GitHub's metadata
    Requirement: docs/specs/issue-243/requirements.md#R4

    Scenario: every comment surface the poller reads distils the same way
      Given a pull-request review and an inline review-thread comment
      When the poller synthesises each one's event
      Then the review carries its state, body and address
      And the inline comment carries its file and line ahead of its body
    """
    provider = GitHubPollProvider(repos=[], label="l")
    item = WorkItem(
        provider="github",
        owner="octo",
        repo="repo",
        number=15,
        kind="pull-request",
        title="the PR",
        url="https://github.com/octo/repo/pull/15",
        author="opener",
        raw={
            "headRef": "claude/github-issue-15",
            "body": "pr body",
            "linkedIssues": [],
        },
    )
    refs = [WorkItemRef(provider="github", owner="octo", repo="repo", number=15)]

    review = provider.comment_event(
        item,
        Comment(
            id="PRR_1",
            body="please split this function",
            author="reviewer",
            created_at="2026-08-16T16:00:00Z",
            url="https://github.com/octo/repo/pull/15#pullrequestreview-1",
            raw={"kind": "review", "state": "CHANGES_REQUESTED"},
        ),
        refs,
    )
    assert json.loads(event_excerpt(review.event, review.payload)) == {
        "review": {
            "state": "CHANGES_REQUESTED",
            "body": "please split this function",
            "html_url": "https://github.com/octo/repo/pull/15#pullrequestreview-1",
            "author": "reviewer",
        }
    }

    inline = provider.comment_event(
        item,
        Comment(
            id="PRRC_1",
            body="this loop is quadratic",
            author="reviewer",
            created_at="2026-08-16T16:01:00Z",
            url="https://github.com/octo/repo/pull/15#discussion_r1",
            raw={
                "kind": "review-thread",
                "path": "cli/the_loop/poller/poller.py",
                "line": 655,
            },
        ),
        refs,
    )
    text = event_excerpt(inline.event, inline.payload)
    assert json.loads(text)["comment"] == {
        "path": "cli/the_loop/poller/poller.py",
        "line": 655,
        "body": "this loop is quadratic",
        "html_url": "https://github.com/octo/repo/pull/15#discussion_r1",
        "author": "reviewer",
    }
    assert text.index('"path"') < text.index('"body"')


# -- T5: the gates read the payload, not the excerpt (R5) ---------------------


def test_the_gates_read_the_payload_not_the_excerpt():
    """
    Feature: A forwarded event carries the instruction, not GitHub's metadata
    Requirement: docs/specs/issue-243/requirements.md#R5

    Scenario: the gates read the payload, not the excerpt
      Given a comment whose excerpt no longer shows the sender or the issue
      When authorization, self-comment detection, control parsing and reaction
        targeting judge the event
      Then each one still decides from the full payload
      And each one decides exactly what it decided before
    """
    payload = webhook_comment_payload(body="the-loop execute", author="reviewer")
    excerpt = event_excerpt("issue_comment", payload)

    # The excerpt shows none of these — every gate reads the payload instead.
    assert "sender" not in excerpt and "node_id" not in excerpt

    assert event_actor("issue_comment", payload) == "reviewer"
    assert is_authorized("reviewer", ["reviewer"]) is True
    assert is_authorized("stranger", ["reviewer"]) is False
    assert event_body("issue_comment", payload) == "the-loop execute"
    routed = RoutedEvent(
        event="issue_comment",
        action="created",
        delivery_id="d-1",
        work_items=[WorkItemRef.parse(REF)],
        payload=payload,
    )
    assert parse_command("the-loop execute", ControlConfig()).command == "execute"
    assert target_from_event(routed) is not None

    marked = dict(payload)
    marked["comment"] = dict(payload["comment"])
    marked["comment"]["body"] = mark_self_authored("the-loop execute")
    assert is_self_authored(event_body("issue_comment", marked) or "") is True


def test_a_delivered_prompt_carries_the_instruction_and_not_the_metadata(tmp_path):
    """
    Feature: A forwarded event carries the instruction, not GitHub's metadata
    Requirement: docs/specs/issue-243/requirements.md#R1

    Scenario: what actually reaches the tmux session
      Given a live session registered against the work item
      When a comment event is dispatched to it
      Then the prompt it receives carries the comment's body and URL
      And it carries neither the issue object nor any GitHub API URL
      And it still frames the excerpt as untrusted data
    """
    tmux = FakeTmux()
    registry = SessionRegistry(tmp_path / "sessions.json")
    registry.register(
        Session(
            work_item=WorkItemRef.parse(REF),
            harness="claude",
            harness_session_id="sess-1",
            cwd=str(tmp_path),
        )
    )
    dispatcher = Dispatcher(
        registry=registry,
        adapters={"claude": StubInteractiveAdapter()},
        config=RoutingConfig(
            registry_dir=str(tmp_path),
            control=ControlConfig(require_start_command=False),
        ),
        tmux_runner=tmux,
    )
    payload = webhook_comment_payload()
    dispatcher.handle(
        RoutedEvent(
            event="issue_comment",
            action="created",
            delivery_id="d-1",
            work_items=[WorkItemRef.parse(REF)],
            payload=payload,
        )
    )
    assert wait_until(lambda: len(tmux.delivers) == 1)
    dispatcher.stop()

    _, prompt = tmux.delivers[0]
    assert INSTRUCTION in prompt
    assert "https://github.com/octo/repo/issues/15#issuecomment-98765" in prompt
    assert "UNTRUSTED" in prompt  # the framing is unchanged (R5.2)
    assert "api.github.com" not in prompt
    assert "the whole issue body" not in prompt
    assert "avatar_url" not in prompt
