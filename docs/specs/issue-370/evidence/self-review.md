---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#370"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: a pull request is tracked because the-loop recorded it

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `claude/claude-opus-5` (self) | new findings | 3 found, 3 fixed — see below | this file |
| 2 | `claude/claude-opus-5` (self) | zero (converged) | re-read of the same diff after the round-1 fixes surfaced nothing new | this file |

## Round 1 findings

1. **`--dry-run` was matched as a substring of the whole command**, so
   `gh pr create --title "support --dry-run"` would have been silently skipped and the
   pull request left unrecorded — the exact failure mode this hook exists to remove.
   *Fixed:* `_DRY_RUN_RE` matches it as a flag (`(?:^|\s)--dry-run(?:[\s=]|$)`), with a
   test asserting a title containing the text still links.
2. **A leak of the removed inference back into the review pre-fill, unstated.** Delivery
   routing is deliberately untouched, so an event for an inference-linked pull request
   still creates `pr-loops/pr-<n>/` under the work item's spec directory, and
   `_state_pulls` then suggests it. This is defensible — a directory means the-loop ran an
   inner loop for that pull request, which is something the-loop did — but leaving it
   undisclosed would have made the design's claim broader than the code's.
   *Fixed:* stated in `design.md` § C3 as a known consequence, with the one-line change
   that would close it if the owner wants it closed.
3. **`requirements.md` R6.1 named `docs/capabilities/review-loop.md`**, which describes
   none of the changed behaviour — an invitation to edit a document for the sake of the
   checklist. *Fixed:* R6.1 names the four capability docs and two user-facing pages that
   actually changed, and says an unaffected doc is recorded with its reason instead.

## What was checked and found sound

- **The removal is at the tracking seam only.** `provider.refs` still runs and still feeds
  delivery and closure reconciliation; only `_resolve_owner` stopped reading it. The
  integration scenario (`test_an_inferred_pull_request_is_delivered_but_never_tracked`)
  asserts both halves in one run.
- **No migration is silently performed.** Question 2 of `_resolve_owner` (the existing
  portable ledger) is unchanged and answers before anything else, so an upgrade re-files
  nothing.
- **`linkedBy: "event"` still round-trips.** `PR_LINKED_BY` keeps both names as the read
  vocabulary; only the writers narrowed.
- **The hook cannot reach a shell.** argv lists throughout, `shell=True` absent and
  asserted absent, every extracted coordinate validated against GitHub's name shape before
  it reaches an argument, both subprocesses bounded by a timeout.
- **The hook cannot block a session.** Every path returns 0; the failure test asserts a
  non-zero `link-pr` is silent rather than an exit 2.
