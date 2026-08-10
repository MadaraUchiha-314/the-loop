---
type: execution-log
workItem: issue-199
phase: needs-review
status: in-progress
---

# Execution Log: a contribution is asked where its outer loop goes, and then waits

> Append-only log for [#199](https://github.com/MadaraUchiha-314/the-loop/issues/199).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-10 | pending — PR gate | Risk tier 3: graph hooks + the ingress↔graph seam; no schema, no new config key |
| design | 2026-08-10 | pending — PR gate | One predicate read in three places; one new `GraphContext` field; one guarded evaluation at spawn |
| test-planning | 2026-08-10 | pending — PR gate | 14-row matrix; every row runs offline against a fake integration |
| tasks-breakdown | 2026-08-10 | pending — PR gate | 9 tasks; T1–T4 code, T5–T7 tests, T8 docs, T9 verification |
| implementation | 2026-08-10 | — | T1–T8 complete, plus one unplanned change recorded in `tasks.md` |
| verification | 2026-08-10 | — | Every applicable row executed; see `testing-plan.md` § Verification results |
| needs-review | 2026-08-10 | pending | Self-review done (three rounds); the human gate is the PR |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#200](https://github.com/MadaraUchiha-314/the-loop/pull/200) (this repository) | Tasks 1–9 — the whole work item | open |

## Progress entries

### 2026-08-10 — spec chain locked

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** Read the ticket, then the code it names and the code around it:
  `graph/hooks/selection.py`, `graph/hooks/goal.py`, `graph/pdlc-contribution-loop.yaml`,
  `graph/runtime.py`, `graph/state.py`, `graphlink.py`, `control.py` and
  `webhook/dispatcher.py`. Confirmed **both** halves by reading and then by running the
  ticket's scenario offline against the pre-change code (`evidence/reproduction.md`): the
  pointer stops at `goal-definition` with nothing posted, and the checklist a later event
  finally produces carries a row about an outer loop this loop does not have. Established
  why the second defect is invisible on the outer loop — its start node needs a *different*
  comment anyway, and two control keywords in one comment are refused as ambiguous — which
  is what makes the contribution loop the first graph to hit it. Wrote and locked
  `bugfix.md` → `design.md` → `testing-plan.md` → `tasks.md`.
- **Checkpoint/tests:** baseline `make check` green — 1760 passed, 1 skipped.
- **Next:** implement T1–T4, then the tests.
- **Blockers:** none.

### 2026-08-10 — implementation

- **Phase:** implementation
- **Did:** T1–T8. `_asks_surface()` in `selection.py` read at render, parse, confirm and
  freeze (with `NO_SURFACE` documenting *never asked* vs *default kept*);
  `GraphContext.loop` plus the `_is_contribution` branch in `render_graph_context`;
  `GraphLink.on_spawn` evaluating a **human** start node once with the spawning event
  attached, behind `_entered_a_human_gate` (fails closed) and the fresh-entry guard; the
  dispatcher passing `routed` at the spawn seam; the documentation set.
- **Checkpoint/tests:** `make check` green.
- **Next:** verification, then self-review.
- **Blockers:** none.

### 2026-08-10 — verification

- **Phase:** verification
- **Did:** Ran every applicable row of the testing plan and recorded the results in
  `testing-plan.md` § Verification results. Captured the before/after reproduction, the
  unit and abuse-case runs, the dispatcher scenario and the full check under `evidence/`.
- **Checkpoint/tests:** `make check` exit 0 — 1770 passed, 1 skipped.
- **Next:** self-review.
- **Blockers:** none.

## Review cycles

### Self-review — 2026-08-10

Three rounds over the diff, the reasoning recorded because the findings shaped the code:

1. **Round 1 — "does the spawn-time evaluation break anything that was working?"**
   Traced every caller of `on_spawn`: `_spawn_tmux` (a real first spawn) and the respawn
   seam, which is pointer-idempotent. Found the case that would have been a regression —
   an **agent** start node, whose exit chain gates artifacts the session has not written —
   and narrowed the evaluation to human nodes, with `test_a_spawn_never_evaluates_an_agent_start_node`
   pinning it. Also confirmed `Runtime.advance` does not re-acquire the graph-state lock
   `_guarded` already holds (only `Runtime.complete` does), and ordered the advance after
   `_bind_session` so a `session: inherit` gate resolves against the session just spawned.
2. **Round 2 — "is the surface really absent, in every direction?"** Render, parse,
   confirm and freeze were each checked separately, because three of them could have been
   left inconsistent: a checklist without the row whose parser still honoured a typed
   token would be worse than the bug. Settled on recording `""` rather than the default
   after checking that `_record_selected_skips` writes `state.surface` only for a truthy
   value — so *never asked* is representable without teaching any reader a third literal.
   Chose the negative predicate (`!= PDLC_CONTRIBUTION_LOOP`) so a repository-supplied
   outer loop keeps the question.
3. **Round 3 — "what does the user see?"** Ran the reproduction end to end and read the
   posted comment and the prompt block as a human would. The empty space where the row had
   been read as an omission, so the checklist now says where a contribution's conversation
   happens instead; and the prompt's "iterate the outer loop's artifacts on…" line was
   still instructing a contribution about an outer loop, which is the same defect one
   layer along — fixed with `GraphContext.loop` rather than left as a follow-up.

No finding was carried forward unresolved. Critic review and the security review are for
the reviewer to run at the PR gate.

## Security review (gate)

The change moves **when** untrusted comment text reaches a hook chain, not **whether** —
the three trust boundaries and the abuse cases are enumerated in `bugfix.md` § Security
considerations, and each abuse case has a test named in `evidence/unit.md` § T10.
Reachable state is strictly reduced in one place: a contribution can no longer be given a
pull-request surface at all.

## Capability docs

- `docs/capabilities/process-graph.md` — the contribution-loop bullet gains the "no outer
  loop to place" clause; the ingress-drives-the-graph bullet gains the human-start-node
  evaluation; a history row.
- `docs/capabilities/webhook-triggers.md` — the control-keyword bullet gains why a
  spawning command is handed to the graph; a history row.
- `docs/capabilities/spec-workflow.md` — the outer-loop surface bullet names the
  contribution exception.

## Documentation

- `docs/cli/commands/graph.md` — the `phase-selection` section says the row is absent on a
  contribution and what is said instead.
- `skills/the-loop/SKILL.md`, `skills/the-loop/reference/workflow.md`,
  `skills/the-loop/reference/collaboration.md` — the same two facts where an agent reading
  the skill will meet them.

## Verification results

Recorded in [`testing-plan.md`](testing-plan.md) § Verification results, with the
transcripts under [`evidence/`](evidence/): `reproduction.md` (before/after),
`unit.md` (T1, T2, T4, T10, T12), `integration.md` (T3), `check.md` (T6, T14).
