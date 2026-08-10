---
type: execution-log
workItem: issue-197
phase: needs-review
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
| implementation | 2026-08-10 | — | T1–T9 complete, plus four unplanned changes recorded in `tasks.md` |
| verification | 2026-08-10 | — | Every applicable row executed; see `testing-plan.md` § Verification results |
| needs-review | 2026-08-10 | pending | Self-review done (three rounds, two findings fixed); the human gate is the PR |
| complete | | | Risk tier 4 — needs a named human security sign-off as well as PR approval |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#198](https://github.com/MadaraUchiha-314/the-loop/pull/198) (this repository) | Tasks 1–10 — the whole work item | open |

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

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** T1–T9. `spawn_authorized` in `_process_item` (the item's author **or**
  `ControlStore.start_requested`), `_pending_control_ids` asked unconditionally, the
  candidate loop's `item_authorized` wrapper removed, the withheld-spawn warning rewritten
  to name the remedy and to fire only while something is withheld, and the untrusted
  work-item paragraph added to both copies of the spawn prompt. Then the tests: nine unit
  (including the four abuse cases), two Gherkin integration scenarios through the real
  dispatcher, one template-parity assertion, and one rewritten test that had asserted the
  bug.
- **Checkpoint/tests:** `make check` green.
- **Next:** self-review, then verification.
- **Blockers:** none.

### 2026-08-10 — self-review and verification

- **Phase:** implementation → verification → needs-review
- **Did:** Three self-review rounds over the diff. Round 1 found the two findings that
  mattered. The first: the new warning interpolated `control.keyword("start")` with no
  regard for `control.enabled` or for a keyword an operator disabled with an empty string,
  so the remedy it named could be `commenting '' on it` — it now names
  `the-loop sessions start` in exactly those cases, which works with control disabled
  because `core/sessions.py` records the arming command regardless of the keyword config.
  The second: `poll.unauthorized`'s entry in `eventlog.EVENT_TYPES` still said the item
  "was ignored", which after this change is the opposite of what happens to its comments.
  Round 2 walked the surrounding decisions: `spawn_authorized` short-circuits, so the extra
  control-record read only happens for an item whose author is unauthorized; a PR linked to
  an armed issue is unaffected (it matches by session, and `_awaiting_start` already keys on
  the item's own ref); and an unreadable control store reads as "nothing recorded", which is
  the closed direction. Round 3 found nothing new, which is the stop condition. Then
  executed the testing plan and committed the evidence.
- **Checkpoint/tests:** `make check` green — 1742 passed, 1 skipped, 0 lint/format/pyright
  findings. Red→green confirmed: 8 of the 13 selected tests fail against the pre-fix source.
- **Next:** the PR briefing, then human review.
- **Blockers:** none.

## Documentation

Four user-facing documents stated the rule this change replaces, and all four ship with it:

- **`docs/cli/commands/poll.md`** — the *Guards* block said "the poller spawns only for
  items authored by a login in `authorizedUsers`, and forwards only comments from
  authorized authors", which was the bug written down as a feature. It now separates the
  two: comments are judged by their own author, and the item's author gates only whether
  the poller starts work by itself.
- **`docs/cli/concepts.md`** — § Guards is the page both ingresses link to for the trust
  model, so it now says the authorized actor is whoever performed the action, and names the
  one poll-path exception.
- **`docs/config/cli/routing-options.md`** — `authorizedUsers`' danger block said "items
  authored by anyone not listed are ignored"; it now says which decision the item's author
  actually reaches, and how to arm such an item.
- **`skills/the-loop/templates/cli-config.yaml`** — the security comment beside
  `authorizedUsers` is what an operator reads while configuring the daemon, and it carried
  the same claim.

`README.md` and the skill's `reference/` docs needed **no** change: nothing about the
operating model, the phases, the artifacts or the commands moved — only which actor one
guard reads, on one ingress. `reference/automation.md` describes the control keywords and
`authorizedUsers` correctly at the level it describes them.

## Capability docs

- **[`webhook-triggers`](../../capabilities/webhook-triggers.md)** — the capability this
  change belongs to (both ingresses and their guards). New behaviour statement covering the
  spawn gate, the comment rule and the prompt framing, plus a history row.

No other capability doc is affected: no schema, no config key, no state-file shape and no
API contract changed, and the control-plane surface is untouched.

## Security review

Filled in at `security-review`. Risk tier 4 ⇒ a named human security sign-off is required
before `complete`, per `security.review.humanSignOffMinTier`.
