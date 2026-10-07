---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Security review: Jira as a first-class work-item source and update channel (issue-475)

## Security review (gate)

- **Outcome: pass. No findings, and all eight checklist items pass.** This is risk tier 4:
  the change adds a Jira credential, an inbound webhook route, a second ref grammar, and
  changes to the config schema. A **named human sign-off is required** before the work item
  completes (see *Sign-off* below).
- **Mechanism:**
  - Claude Code's built-in `security-review` skill, run against
    `origin/main...feat/issue-475-jira-5-edges` after both self-review rounds and the critic
    round were fixed. It traced each untrusted Jira input into sensitive code: webhook
    authentication, JQL, file paths and URLs, who wrote a marker, which host credentials go
    to, logging, deserialization and rendered output. It reported *"No HIGH- or
    MEDIUM-confidence vulnerability is introduced by this diff."*
  - the-loop's checklist (`reference/security.md`), each item checked against the diff.
- **Earlier security-relevant findings, all fixed before this round:**
  - self-review R2-4: any Jira user could plant a phase-selection checklist;
  - critic C1: a checklist could be planted through mirrored or quoted content;
  - self-review L1: the visible marker was also matched on GitHub bodies;
  - self-review M1: a control comment could execute twice.

  See `self-review.md` and `critic-review.md`.

### Checklist

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Each trust boundary in `design.md` §Security design is enforced | pass | **Webhook → receiver:** the route exists only with a secret, and HMAC-SHA256 is checked with `compare_digest` before parsing (`webhook/server.py`). The doorbell reads 3 fields and re-fetches the rest. **Jira data → router:** `authz.jira_comment_origin`, `is_authorized_on`. **Ticket text → prompt:** the "UNTRUSTED data" frame. **Config → JQL:** `jql_string` plus the key grammar. **PR → linkage:** the mapped repository plus a registered ref. **Secrets:** `server()` comes from config only, and redaction is in `jiraapi.py`. |
| 2 | Untrusted inputs are validated at ingress, and injection surfaces are covered | pass | Grammars for issue and project keys; digit-only comment and transition ids; refs cannot contain `..`; no ticket value reaches JQL; spoofed markers are neutralised (`jiraformat.literal_markers`, `channels/jira.jira_ledger_body`). |
| 3 | Untrusted content cannot steer privileged behaviour | pass | A relay counts only from the service account carrying the relay marker. Gate markers count only in the service account's own top-level paragraphs. Gate authors are `jira:<id>`, which no GitHub login can spell. Tests: `test_relay_marker_from_other_user_grants_nothing`, `test_a_jira_user_cannot_plant_a_phase_selection_checklist` (×3), `test_a_mirrored_snapshot_carrying_a_gate_marker_is_not_a_checklist` (×12). |
| 4 | No secrets in code, config, logs, fixtures or evidence | pass | A pattern scan (Atlassian, GitHub, Slack and OpenAI tokens, auth headers, emails) over `docs/specs/issue-475/**` (including `evidence/jira/*`), the fixtures and the configs found only `xoxb-` placeholders in config comments. `test_jira_errors_and_logs_carry_no_secret` passes. |
| 5 | AuthZ fails closed | pass | A missing actor is denied. A failed `myself` lookup means no relay is trusted. No secret means no route. An unknown site or project raises `UnknownJiraProject` before any request. Partial credentials raise `JiraApiError`. |
| 6 | Least privilege | pass | The documented scopes are `read:jira-work`, `write:jira-work`, and `read:jira-user` (for `myself` only); no admin scope is needed. Credentials go only to the configured site or gateway, and response `next`/`self` links are not followed for paging. The GitHub path gains nothing, and GitHub deliveries carrying `x-the-loop-provider` are dropped. |
| 7 | Every abuse case has a passing negative test | pass | 41 passed: the T7 tests for abuse cases 1–10, plus the three negatives added in review. |
| 8 | New dependencies are justified and from trusted sources | pass | `jira>=3.10,<4` and `markdown-it-py>=3,<5` are justified in design §Trade-offs. They and their transitive packages (`defusedxml`, `mdurl`, `oauthlib`, `requests-oauthlib`, `requests-toolbelt`) come from PyPI, with sha256 hashes in `uv.lock`. |

### Findings

None. Two notes fall below the reporting bar and need no action:

- `_ISSUE_KEY_RE` accepts a trailing newline. Its inputs are stripped, or come from the
  configured server.
- `isdigit()` accepts Unicode digits in a comment id. The value only reaches a URL path on
  the configured host.

### Residual risks the signer accepts

1. **The GitHub phase-selection marker can be typed by anyone.** This predates this work
   and is proposed as a follow-up. The Jira-side fix does not change GitHub.
2. **Jira ticket descriptions** turn markers into gate markers whoever wrote them
   (pre-existing; follow-up). No gate reads markers from a description today.
3. **The service account's token anchors relay trust.** Anyone who holds it, or a Jira
   admin able to post as that account, can write relays that count as authorized gate
   answers. The account must be dedicated and tightly held.
4. **The webhook is protected by an HMAC over a shared secret, with no replay window.** A
   captured, signed delivery can be replayed. It carries only ids, which are re-fetched,
   and comment-id deduplication limits the effect.
5. **The SDK's `issue.update` follows the issue's `self` link.** That link comes from the
   configured server, so credentials stay on that host only while the Jira instance is
   trusted.
6. **Token redaction in the third-party SDK's logs relies on one logger filter.** Re-run
   `test_jira_errors_and_logs_carry_no_secret` whenever the `jira` dependency is upgraded.

### Sign-off

**Pending.** Tier 4 requires a named human sign-off on this review, separate from the PR
approval. The request is on [#475](https://github.com/MadaraUchiha-314/the-loop/issues/475).
