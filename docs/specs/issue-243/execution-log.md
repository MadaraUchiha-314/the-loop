---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#243"
phase: tasks-breakdown       # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a forwarded event carries the instruction, not GitHub's metadata

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner's direct instruction to complete #243 in a cloud session (see *Deviations from the standard gates*). Full process; `brainstorming` skipped — the issue names the change; `design-critic-review` not selected (`reviews.critics` is empty). |
| requirements-definition | 2026-08-16 | pending — PR | `requirements.md`. Six requirements; the ticket's second question is R6 (answer it, do not act on it). |
| design | 2026-08-16 | pending — PR | Field allow-list per container, in a new `webhook/excerpt.py`. Carries the pros/cons analysis the ticket asked for. |
| test-planning | 2026-08-16 | pending — PR | 16 rows, 8 in scope; every `n/a` carries a reason. |
| tasks-breakdown | 2026-08-16 |  | 10 tasks; three independent red roots plus an independent baseline measurement. |
| implementation |  |  |  |
| verification |  |  |  |
| needs-review |  |  |  |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| *pending* | The whole work item — the spec chain and the change. | — |

## Progress entries

### 2026-08-16 — read the render path, measured it, wrote the spec chain

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** traced what a session actually receives —
  `Dispatcher._render_prompt` (`cli/the_loop/webhook/dispatcher.py:2491`) →
  `payload_excerpt` (`:443`) → `_PAYLOAD_EXCERPT_KEYS` (`:73`) — and measured it against a
  realistic `issue_comment` webhook rather than estimating: a 61-character instruction
  arrives inside a 4,014-character excerpt that **hits the 4,000-char cap** and is chopped
  mid-string inside `issue.user.gists_url`, so the delivered JSON does not even parse.
  Confirmed the poll ingress synthesises lean payloads already
  (`poller/github.py:_item_payload`), so this is a webhook-shaped problem distilled at a
  seam both ingresses share.
- **Checkpoint/tests:** baseline suite green before any edit.
- **Next:** capture the baseline as evidence, then the red tests.
- **Blockers:** none.

## Deviations from the standard gates

Two, both stated rather than quietly taken — the same two [issue-246](../issue-246/execution-log.md)
recorded, for the same reason:

1. **`phase-selection` was not posted as a checklist and waited on.** This session was
   started by the owner directly against issue #243, in a cloud checkout with no poller
   and no daemon, so there is no ingress that could deliver the reply to such a post. The
   instruction is treated as the declaration (`the-loop execute`, default phase set,
   `brainstorming` skipped). The gate the risk tier actually turns on —
   `human-approves-pr` — is **not** bypassed.
2. **The four spec artifacts are marked `approved` in one PR** rather than approved one at
   a time, for the same reason. The reviewer approves the chain and the code together.

## Verification results

> This work item has a `testing-plan.md`, so the `verification` node records its results
> there, against the matrix rows it planned. This section stays as the template left it.

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
|                   |         | pass \| fail | link or `evidence/<file>` |

## Design critic review

> Only when this work item selected the opt-in `design-critic-review` phase (issue-188).
> Not selected: `reviews.critics` is empty in `.the-loop/harness-config.yaml`, so no
> different model is configured to read the locked design.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
|       |                             | new findings \| zero (converged) \| escalated \| unavailable | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
|       |                             |         |         |      |

## Security review (gate)

*Pending — recorded at the `needs-review` node.*

## Final validation evidence

*Pending.*

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| *pending* | | |

## Documentation

| Document | What changed |
|----------|--------------|
| *pending* | |
