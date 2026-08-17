---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#245"
phase: implementation        # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: channels — back-and-forth user communication, starting with a Slack bot

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-17 | @MadaraUchiha-314 | Declared by the owner filing [#245](https://github.com/MadaraUchiha-314/the-loop/issues/245) and starting this cloud session on it. The ticket states the abstraction (channels), the first provider (a Slack bot, credentials in a configurable env var), both read transports (with and without polling), the source-of-truth rule and the magic-marker rule; the owner's comment adds "Use python SDK for slack". `brainstorming` skipped (the idea is not fuzzy); `design-critic-review` not selected (no critic configured in this repository). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-17 | pending — PR for this branch | `requirements.md`: six requirements; the inbound-authorization one (R5) written in formal register — it is the contract the security review gates on. |
| design | 2026-08-17 | pending — PR for this branch | Reuse-first: the issue-64/104 marker contract for loop prevention, `reply_session`'s fail-closed delivery, the issue-242 `redact` helpers for the mirror, the self-diagnosis watcher shape for the poll transport. Six alternatives recorded as rejected. Risk tier 4 (schema touched; inbound text gains a path into sessions). |
| test-planning | 2026-08-17 | pending — PR for this branch | 13 rows, 5 in scope; every `n/a` carries a reason; T4 (live Slack) and T11 (manual) deferred with reasons — no workspace in this environment. |
| tasks-breakdown | 2026-08-17 | | 12 tasks, two independent red roots. |
| implementation | 2026-08-17 | | TDD: red captured before the code. |
| verification | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (pending) | The whole work item — the spec chain and the feature. | |

## Progress entries

### 2026-08-17 — mapped the seams before designing

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** mapped every surface the ticket touches. Outbound today is one shape:
  `integrations.slack` `post-message` (incoming webhook) fired by the graph's `notify`
  hook — write-only, unconfigurable per event. Inbound is GitHub-only: poller +
  webhook router, both dropping `SELF_COMMENT_MARKER` bodies before authz
  (issue-64/104). `the-loop ask` posts to the work item and emits
  `session.awaiting_input`; `reply_session` delivers into the tmux pane fail-closed
  (never spawns, refuses paused) and is the delivery seam a channel reply needs.
- **Found, and it decided the design:** the poller's `PollProvider` seam looks like
  the obvious inbound port but synthesises GitHub-webhook-shaped payloads — a Slack
  reply forced through it would impersonate a GitHub comment (actor semantics, authz
  and reactions all read GitHub keys). So channels got their own inbound pipeline that
  converges on the existing *reply* path instead of the *event* path.
- **Also decided:** the mirror is composed by the-loop (quoting the reply), so it may
  and must carry the marker; the reply reaches the session via `reply_session`, so the
  marker never suppresses processing — it suppresses *re*-processing. That is the
  ticket's "not processed twice" rule, implemented with zero new marker machinery.

## Deviations from the standard gates

- **`phase-selection` was answered by direct instruction, not by the checklist
  comment.** This work started from the owner's cloud-session request on the ticket
  rather than from `the-loop start`, so no checklist was posted and no
  `the-loop execute` reply exists. The owner's filed ticket is the authorization; the
  spec chain exists in full rather than being skipped.
- **The artifacts are `in-review`, not `approved`.** Nothing here has been through a
  human gate yet; the pull request carries the whole chain for review in one place. No
  phase claims an approval it does not have.
- **Risk tier 4 without a pre-implementation spec approval.** `autonomy.tiers["4"]` is
  `human-approves-pr`, so the gate this work needs is the PR itself — and
  `security.review.humanSignOffMinTier: 4` also applies: the PR briefing explicitly
  requests a named human security sign-off on the inbound-authorization and
  loop-prevention contracts (R4.5, R5.1, R1.3).
- **No `loop:<phase>` label on #245 from the harness** — the known #73 gap: a cloud
  session has no daemon. The phase state is this file.

## Capability docs

> Completed at the capability-docs gate — see the entries added with the change.

## Documentation

> Completed at the capability-docs gate — see the entries added with the change.
