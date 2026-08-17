---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#260"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: how many sessions a work item's pull requests get is the work item's choice

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| not-started | 2026-08-17 | — | ticket #260 opened from the owner's objection to #259 |
| phase-selection | 2026-08-17 | — | see Deviations: the loop was run by hand in a cloud session, not by a daemon |
| requirements-definition | 2026-08-17 | pending | `requirements.md` |
| design | 2026-08-17 | pending | `design.md` |
| test-planning | 2026-08-17 | pending | `testing-plan.md` |
| tasks-breakdown | 2026-08-17 | pending | `tasks.md` |
| implementation | 2026-08-17 | — | T4–T8 |
| verification | 2026-08-17 | — | every activity in the testing plan ran; results recorded there |
| needs-review | 2026-08-17 | pending | human approval of the pull request (tier 3: `human-approves-pr`) |

## Pull requests

| Repository | PR | Loop state | Status |
|---|---|---|---|
| MadaraUchiha-314/the-loop | (this branch) | outer loop only — one repository, one delivery | open |

## Progress entries

### 2026-08-17 — read #259 before writing anything

The ticket is one sentence of objection to a pull request that merged hours earlier. Read
[#259](https://github.com/MadaraUchiha-314/the-loop/pull/259) end to end first —
`docs/specs/issue-258/requirements.md`, `decision-092.md`, and the code it landed — because
the complaint is *about* a decision, and overruling one without reading it is how a
subsequent work item reintroduces the defect the first one fixed.

Two things came out of that read and shaped everything after:

1. **issue-258 anticipated this.** Its Out of scope section lists *"a per-work-item override
   of the choice"* with the reason *"nobody has asked it"*. Nobody had. So this is not a
   reversal of decision-092 — its three modes, its boolean compatibility, its fail-closed
   rule and its `require_branch` safety clause all survive untouched. Only **who decides**
   moves. decision-093 says so in its Refines line rather than superseding 092.
2. **The argument already exists in the repository, written by the same author.**
   issue-183/decision-069 put `outer-loop-on-pull-request` at `phase-selection` and not in a
   config file, *"because one repository has both a one-repo bugfix and a three-repo
   migration"*. That sentence is the ticket. Building the second question in the shape of the
   first is what makes this a small change instead of a new mechanism.

### 2026-08-17 — the shape: a default-and-override chain, not a new channel

The whole design is three links — config → checklist → frozen record → routing — and the
interesting choices were all about *failure*:

- **Three rows, not one box.** A checkbox has two states and the question has three.
  Collapsing two of them is precisely what #260 objects to, so reintroducing a collapse one
  level up would have been the same bug in a new place.
- **Ambiguity resolves to the operator's value, not to the narrowest mode.** Fail closed here
  means *the value already in force* — what the operator stated and what every work item ran
  on before the question existed. Guessing which of two ticks a human meant is how a
  three-repo migration silently gets one conversation.
- **The frozen answer wins over a later config edit.** A frozen selection is a recorded
  agreement (issue-177); a work item whose routing changed under it because someone edited a
  file next week would be the same complaint one level down.
- **A new module for the vocabulary.** `graph/hooks/selection.py` cannot import
  `webhook/dispatcher.py` — `dispatcher → graphlink → graph` is a cycle. A function-level
  import would have dodged it while hiding the dependency, so the three names and their
  resolver moved down to `the_loop/prsessions.py` and both readers import it. Two copies of a
  three-name vocabulary is how a config file and a checklist come to disagree about what
  `always` means.

### 2026-08-17 — one seam that was not obvious

`delivery_status` had to move with `_endpoint_for`. It is the poll path's "was this delivery
handled?" question, and it resolved the ref through the **operator's**
`splits_pull_requests`. A pull request that has merely been *linked* has a live endpoint with
no conversation — so for a work item that chose `never`, asking with splitting on would have
looked straight past the session that actually recorded the delivery and answered
`unhandled`, and the poller would have re-forwarded the same comment until its retry budget
was spent. It now resolves through the owning record's own mode. R2.5 and its test exist
because of this; the failure would only ever have shown up as a duplicated comment in
production.

### 2026-08-17 — red, then green

Red run: 17 failures across four files, captured in `evidence/red.md` with a note on the
three cases that pass red **by design** (they assert the fallback, which is the requirement
that nothing changes for a work item that never answered).

Green: `make test` — 2333 passed, 1 skipped. No existing test was modified to accommodate the
change; three helpers were extended (`_endpoint_ref_for`, `pr_comment_payload`, and a new
`_selecting_with`). `_endpoint_ref_for` also gained `portable_dir=tmp_path`, which it should
always have had — it was inheriting `RoutingConfig`'s default and reading this repository's
own `.the-loop/portable`.

### 2026-08-17 — verification

Every activity in `testing-plan.md` ran; results and evidence links are in that file's
Verification results table. `make lint` raised three findings during the run (an import left
behind by the module move, a short table row in this work item's own testing plan, and a link
fragment to a heading containing an em dash) — all fixed before the gate, all listed in
`evidence/lint-and-typecheck.md` rather than quietly dropped.

## Capability docs

- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — the
  `phase-selection` contract gains the third question (rows, resolution, freeze, which loops
  are asked), the inner-loop clause now reads the frozen mode first, and a history row.
- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — routing
  reads the work item's frozen `sessionPerPr` ahead of the config key, with the retry-path
  clause stated, and a history row.
- [`docs/cli/state.md`](../../cli/state.md) — the portable record's `graph` section documents
  `sessionPerPr`, including what deleting the record now costs.

## Documentation

- [`docs/config/cli/routing-options.md`](../../config/cli/routing-options.md) —
  `tmux.sessionPerPr` is stated as the **default**, with the checklist tokens and the
  override.
- Both copies of `cli-config.schema.json` (authored + packaged, byte-identical) — description
  only; the type, enum and default are unchanged, which is why no schema test moved.
- `.the-loop/cli-config.yaml` and `skills/the-loop/templates/cli-config.yaml` — the block
  commentary now says "default", not "choice".
- [`skills/the-loop/reference/workflow.md`](../../../skills/the-loop/reference/workflow.md) —
  a section beside the surface one, including *the agent never ticks these rows*.
- [`skills/the-loop/SKILL.md`](../../../skills/the-loop/SKILL.md) — one clause naming both
  non-phase questions.

## Decisions

- [decision-093](../../decisions/decision-093.md) — *how many sessions a work item's pull
  requests get is the work item's choice; the operator states the default*. Refines
  decision-092 (its premise only — every sub-decision stands) and extends decision-069.

## Deviations from the standard gates

- **The loop was walked by hand.** This session is a Claude Code cloud session in the-loop's
  own repository, where the plugin's SessionStart hook does not fire and no daemon is
  driving the graph (the gap `CLAUDE.md` exists to cover). The spec chain, the phase labels
  and this log were produced by following `skills/the-loop/SKILL.md` directly. No
  `phase-selection` checklist was posted and no `the-loop execute` was signed, because there
  was no daemon to post one — so the artifacts stand in for the gate, and the human approval
  is the pull request review.
- **`tdd.mode: standard`, out of order.** The production edits were drafted before the tests
  were written; the red run was produced by reverting them (`git stash push -- cli/the_loop`)
  and is a genuine capture of `main` + these tests, but the sequence was not tests-first.
  Recorded here and in `evidence/red.md` rather than presented as a clean TDD run.
- **One unrelated line.** `uv.lock` picks up `version = "10.5.0"` for the workspace package.
  The `10.4.1 → 10.5.0` bump commit did not refresh the lock, so `uv run` rewrites it on the
  first invocation in any checkout. Included because leaving it dirty is worse than carrying
  a one-line lock sync; it is not part of this change.
