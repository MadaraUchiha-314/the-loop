---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#524"
---

# Final validation: a review session receives the CI heal prompt

> The `evidence` node's proof. The spec chain was skipped by declaration, so each claim
> is taken from the issue itself. Summarised from [verification.md](verification.md) and
> [critic-review.md](critic-review.md). Full suite: 6794 passed. `pre-commit run --all-files`
> is clean.

## Final validation evidence

| What the issue asks | How it was proved | Where |
|---------------------|-------------------|-------|
| A review-loop session does not receive the "heal it … then push" section | `test_a_review_session_is_not_told_to_heal_a_check`: red with the check disabled, green with it | [verification.md](verification.md) |
| A red check seen only by a reviewer spends no CI-budget attempt | the same scenario asserts that no `ci.*` event is emitted and that the event settles as `ci-review-loop` | [verification.md](verification.md) |
| The drop is visible in the event log | `dispatch.dropped reason=ci-review-loop` is asserted per reviewer, and is in the event catalogue and the settled vocabulary | [verification.md](verification.md) |
| An authoring session on the same PR still heals | `test_a_reviewer_beside_the_author_leaves_the_heal_to_the_author` | [verification.md](verification.md) |
| It holds across a pause and a resume (critic round 1) | `test_a_paused_then_resumed_reviewer_is_still_a_reviewer`, plus the `ControlStore` carry-forward tests | [critic-review.md](critic-review.md) |
