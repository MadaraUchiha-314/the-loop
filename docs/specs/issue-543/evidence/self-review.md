---
type: evidence
phase: needs-review
workItem: "issue-543"
---

<!-- Written per the `the-loop:writing` skill. -->

# Self-review: PR-scoped specs for multi-PR work items

## The short version

The review took two rounds, the limit `the-loop critic policy` sets
(`selfReviewCount: 2`). Round 1 found one gap: `--still-valid` accepted any comment by an
authorized user on the PR, including one written before the chain changed. It is fixed,
test first. Round 2 found nothing new, so nothing is carried to the critic round.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | [claude/opus-5.5] | new findings | **F1. A stale declaration was accepted.** `record_pr_spec --still-valid` checked the comment's thread, its author and the loop-prevention marker, but not when it was written. An old "LGTM" on the PR could therefore be cited as the human's declaration that a *later* chain change does not affect the PR. → **will-fix, fixed.** The verb now refuses a comment that is not newer than the record it moves forward, and an unparsable time is also refused. Tests: `test_abuse_still_valid_comment_older_than_record_refused` (new, failed first); `test_verb_still_valid_rerecords_digest` and the R5 integration scenario now give a later comment. Docs: `docs/cli/commands/graph.md` § pr-spec and `reference/workflow.md` § PR specs. `design.md` is approved and unchanged: its authorization row lists three checks, and this is a fourth. It is raised in the reviewer briefing for the owner to confirm. **F2. The comment URL's host is not checked** against the configured GitHub host. → **won't-fix.** Authorization fetches the comment by repository, number and anchor from the configured API, so a foreign host cannot change what authorizes. Only the URL string in the record would carry it. | this file |
| 2 | [claude/opus-5.5] | zero (converged) | Checked with no finding: the hook re-derives applicability and recomputes the digest on every evaluation, and never trusts the record's own `required: false`. `spec-only` is honoured only for an origin-repository PR. Both inner-loop state layouts are searched. Every failure path in the verb (unread PR, wrong remote or branch, unapproved chain, unsafe path, symlinked file, missing section, unresolved or missing citation, secret shape, unread visibility, unauthorized or marked comment) records nothing. The verb writes only `pr-spec.json`. An empty `authorizedUsers` authorizes nobody. Comments under `cli/the_loop/` cite no review round. | this file |

**Known follow-up, not in scope:** `harness_routed` treats a 404 with an empty `detail`
from a daemon older than the route as an error, not a fallback to in-process. The dogfood
ran in-process (`evidence/dogfood.md`).
