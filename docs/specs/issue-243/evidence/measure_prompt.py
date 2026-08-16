"""Measure what a session actually receives for one ordinary comment (issue-243).

Renders the shipped event-prompt template for a realistic ``issue_comment`` webhook
payload — the shape GitHub documents, with its two ``user`` objects, its ``reactions``
blocks, its label objects and the whole ``issue`` — and reports how much of the delivered
prompt is the instruction and how much is metadata.

Run from the repository root, before and after the change:

    uv run python docs/specs/issue-243/evidence/measure_prompt.py

Committed as evidence, not as a test: it measures cost, and cost is a number to read in a
review, never a gate to fail a build on.
"""

from __future__ import annotations

import json
from string import Template

from the_loop.interaction import directive_for
from the_loop.webhook import dispatcher

INSTRUCTION = "the-loop execute\n\nPlease keep the anchor for inline comments."

GRAPH_CONTEXT = (
    "the-loop process state for github:o/r#243:\n"
    "  node: implementation (phase: implementation) — status: in-progress\n"
    "  resume with: `/the-loop:execute-tasks github:o/r#243`\n"
    "  iterate the outer loop's artifacts on: this work item\n"
    "  when this node's work is done, run: `the-loop graph complete github:o/r#243`\n"
    "  (this block is the-loop's own state, not part of the event payload)"
)


def user(login: str = "octocat", uid: int = 583231) -> dict:
    """A GitHub ``user`` object, with every URL field GitHub sends."""
    return {
        "login": login,
        "id": uid,
        "node_id": "MDQ6VXNlcjU4MzIzMQ==",
        "avatar_url": f"https://avatars.githubusercontent.com/u/{uid}?v=4",
        "gravatar_id": "",
        "url": f"https://api.github.com/users/{login}",
        "html_url": f"https://github.com/{login}",
        "followers_url": f"https://api.github.com/users/{login}/followers",
        "following_url": f"https://api.github.com/users/{login}/following{{/other_user}}",
        "gists_url": f"https://api.github.com/users/{login}/gists{{/gist_id}}",
        "starred_url": f"https://api.github.com/users/{login}/starred{{/owner}}{{/repo}}",
        "subscriptions_url": f"https://api.github.com/users/{login}/subscriptions",
        "organizations_url": f"https://api.github.com/users/{login}/orgs",
        "repos_url": f"https://api.github.com/users/{login}/repos",
        "events_url": f"https://api.github.com/users/{login}/events{{/privacy}}",
        "received_events_url": f"https://api.github.com/users/{login}/received_events",
        "type": "User",
        "user_view_type": "public",
        "site_admin": False,
    }


def reactions(target: str) -> dict:
    return {
        "url": f"https://api.github.com/repos/o/r/{target}/reactions",
        "total_count": 0,
        "+1": 0,
        "-1": 0,
        "laugh": 0,
        "hooray": 0,
        "confused": 0,
        "heart": 0,
        "rocket": 0,
        "eyes": 0,
    }


def issue_comment_payload() -> dict:
    """A realistic ``issue_comment`` webhook payload for issue #243 itself."""
    return {
        "action": "created",
        "issue": {
            "url": "https://api.github.com/repos/o/r/issues/243",
            "repository_url": "https://api.github.com/repos/o/r",
            "labels_url": "https://api.github.com/repos/o/r/issues/243/labels{/name}",
            "comments_url": "https://api.github.com/repos/o/r/issues/243/comments",
            "events_url": "https://api.github.com/repos/o/r/issues/243/events",
            "html_url": "https://github.com/o/r/issues/243",
            "id": 3456789012,
            "node_id": "I_kwDOAAA",
            "number": 243,
            "title": "optimize tokens by stripping out meta-data",
            "user": user(),
            "labels": [
                {
                    "id": 1,
                    "node_id": "LA_1",
                    "url": "https://api.github.com/repos/o/r/labels/loop:implementation",
                    "name": "loop:implementation",
                    "color": "ededed",
                    "default": False,
                    "description": None,
                },
                {
                    "id": 2,
                    "node_id": "LA_2",
                    "url": "https://api.github.com/repos/o/r/labels/enhancement",
                    "name": "enhancement",
                    "color": "a2eeef",
                    "default": True,
                    "description": "New feature or request",
                },
            ],
            "state": "open",
            "locked": False,
            "assignee": None,
            "assignees": [],
            "milestone": None,
            "comments": 3,
            "created_at": "2026-08-16T15:42:52Z",
            "updated_at": "2026-08-16T16:02:10Z",
            "closed_at": None,
            "author_association": "OWNER",
            "active_lock_reason": None,
            "sub_issues_summary": {"total": 0, "completed": 0, "percent_completed": 0},
            "body": (
                "- When any comment is posted on the work item (gh issue or jira) or "
                "the PR then the-loop forwards the entire payload that it receives "
                "which includes a lot of meta-data to the tmux session\n"
                "- This is not required\n"
                "- A comment just needs a body of the comment and the URL of the "
                "comment\n"
            ),
            "reactions": reactions("issues/243"),
            "timeline_url": "https://api.github.com/repos/o/r/issues/243/timeline",
            "performed_via_github_app": None,
            "state_reason": None,
        },
        "comment": {
            "url": "https://api.github.com/repos/o/r/issues/comments/9876543210",
            "html_url": "https://github.com/o/r/issues/243#issuecomment-9876543210",
            "issue_url": "https://api.github.com/repos/o/r/issues/243",
            "id": 9876543210,
            "node_id": "IC_kwDOAAA",
            "user": user("reviewer", 42),
            "created_at": "2026-08-16T16:02:10Z",
            "updated_at": "2026-08-16T16:02:10Z",
            "author_association": "OWNER",
            "body": INSTRUCTION,
            "reactions": reactions("issues/comments/9876543210"),
            "performed_via_github_app": None,
        },
        "repository": {"full_name": "o/r", "html_url": "https://github.com/o/r"},
        "sender": user("reviewer", 42),
    }


def excerpt_for(event: str, payload: dict) -> str:
    """The excerpt this tree produces — either signature, so one script measures both."""
    distil = getattr(dispatcher, "event_excerpt", None)
    if distil is not None:  # post-change: distilled per event (issue-243)
        return distil(event, payload)
    return dispatcher.payload_excerpt(payload)  # pre-change: container subset


def main() -> None:
    payload = issue_comment_payload()
    excerpt = excerpt_for("issue_comment", payload)
    prompt = Template(dispatcher.DEFAULT_PROMPT_TEMPLATE).safe_substitute(
        work_item="github:o/r#243",
        event="issue_comment",
        action="created",
        repository="o/r",
        delivery_id="abc-123",
        payload_excerpt=excerpt,
        interaction_directive=directive_for("work-item"),
        graph_context=GRAPH_CONTEXT,
    )
    raw = json.dumps(payload, indent=2)
    constant = len(prompt) - len(excerpt) - len(GRAPH_CONTEXT)
    try:
        json.loads(excerpt)
        parses = "yes"
    except json.JSONDecodeError as exc:
        parses = f"NO — {exc.msg} at char {exc.pos}"

    print(f"the-loop version          : {dispatcher.__name__} @ tree under test")
    print(f"raw webhook payload       : {len(raw):6d} chars")
    print(f"payload excerpt delivered : {len(excerpt):6d} chars")
    print(f"  parses as JSON          : {parses}")
    print(f"  truncated               : {'… (truncated)' in excerpt}")
    print(f"whole rendered prompt     : {len(prompt):6d} chars")
    print(f"  the instruction itself  : {len(INSTRUCTION):6d} chars")
    print(f"  the-loop constant text  : {constant:6d} chars")
    print(f"  graph context           : {len(GRAPH_CONTEXT):6d} chars")
    print()
    print("---- the excerpt as delivered ----")
    print(excerpt)


if __name__ == "__main__":
    main()
