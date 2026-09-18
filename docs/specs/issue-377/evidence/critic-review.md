---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#377"
---

<!-- Authored per the the-loop:writing skill. -->

# Critic review: a released work item is launched with the arguments the operator declared

> The `critic-review` node's proof (`reference/reviewing.md` § Running a critic round).

## Rounds

| Round | Critic | Outcome | Findings → disposition |
|-------|--------|---------|------------------------|
| 1 | — | `unavailable` | No critic is configured for this repository (`critics: []`), and this session has no `the-loop critic` runtime attached. Recorded `unavailable`, which does **not** count toward `criticReviewCount` |

## Compensating coverage

With no critic round available, the adversarial pass was carried by the self-review
(`self-review.md`) and by tests written to compose the dispatcher **the way the daemons
do** rather than by hand — the gap that let this bug ship with a green suite:

- **The report's own check, automated.** `test_a_released_session_is_launched_with_every_configured_harness_argument`
  builds the dispatcher through `poller.daemon._build_dispatcher`, releases a parked work
  item with an `issue_comment`, and asserts the argv on both the session record and the
  `session.spawned` event.
- **The promise issue-358 made, tested for the first time.** R8 said the post-gate session
  "already carries the frozen choice"; no test had a gate double that actually froze
  anything. `_GateLink(freeze_model=…)` writes the state file the way `phase-selection`
  does, and the scenario asserts the argv, the record, and that the next event is
  delivered into the session rather than re-launching it.
- **The negative case on the new path.** A forged, undeclared model frozen by the same
  reply contributes nothing — asserted, not inherited.
- **The rewired fixture.** `test_dispatcher_choice.py` now builds its adapter through
  `launch_args`, so the 25 issue-358 tests — the abuse table included — run against the
  real wiring instead of an adapter that happened to carry nothing.

## Findings the self-review raised, and their disposition

| # | Finding | Disposition |
|---|---|---|
| 1 | The conflict finding named the whole `harnesses` section rather than the winning key | Fixed — `harnesses[<h>].args` |
| 2 | `config_findings` could not see the deprecated block when `models_cmd` called it | Fixed — read from the document when the caller passes none |
| 3 | Docs claimed `the-loop diagnose` reports these findings; only `the-loop models` does | Fixed in three places, one of them pre-existing |
| 4 | This repository's config comment pointed at a `harnesses` key it does not have | Fixed — wording |
