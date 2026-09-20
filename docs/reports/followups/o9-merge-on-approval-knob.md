# A config knob for what a PR approval does: "may merge" vs "merged"

**Kind:** enhancement · **Source:** e2e Slack test 2026-09-19 (O9) · **Not fixed in issue-393**

## What was seen

After a Slack "approved" satisfied `human-approval`, the session merged PR #<n>
within 21 seconds and closed the issue, with **zero** GitHub reviews on the PR.
The Slack "approved" was the human PR approval the tier requires, so this is
consistent with the tier rules — but:

- a repository with branch protection would have **refused** the merge; and
- some teams will want "approved" to mean "you may merge" rather than "merged
  now".

## Suggested change (from the report)

A config knob, or at least a line in the approval request saying what approving
will do:
- an option where `human-approval` means "the-loop may merge" (it merges) vs.
  "the human will merge" (the-loop stops at approved and leaves the merge to a
  person / branch protection); and/or
- the approval request message stating plainly, before the tap, that approving
  will merge and close.

## Acceptance

- An operator can configure whether an approval merges the PR or only marks it
  approved, and the approval request says which behaviour is in effect; branch
  protection is respected rather than hit as a surprise.

## Note

Lower priority than the bugs — current behaviour is *correct per the tier rules*,
this is about making the consequence explicit and configurable.
