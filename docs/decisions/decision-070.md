# Decision 070: joining existing work is a third loop, armed by a keyword and gated on a stated goal

- **Status:** proposed
- **Date:** 2026-08-09
- **Deciders:** @MadaraUchiha-314 (issue #185); shape proposed by the harness, pending PR review
- **Work item:** issue-185
- **Spec:** `docs/specs/issue-185/`
- **Refines:** [decision-065](decision-065.md) (the PDLC is two loops — it is now three)
  and [decision-068](decision-068.md) (the selection-gate invariant, which this loop
  carries twice: once for the phases, once for the goal).

## Context

Issue #185, verbatim: *"What if we want to have the-loop work on a small addition or fix
to some existing work item for which there might exist a PR etc … Simply saying 'the-loop
start' or 'the-loop execute' won't cut it. The user needs to give a goal and a success
criteria for the-loop to do it's intervention and to determine when it's complete … also
need to ensure that the-loop doesn't bloat the existing work item with all it's heavy
machinery."*

Both shipped loops assume the-loop owns the work item: the outer loop derives the full
four-artifact spec chain; the inner loop walks a PR the process itself opened. Neither
fits being *invited into* someone's in-progress work — possibly produced by a bespoke
process — for a scoped intervention.

## Decision

1. **A third shipped graph, `pdlc-contribution-loop`** — same vocabulary, hooks, runtime
   and state files as the other two; a repository still cannot override it.
2. **The mode is declared, never inferred.** A new arming control keyword, `contribute`
   (default `the-loop contribute`), behaves as `start` at every spawn seam and selects
   this loop. Auto-detecting "in-progress" from the item's history was rejected: joining
   someone's work is a decision, and decisions here get a named author and a durable
   record (the issue-177 principle). The choice is persisted in the portable control
   record and then in `GraphState.loop`, resolved state-first everywhere; non-shipped
   names fail closed to the default.
3. **No goal, no start.** A required `goal-definition` node precedes even
   `phase-selection`: it waits for an authorized comment carrying `Goal:` plus a
   `Success criteria:` bullet list (the arming comment qualifies — the gate re-reads the
   thread), freezes them with provenance, and confirms. The criteria become checkboxes
   the `verification` node blocks on: **done means the criteria are met.**
4. **One artifact, not four.** The planning nodes author a single `contribution.md`
   (goal, criteria, context, approach, verification plan/results — bundled template),
   locked and human-approved; the review chain gates the shared execution log as ever.
   Every node but the two gates is skippable (skip sets `plan`, `review-chain`), so a
   contained instruction runs as little as implementation + verification.
5. **An unadopted repository stays clean** (added on PR #187 review). The target may
   carry no `.the-loop/harness-config.yaml` at all: every read then degrades to the
   defaults (decision-044), the spec tree is working state only — excluded from git in
   the checkout at `Runtime.start`, so the contribution PR structurally cannot carry
   it — and the plan and its verification results are posted to the thread
   (`publish-artifact` at `plan-approval` and `human-approval`), the one review
   surface such a repository offers. In an adopted repository the hook skips and
   nothing changes.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Walk the outer loop with phases declared away | Still frames the work as owning the whole item; no goal gate, so "start" alone would produce an unscoped agent in someone's work |
| Auto-detect in-progress items (existing PR, no spec dir) | A heuristic the human never declared — the exact shape issue-177 removed from skips |
| Goal as a new comment format parsed by the dispatcher | Widens the daemon's trust boundary; as a graph gate it reuses the authorization and decision-record machinery that already exists |
| A `mode` field in the harness config | The mode is per-work-item, not per-repository — the same argument that moved the surface out of the config (decision-069) |

## Consequences

The control vocabulary grows by one word and the cli-config schema by one property (a
`sensitivePaths` match — risk tier 4). The CLI `sessions start` verb still arms only the
outer loop; a CLI-side `contribute` verb is deliberately deferred until wanted. `graph
show` without a work item still renders the shipped outer loop.
