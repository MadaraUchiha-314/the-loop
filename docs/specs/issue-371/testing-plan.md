---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#371"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: every comment the-loop finishes with says so on the comment

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials or the network: every row drives the real
> `Dispatcher` with a real `GitHubReactor` whose `gh` invocation is captured by a fake
> runner, which is how issue-84's own tests prove what is posted and on which entity.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `ACK_STATES` maps exactly the outcomes R1.3 names, to the states it names, and no scope refusal has an entry; every key is a member of `SETTLED_OUTCOMES` (R1.2, R1.3) | `cli/tests/test_reactions.py` |
| T2 | Integration | yes | **the reported bug**: `the-loop add-collaborator @someone` in a comment from an authorized user posts 🎉 on that comment, and the roster is written (R1.1, AC1) | `cli/tests/test_reactions_integration.py` |
| T3 | Integration | yes | an executed session command (`the-loop pause`) posts 🎉 on the comment (R1.1, R1.3) | `cli/tests/test_reactions_integration.py` |
| T4 | Integration | yes | a refused command (`the-loop start` on an unarmed work item) posts 😕 and starts nothing (R1.3, AC2) | `cli/tests/test_reactions_integration.py` |
| T5 | Integration | yes | a comment carrying two different control keywords posts 😕 and executes nothing (R1.3, AC3) | `cli/tests/test_reactions_integration.py` |
| T6 | Integration | yes | a comment on an armed work item with no session and no start request posts 👀 once and is not delivered (R1.3, R1.4, AC4) | `cli/tests/test_reactions_integration.py` |
| T7 | Integration | yes | an out-of-scope refusal posts **nothing**, including when the comment carries an authorized control command (R2.4, AC5) | `cli/tests/test_reactions_integration.py` |
| T8 | Integration | yes | a duplicate delivery, an event whose work items were all invented by a branch name, and a spawn-policy drop still post nothing (AC6) | `cli/tests/test_reactions_integration.py` |
| T9 | Regression | yes | the delivered branch is unchanged: success is 👀 → 🎉, failure is 👀 → 😕, a labelled spawn reacts on the issue itself, and a duplicate adds nothing — issue-84's existing scenarios still pass untouched (R2.3, AC7) | `cli/tests/test_reactions_integration.py` (existing) |
| T10 | Integration | yes | a session paused between enqueue and dequeue posts exactly two reactions, as it does today — the in-worker settle adds none (R2.3, AC7) | `cli/tests/test_reactions_integration.py` |
| T11 | Integration | yes | `routing.reactions.enabled: false` silences every new acknowledgement (R2.5, AC8) | `cli/tests/test_reactions_integration.py` |
| T12 | Unit | yes | a reactor that raises cannot break a settle: the control command still executes, the delivery is still marked settled, and the eventlog entry is still written (R2.1, R2.2) | `cli/tests/test_reactions.py` |
| T13 | Regression | yes | the control, routing and scope suites are unaffected — the settle contract they assert on is unchanged | `cli/tests/test_control.py`, `test_routing.py`, `test_control_integration.py` |
| T14 | Docs parity | yes | `docs/config/cli/routing-options.md` describes both branches and the outcome table; the capability docs carry a history row (R5.1, R5.2) | review, recorded in `evidence/documentation.md` |
| T15 | Security | yes | no new payload-derived value reaches an argv: the acknowledgement reuses `target_from_event`'s validated coordinates and a palette name from the config | `evidence/security-review.md` |
| T16 | Performance | no | one best-effort subprocess on paths that previously did none, bounded by the reactor's existing timeout and off the dispatch hot path | — |
| T17 | Accessibility | no | no UI surface | — |

## Commands

```bash
make lint format-check typecheck
uv run --project cli python -m pytest -q cli
```

## Gherkin docstrings

`cli/tests/test_reactions_integration.py` is not a configured integration glob
(`.the-loop/harness-config.yaml` → `testing.integrationTestGlobs` names
`cli/tests/test_*_integration.py`, which it matches), so every scenario added there carries
a Gherkin docstring naming the requirement it links — matching the file's existing tests.

## What is deliberately not tested

- A live `gh`. Every row captures the argv a fake runner receives, which is what issue-84
  established as the unit under test: a network call would prove nothing the capture does
  not, and the reactor's own failure handling already has unit coverage.
- The Slack pipeline's reactions. This work item changes nothing there (R4.2); its
  existing coverage in `cli/tests/test_channels*.py` stands.
- GitHub's idempotency for a repeated reaction. The design's ordering means no path posts
  the same state twice, so the question does not arise.
