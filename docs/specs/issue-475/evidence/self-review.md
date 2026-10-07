---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#475"
---

# Self-review: Jira as a first-class work-item source and update channel (issue-475)

> **Two rounds, the operator's cap (`selfReviewCount: 2`). Thirteen findings, every one fixed
> or disclosed. One out-of-scope follow-up is proposed.** Each round was a fresh, read-only
> `claude/opus-5.5` reviewer over the whole stack (`git diff origin/main...feat/issue-475-jira-5-edges`),
> checking the code against the locked spec. The findings and their dispositions are posted
> on [#480](https://github.com/MadaraUchiha-314/the-loop/pull/480): round 1 at
> [issuecomment-6041103486](https://github.com/MadaraUchiha-314/the-loop/pull/480#issuecomment-6041103486)
> with its fixes at [issuecomment-6041552904](https://github.com/MadaraUchiha-314/the-loop/pull/480#issuecomment-6041552904),
> and round 2 at [issuecomment-6041660539](https://github.com/MadaraUchiha-314/the-loop/pull/480#issuecomment-6041660539).
> The fixes are on the top branch, one commit per finding, each with a test that failed first.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | `claude/opus-5.5` (whole stack: security first, then GitHub regression, Jira correctness, design departures) | 9 new | **H1** a Jira event had no repository, so no worktree was made → `103ba9b`. **M1** a control comment could run twice across webhook and poller → `9dd8aad` (persisted `control-deliveries.json`). **M2** stale cached service-account id → `1911566`. **L1** the visible marker also matched GitHub bodies → `ab41331`. **L2** the doorbell followed a moved ticket → `657087b`. **L3** the doorbell was not rebuilt on hot reload → `813cfbb`. **L4** `UnknownJiraProject` on close paths → `e5714f1`. **L5** four wiki ⇄ Markdown edge cases → `30b1dd3`. **L6** undisclosed stricter arming → disclosed on #479, code kept. |
| 2 | `claude/opus-5.5` (verify round-1 fixes; schema, migration, tickets, Slack→Jira, ADF edges) | 4 new | **R2-1** a migrated Jira stub failed the schema and blocked config writes → `866b348`. **R2-2** the M1 claim blocked a retry after a failed spawn → `0565547`. **R2-3** the ADF reader crashed on malformed nodes and dropped media → `9b99514`. **R2-4 (security)** any Jira user could plant a phase-selection checklist via the visible marker → `23e68ea`, which only lets the service account's comments carry gate markers. Nit: misleading `_announce` comments → corrected in `23e68ea`. |

The round-1 fixes were re-checked in round 2 and hold:

- The M1 store uses a `flock`, an atomic replace and a 256-id bound, and a corrupt file reads as empty.
- H1 is covered on every spawn and close path.
- L1: every Jira call site passes the provider.

After round 2's fixes, the full gate passed: 6004 tests, ruff, pyright, markdownlint and the config schema.

## Checked clean (no findings)

- **Webhook:** the HMAC is checked before parsing, the route is absent without a secret, and only three fields are read.
- **Event flag:** a GitHub delivery cannot use `x-the-loop-provider`.
- **Identities:** the `jira:<id>` namespace holds at every authorization site (router, dispatcher, poller, in-daemon gate, CLI gate).
- **Relays:** trusted only from the service account, and a failed `myself` lookup fails closed.
- **Abuse cases:** JQL quoting and key grammar; the credential-host check before any request; secret scrubbing.
- **Linkage:** branch name and title only, the mapped repository only, a registered work item only.
- **Transitions:** zero or several candidates is refused.
- **Config schema:** the new validator keywords hold against the real schema, and GitHub-only configs are unaffected.
- **Migration:** idempotent.
- **`JiraTickets`:** the project allow-list, and `_authority` before closing.
- **Slack → Jira:** relays only for relayed event types, and `add-channel jira@` is limited to configured projects.

## Out of scope: proposed follow-up

- **GitHub variant of R2-4.** `graph/hooks/selection.py` `_checklist_state` trusts the newest comment carrying the phase-selection marker without checking its author. On GitHub anyone can type the hidden marker, so the gap predates this stack. Fixing it changes GitHub behaviour, so it belongs in its own issue.
- **Jira descriptions.** Ticket descriptions are still read with marker conversion for any author. No gate reads markers from a description today, so the follow-up should cover descriptions too.
