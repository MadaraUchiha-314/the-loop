---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#381"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review: a work item is armed by a set of labels, all of which must be present

> The `critic-review` node's proof (`reference/reviewing.md` § Running a critic round).

## Rounds

| Round | Critic | Outcome | Findings → disposition |
|-------|--------|---------|------------------------|
| 1 | — | `unavailable` | `the-loop critic list` answers *No critics configured* for this repository, and this session has no critic harness attached. Recorded `unavailable`, which does **not** count toward `criticReviewCount` (policy: 3 self, 3 critic, stop on no new findings) |

## Compensating coverage

With no critic round available, the adversarial pass was carried by the self-review
(`self-review.md`) and by tests written for the cases that would embarrass the design:

- **The vacuous truth.** `test_an_empty_label_list_arms_nothing` — the one input on
  which `all()` gives the wrong answer.
- **The wrong label being added.** `test_event_carries_labels_counts_the_label_being_added`
  asserts both directions: the last missing label arms, another label does not.
- **A listing that returns too much.** `test_provider_drops_a_listed_item_missing_one_label`
  proves R2.1 without trusting `gh`.
- **Both ingresses, end to end.** `Scenario: an item carrying only some of the labels is
  not armed`, `Scenario: adding the last missing label spawns a session`, `Scenario: the
  poller drops a listed item missing one label`.
- **The migration both ways.** Refusal of each old key, the wrap, the empty source label,
  the empty routing label, the half-migrated file, idempotence, and a `jira` source's
  `label` left alone.
