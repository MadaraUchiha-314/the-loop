---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#273"
phase: needs-review              # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress              # in-progress | complete
---

# Execution Log: `phase-selection` never ran for a work item whose spec folder does not exist yet

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| not-started | 2026-08-20 | — | ticket #273 |
| phase-selection | 2026-08-20 | — | see Deviations: the loop was run by hand in a cloud session, not by a daemon |
| requirements-definition | 2026-08-20 | pending | `bugfix.md` |
| design | 2026-08-20 | pending | `design.md` |
| test-planning | 2026-08-20 | pending | `testing-plan.md` |
| tasks-breakdown | 2026-08-20 | pending | `tasks.md` |
| implementation | 2026-08-20 | — | tasks 1–6, test-first per `tdd.mode: standard` |
| verification | 2026-08-20 | — | every activity in the testing plan ran; results recorded there |
| needs-review | 2026-08-20 | pending | human approval of the pull request (tier 3: `human-approves-pr`) |

## Pull requests

| Repository | PR | Loop state | Status |
|---|---|---|---|
| MadaraUchiha-314/the-loop | [#274](https://github.com/MadaraUchiha-314/the-loop/pull/274) | outer loop only — one repository, one delivery | open, briefing posted |

## Progress entries

### 2026-08-20 — the ticket's diagnosis is right, and the predicate is one line

`GraphLink._guarded` gated **every** graph action on `<specDir>/<id>/` existing. Confirmed
by reading, not by inference: the same `is_dir()` sits between `_adopt` and the runtime
build, and `start` reaches it exactly like `advance` does. The ticket's suggested fix 1 —
exempt `start` — is the right shape, and the two writers a start reaches
(`state_lock`, `GraphState.save`) already `mkdir(parents=True, exist_ok=True)`, so there is
nothing to pre-create.

### 2026-08-20 — `context` has to come with it, or the fix is half a fix

The ticket's closing paragraph ("the auto-execute session prompt should not let the harness
begin phase work while the item's graph is absent") turns out to be load-bearing, and to
need the *same* exemption for a different reason.

The dispatcher reads the graph context **before** it spawns and enters the graph **after**
(issue-148, D5 — a failed spawn must not leave a labelled ticket pointing at a node nobody
stands on). So for a fresh work item the prompt is written at the one moment there is no
pointer, and `_context_from` answered that with `None`: an empty `$graph_context`, in a
prompt whose own sentence says *"the block below states where this item stands"*. Exempting
only `start` would have left the session reading that empty block and starting work while
the graph — correctly started, moments later — sat at `phase-selection`.

So `context` is exempt too (it is a pure read, already excluded from `_ADOPTING_ACTIONS`),
and an unplaced work item now resolves to its graph's `start` node with status `pending`.
`advance` and `clean` keep the check: neither can be a work item's first contact with the
graph, and keeping it there is what preserves this module's stated asymmetry — no input
moves an unplaced work item forward.

### 2026-08-20 — the fix, red→green, task by task

Written test-first: the 8 tests in [`evidence/red.md`](evidence/red.md) all failed with the
production change stashed, each on the behaviour rather than on a missing symbol.

| Task | Red → green | What landed |
|---|---|---|
| 1 the predicate | `test_a_work_item_with_no_spec_directory_is_still_started`, `…_records_no_skip` | `_SPEC_DIR_OPTIONAL_ACTIONS = {"start", "context"}` beside `_ADOPTING_ACTIONS`, consulted by `_guarded`'s `is_dir()` gate. Nothing above it in the gate order moved |
| 2 the pending context | `test_a_fresh_item_reports_the_node_it_is_about_to_stand_on` | `GraphLink._pending_context`; `_context_from` delegates to it; `GraphContext.status` documents `pending` and why it is not `at_human_gate` |
| 3 the pending block | `test_the_spawn_prompt_of_an_unplaced_work_item_forbids_starting_a_phase` | `render_graph_context` short-circuits on the status: NOT-ENTERED-YET, the human-gate line, the escalation line — and none of the resume, claim or surface lines |
| 4 the reproduction | `test_a_ticket_with_no_spec_folder_is_still_held_at_phase_selection`, `test_the_gate_still_waits_for_an_authorized_human`, `test_a_graph_that_has_started_reports_its_real_node` | real `Dispatcher` + real `Runtime` over the shipped graph, with `_bare_checkout` and a recording `_FakeGitHub` |
| 5 the tests that pinned the old behaviour | 4 rewritten | the skip tests retargeted to `advance`; the `specDir` parity test split across a gated and an exempt action; the scaffold suite gained an autouse offline provider and now asserts `graph-state.json` instead of its absence |
| 6 the docs | `make lint` | `process-graph.md` and `webhook-triggers.md` |

### 2026-08-20 — the scaffold suite started reaching the network, which is a consequence worth naming

`test_harness_config_scaffold_integration.py` drives the **real** coupling in an unadopted
checkout. Once a spawn there starts a graph, the `phase-selection` entry chain resolves a
provider and calls it — and the suite's first run after the fix printed
`403 Forbidden` warnings for `PUT /repos/octo/repo/issues/193/labels` and a comment POST. The
hooks are best-effort so nothing failed, but a test about writing one YAML file had acquired
a network dependency. It now carries an autouse offline provider at the seam issue-194
established (`the_loop.graph.integrations.resolve`).

## Capability docs

- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — a new
  behaviour bullet stating which actions require the spec directory and why the split falls
  there; the `pending` context and what its block says, added to the
  resolved-before-delivery bullet; the `graph.skipped` bullet now says which actions can
  still produce one; and an `issue-273` history row.
- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — the
  list of when `$graph_context` renders empty corrected ("fresh item" and "no spec
  directory" are no longer members), the exemption noted beside the `specDir` paragraph,
  and an `issue-273` history row.

## Documentation

No user-facing configuration, CLI surface or state format changed, so nothing under
`docs/cli/`, `docs/config/` or the README describes anything differently. The two prompt
**templates** are deliberately untouched — see `design.md` § Trade-offs: a template sentence
cannot tell whether a graph exists, so "wait to be placed" in the template would deadlock
every deployment running with `graph.enabled: false`. The guard lives in the block that
knows.

## Reviews

`reviews.selfReviewCount: 3`, `stopOnNoNewFindings: true`.

| # | Type | Focus | Findings | Resolution |
|---|------|-------|----------|------------|
| 1 | self | the production diff, line by line | **1, and it mattered.** The `pending` block's first draft said "until that assignment arrives, do not start a phase". True at a spawn; false on an *event* prompt, which can carry a pending context for a session that predates the coupling or whose entry faulted — there no assignment is ever coming, so the block would have parked such a session indefinitely. A worse failure than the empty block it replaces | reworded for both prompts ("the loop delivers this node's assignment when it enters it") and given a closing line that turns the stall into an escalation: *if no assignment arrives, say so on the work item — never start the phase yourself*. The docs and the spec chain were re-synced to the final wording |
| 2 | self | the tests | **1.** The new integration scenario called `eventlog.reset()` at its end, which conftest's autouse `_hermetic_eventlog` already does on both sides of every test — and which would not have run at all had the assertion above it failed | removed; the fixture is the single place that owns it |
| 3 | self | the spec chain against what actually landed | **0 new findings** — `stopOnNoNewFindings` | — |

No finding repeated across rounds, so nothing escalated under `escalateOnRepeatFinding`.

## Deviations from the standard gates

- **The loop was walked by hand.** This is a Claude Code cloud session in the-loop's own
  repository, where the plugin's SessionStart hook does not fire and no daemon drives the
  graph (the gap `CLAUDE.md` exists to cover). The spec chain, the phase labels and this log
  were produced by following `skills/the-loop/SKILL.md` directly. No `phase-selection`
  checklist was posted and no `the-loop execute` was signed, because there was no daemon to
  post one — the artifacts stand in for the gate, and the human approval is the pull request
  review. The irony is noted rather than smoothed over: this work item is about that gate,
  and it could not run it either.
- **The critic rounds could not be run as specified.** `reviews.criticReviewCount: 3` asks
  for three rounds from a *different* harness/model, and `reviews.critics` is empty in this
  repository's config, so there is no critic to invoke. Three self-review rounds ran instead
  and are recorded above; the missing rounds are stated here rather than reported as done.
- **The security review used the checklist, not the skill.** `security.review.mechanism` is
  `auto`, which prefers a built-in security-review skill; the checklist is its shipped
  fallback and is what ran here, recorded as what it was.

## Security review

- [x] Checklist (`reference/security.md`), effective risk tier 3 → no named human security
  sign-off required (`humanSignOffMinTier: 4`); pass with no findings, one residual
  recorded — [`evidence/security-review.md`](evidence/security-review.md).

## Verification results

Recorded in full in [`testing-plan.md`](testing-plan.md) § Verification results, with the
console output under [`evidence/`](evidence/). Every planned activity ran; nothing was
replanned and nothing is left unticked.
