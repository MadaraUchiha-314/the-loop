# Baseline: what a session receives for one ordinary comment

Captured **before** any change of this work item, on `68570a6` (v10.2.2), for testing-plan
row **T8**.

## Command

```console
$ uv run python docs/specs/issue-243/evidence/measure_prompt.py
```

## Output

```text
the-loop version          : the_loop.webhook.dispatcher @ tree under test
raw webhook payload       :   6335 chars
payload excerpt delivered :   4014 chars
  parses as JSON          : NO — Invalid control character at at char 4000
  truncated               : True
whole rendered prompt     :   6676 chars
  the instruction itself  :     61 chars
  the-loop constant text  :   2290 chars
  graph context           :    372 chars

---- the excerpt as delivered ----
{
  "action": "created",
  "sender": {
    "login": "reviewer",
    "id": 42,
    "node_id": "MDQ6VXNlcjU4MzIzMQ==",
    "avatar_url": "https://avatars.githubusercontent.com/u/42?v=4",
    "gravatar_id": "",
    "url": "https://api.github.com/users/reviewer",
    "html_url": "https://github.com/reviewer",
    "followers_url": "https://api.github.com/users/reviewer/followers",
    "following_url": "https://api.github.com/users/reviewer/following{/other_user}",
    "gists_url": "https://api.github.com/users/reviewer/gists{/gist_id}",
    "starred_url": "https://api.github.com/users/reviewer/starred{/owner}{/repo}",
    "subscriptions_url": "https://api.github.com/users/reviewer/subscriptions",
    "organizations_url": "https://api.github.com/users/reviewer/orgs",
    "repos_url": "https://api.github.com/users/reviewer/repos",
    "events_url": "https://api.github.com/users/reviewer/events{/privacy}",
    "received_events_url": "https://api.github.com/users/reviewer/received_events",
    "type": "User",
    "user_view_type": "public",
    "site_admin": false
  },
  "comment": {
    "url": "https://api.github.com/repos/o/r/issues/comments/9876543210",
    "html_url": "https://github.com/o/r/issues/243#issuecomment-9876543210",
    "issue_url": "https://api.github.com/repos/o/r/issues/243",
    "id": 9876543210,
    "node_id": "IC_kwDOAAA",
    "user": {
      "login": "reviewer",
      "id": 42,
      "node_id": "MDQ6VXNlcjU4MzIzMQ==",
      "avatar_url": "https://avatars.githubusercontent.com/u/42?v=4",
      "gravatar_id": "",
      "url": "https://api.github.com/users/reviewer",
      "html_url": "https://github.com/reviewer",
      "followers_url": "https://api.github.com/users/reviewer/followers",
      "following_url": "https://api.github.com/users/reviewer/following{/other_user}",
      "gists_url": "https://api.github.com/users/reviewer/gists{/gist_id}",
      "starred_url": "https://api.github.com/users/reviewer/starred{/owner}{/repo}",
      "subscriptions_url": "https://api.github.com/users/reviewer/subscriptions",
      "organizations_url": "https://api.github.com/users/reviewer/orgs",
      "repos_url": "https://api.github.com/users/reviewer/repos",
      "events_url": "https://api.github.com/users/reviewer/events{/privacy}",
      "received_events_url": "https://api.github.com/users/reviewer/received_events",
      "type": "User",
      "user_view_type": "public",
      "site_admin": false
    },
    "created_at": "2026-08-16T16:02:10Z",
    "updated_at": "2026-08-16T16:02:10Z",
    "author_association": "OWNER",
    "body": "the-loop execute\n\nPlease keep the anchor for inline comments.",
    "reactions": {
      "url": "https://api.github.com/repos/o/r/issues/comments/9876543210/reactions",
      "total_count": 0,
      "+1": 0,
      "-1": 0,
      "laugh": 0,
      "hooray": 0,
      "confused": 0,
      "heart": 0,
      "rocket": 0,
      "eyes": 0
    },
    "performed_via_github_app": null
  },
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
    "user": {
      "login": "octocat",
      "id": 583231,
      "node_id": "MDQ6VXNlcjU4MzIzMQ==",
      "avatar_url": "https://avatars.githubusercontent.com/u/583231?v=4",
      "gravatar_id": "",
      "url": "https://api.github.com/users/octocat",
      "html_url": "https://github.com/octocat",
      "followers_url": "https://api.github.com/users/octocat/followers",
      "following_url": "https://api.github.com/users/octocat/following{/other_user}",
      "gists_url": "https://api.gith
… (truncated)
```

## What this says

| Part of the delivered prompt | Chars | Share |
|---|---:|---:|
| The instruction itself (`comment.body`) | 61 | 0.9% |
| The rest of the payload excerpt | 3,953 | 59.2% |
| the-loop's own constant text (template shell + interaction directive) | 2,290 | 34.3% |
| Graph context (this item's live process state) | 372 | 5.6% |
| **Whole delivered prompt** | **6,676** | 100% |

Two facts the numbers make concrete:

1. **The excerpt hit its 4,000-character cap on an ordinary comment**, and the cut landed
   inside `issue.user.gists_url` — so the delivered "JSON" does not parse
   (`Invalid control character at char 4000`). Everything after that point, including the
   whole tail of the `issue` object, was noise the session paid for and could not read.
2. **The instruction was 0.9% of what was delivered.** The remaining 59% of the excerpt is
   two `user` objects (18 API URLs each), two `reactions` blocks, the label objects, and
   the `issue` object the comment's own URL already identifies.
