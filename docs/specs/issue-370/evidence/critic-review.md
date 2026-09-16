---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#370"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review: a pull request is tracked because the-loop recorded it

> The `critic-review` node's proof — a different model/harness reading the diff.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | — | **unavailable** | `.the-loop/cli-config.yaml` declares `critics: []`, so `the-loop critic run` has no roster to run. The only harness binary on this machine is `claude` — the one already used for the self-review rounds, and a model reviewing its own diff is a second self-review, not a critic round. Does not count toward `reviews.criticReviewCount` | — |

## What stands in for it

Per `reference/reviewing.md`, an `unavailable` round is recorded with its cause and the
work item escalates to the human reviewer rather than counting a round it did not run. The
risk tier is 3 (`human-approves-pr`), so this work item was always going to a human before
completing; the critic round's absence changes what the reviewer is asked to weigh, not
whether they are asked.

The two self-review rounds are in `self-review.md`, and the specific thing a critic would
most usefully attack — the tracking/delivery boundary — is stated as a decision
([decision-129](../../decisions/decision-129.md)) with its rejected alternatives, rather
than buried in a diff.
