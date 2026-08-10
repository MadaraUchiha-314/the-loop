---
type: execution-log
workItem: issue-197
phase: tasks-breakdown
status: in-progress
---

# Execution Log: the poller ignores an authorized user's control comment

> Append-only log for [#197](https://github.com/MadaraUchiha-314/the-loop/issues/197).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-10 | pending — PR gate | Risk tier 4: the change is to the prompt-injection boundary itself, so the tier is raised above the default (`autonomy.inferFromChange`) and a named human security sign-off is required before `complete` |
| design | 2026-08-10 | pending — PR gate | Three conditionals in one method, one constant prompt paragraph, one decision record |
| test-planning | 2026-08-10 | pending — PR gate | 13-row matrix, 4 abuse cases; every test runs offline against in-process doubles |
| tasks-breakdown | 2026-08-10 | pending — PR gate | 10 tasks; T1–T5 code, T6–T8 tests, T9 docs, T10 verification |
| implementation | | | |
| verification | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| _(opened at needs-review)_ | Tasks 1–10 — the whole work item | — |

## Progress entries

### 2026-08-10 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the ticket, then the code it names and the code around it:
  `poller/poller.py`, `poller/github.py`, `poller/base.py`, `authz.py`, `control.py`,
  `webhook/router.py`, `webhook/dispatcher.py` and the existing poller tests. Confirmed the
  root cause by reading, and confirmed the asymmetry the ticket implies but does not state:
  the webhook router authorizes `event_actor`, the poller authorizes `item.author`, so the
  same maintainer's comment works over one ingress and not the other. Confirmed that
  `ControlStore.start_requested` is written only by the dispatcher after a named-actor
  check, which is what makes it usable as the second half of the presence gate. Wrote and
  locked `bugfix.md` → `design.md` → `testing-plan.md` → `tasks.md`, plus
  [decision-074](../../decisions/decision-074.md).
- **Checkpoint/tests:** baseline `make test` green — 1731 passed, 1 skipped.
- **Next:** implement T1–T5, then the tests.
- **Blockers:** none.

## Documentation

_(Filled in with the user-facing documents this change made wrong, and how each was
corrected — or the reason none was.)_

## Capability docs

_(Filled in with the capability doc(s) this change belongs to.)_

## Security review

_(Filled in at `security-review`. Risk tier 4 ⇒ a named human security sign-off is required
before `complete`, per `security.review.humanSignOffMinTier`.)_
