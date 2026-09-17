---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#375"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review: a work item names the room it is worked in

> The `critic-review` node's proof (`reference/reviewing.md` § Running a critic round).

## Rounds

| Round | Critic | Outcome | Findings → disposition |
|-------|--------|---------|------------------------|
| 1 | — | `unavailable` | No critic is configured for this repository, and this session has no `the-loop critic` runtime attached. Recorded `unavailable`, which does **not** count toward `criticReviewCount` |

## Compensating coverage

With no critic round available, the adversarial pass was carried by the self-review
(`self-review.md`) and by a test matrix written to assert the **negative** cases rather
than only the happy path:

- **The declaration must not widen anything.** An unauthorized author declares nothing
  (T13); an unauthorized member's message in a declared room is still dropped (T8). Both
  are asserted directly, not inherited from "that file did not change".
- **Attribution must never be a guess.** A held channel is refused on write (T2, T13) and
  a contested one is attributed to nobody on read (T3) — the second being the case the
  first cannot cover, because a file can be hand-edited.
- **The undeclared path must be unchanged.** T11 asserts the central channel is still
  used and bound for a work item that declared nothing, and that the kickoff still opens
  work items in an undeclared channel; the pre-existing channel and kickoff suites run
  untouched.
- **At-most-once across both transports.** T9 (nothing from the backlog) and T10
  (processed once across three cycles) bracket the cursor change that the self-review
  names as the subtle part of this work item.

## Findings the self-review raised, and their disposition

| # | Finding | Disposition |
|---|---|---|
| 1 | The pointer message claimed replies in the moved-from thread still reached the work item; they do not | Fixed — the message, the docstring and the test now say the opposite, which is the truth |
| 2 | `declared_by` carried a parameter no caller needed | Fixed — removed |
| 3 | `post`/`open`'s "no channel id configured" refusal was no longer the whole truth | Fixed — one message naming both routes; the existing test updated with a line saying why |
