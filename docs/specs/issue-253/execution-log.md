---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#253"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: a work item and its pull request had two sessions in one working tree

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-16 | @MadaraUchiha-314 | Declared by the owner's direct instruction in a cloud session: they read the #239/#244 trace, named the defect ("no clear ownership of a work item"; "for single PR work-items there should only be one session") and pointed the work at a designated branch. `brainstorming` skipped — the diagnosis is the ticket; `design-critic-review` not selected (no critic is configured in this repository). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-16 | pending — PR for this branch | `bugfix.md` (a bug). Three requirements; the transport question the trace raised — collapse, or give each pull request a tree — is settled in design, not here. |
| design | 2026-08-16 | pending — PR for this branch | Two seams, one rule. Four alternatives recorded as rejected, with the reason each fails. |
| test-planning | 2026-08-16 | pending — PR for this branch | 13 rows, 7 in scope; every `n/a` carries a reason. |
| tasks-breakdown | 2026-08-16 | | 10 tasks, two independent red roots. |
| implementation | 2026-08-16 | | TDD: the red run captured and committed before the fix. |
| verification | 2026-08-16 | | Every planned activity ran; nothing replanned, nothing skipped. |
| needs-review | 2026-08-16 | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| this branch's PR | The whole work item — the spec chain and the fix. | open |

## Progress entries

### 2026-08-16 — read the trace, then the code

- **Phase:** requirements-definition → design
- **Did:** followed the reported trace on
  [#239](https://github.com/MadaraUchiha-314/the-loop/issues/239) and
  [#244](https://github.com/MadaraUchiha-314/the-loop/pull/244) to the two session
  announcements, then read the path that produced the second one:
  `Dispatcher.handle` → `record_owning` (matching is by **record**, so a linked pull
  request never reaches the unmatched-spawn path) → `_endpoint_for` → `_spawn_endpoint`.
  The last of those spawns with `cwd=record.cwd`.
- **Found, and it decided the design:** `Workspace.prepare` keys **both** strategies on the
  work-item slug, so there is no configuration under which an endpoint gets a checkout of
  its own. "Its own conversation" could therefore only ever have meant "a second agent in
  the work item's tree". That turned the question from *should we collapse?* into *what
  would a second session even work in?*
- **Checked before assuming:** `pdlc-work-item-loop.yaml` states that a work item with no
  inner loops passes `await-inner-loops` vacuously — "one agent, one session, the whole
  pre-issue-172 world" — so collapsing the same-repository case cannot strand the outer
  loop. Without that line the fix would have needed a graph change too.
- **Next:** the rule at `_endpoint_for`, and the checkout question at `_spawn_endpoint`.

### 2026-08-16 — red first, then the two seams

- **Phase:** tasks-breakdown → implementation
- **Did:** wrote the four new tests and rewrote the two integration scenarios the behaviour
  change invalidates, captured the six failures as
  [`evidence/red.md`](evidence/red.md), then implemented `_same_repository`, the rule in
  `_endpoint_for`, and `_endpoint_cwd`.
- **One thing worth stating:** the rule is placed **before** `record.endpoint_for(pr)`,
  not after. An endpoint spawned by an older the-loop is a second owner that already
  exists; testing the repository first is what stops routing feeding it. Nothing is torn
  down — killing a live conversation to enforce a routing rule would destroy in-flight
  work, and `the-loop cleanup` already ends a work item's endpoints on request.
- **Checkpoint/tests:** 2171 passed, 1 skipped; `make lint`, `make format-check` and
  `make typecheck` clean. Evidence in [`evidence/`](evidence/).

### 2026-08-16 — the rewritten scenarios, and what they still prove

- **Phase:** verification
- **Did:** `test_pr_event_still_reaches_its_work_item_after_the_link_is_removed` was
  issue-172's own regression test. Its subject is the **durable binding** — that routing
  survives the closing keyword being edited out — and that is unchanged: the second comment
  still reaches work item 15 with no derivable linkage left. Only the destination assertion
  moved, from the pull request's endpoint to the work item's session. The Gherkin now says
  so, and both scenarios cite `issue-253/bugfix.md#R1` alongside their original
  requirements, so the trace does not silently lose issue-172's coverage.
- **Also corrected:** `uv.lock` carried `the-loopy-one 10.2.3` while `cli/pyproject.toml`
  was already at 10.2.4 — `main`'s version bump did not relock, so any `uv run` dirties the
  tree. Regenerated here as a one-line correction rather than left for the next branch to
  trip over.

## Deviations from the standard gates

- **`phase-selection` was answered by direct instruction, not by the checklist comment.**
  This work started from the owner's message in a cloud session rather than from
  `the-loop start` on the ticket, so no checklist was posted and no `the-loop execute` reply
  exists. The owner's message is the authorization and is quoted in the table above; the
  ticket ([#253](https://github.com/MadaraUchiha-314/the-loop/issues/253)) was filed before
  any code was written, and the spec chain exists in full rather than being skipped.
- **The artifacts are `in-review`, not `approved`.** Nothing here has been through a human
  gate yet; the pull request carries the whole chain for review in one place. No phase
  claims an approval it does not have.
- **This is the second work item to hit the labels problem from
  [#73](https://github.com/MadaraUchiha-314/the-loop/issues/73)** — a cloud session working
  the-loop's own repository has no daemon, so no `loop:<phase>` label is applied to #253 by
  the harness. The phase state is this file.
