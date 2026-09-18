---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#378"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review: a work item's whole life is told to every channel, and Slack can begin one

> The `critic-review` node's proof (`reference/reviewing.md` § Running a critic round).

## Rounds

| Round | Critic | Outcome | Findings → disposition |
|-------|--------|---------|------------------------|
| 1 | — | `unavailable` | No critic is configured for this repository (`critics: []`), and this session has no `the-loop critic` runtime attached. Recorded `unavailable`, which does **not** count toward `criticReviewCount` |

## Compensating coverage

With no critic round available, the adversarial pass was carried by the self-review
(`self-review.md`) and by tests written for the cases that would embarrass the design:

- **The label rule, not the node rule.** `test_two_nodes_sharing_a_phase_publish_nothing_between_them`
  walks `author → approve → design` and asserts silence on the first edge and a
  completion of the *inherited* phase on the second — the case the first draft failed.
- **The ordering the closure depends on.** The fake lifecycle publisher records what the
  declaration store said *at the moment of the call*, so `declared == [ROOM]` then
  `list(ref) == []` after is a property of the code path, not of the test's setup.
- **A provider the-loop does not ship.** T18 registers a fake type, configures no Slack,
  and asserts the runtime's `phase.started` reached it — the one test that proves R6 rather
  than restates it.
- **Every refusal of the kickoff, through the verb.** Four parametrised refusals plus the
  grant, the allow-list and the duplicate trigger, each asserting nothing was created.
- **The one gate that could go quiet.** T5 pins that every human node of the outer loop
  carries a phase or a `notify` hook, so a future gate cannot park in silence.
