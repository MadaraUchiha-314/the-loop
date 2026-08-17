---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#258"
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the operator chooses how many sessions a work item's pull requests get

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-17 | @MadaraUchiha-314 | Declared by the owner filing the ticket and pointing this cloud session at a designated branch. `brainstorming` skipped — the ticket names the option it wants and the alternative was already argued in decision-088. `design-critic-review` not selected: no critic is configured in this repository (`reviews.critics: []`). See *Deviations from the standard gates*. |
| requirements-definition | 2026-08-17 | pending — PR for this branch | `requirements.md`, three requirements. The ticket has a **title and no body**, so the reading was posted on the ticket *before* any file was written ([comment](https://github.com/MadaraUchiha-314/the-loop/issues/258#issuecomment-5310675593)) and the requirements link back to it. |
| design | 2026-08-17 | pending — PR for this branch | One key grows a value; one seam grows a requirement. Six alternatives recorded as rejected in [decision-092](../../decisions/decision-092.md), each with why it fails. |
| test-planning | 2026-08-17 | pending — PR for this branch | 12 rows, 6 in scope; every `n/a` carries a reason. |
| tasks-breakdown | 2026-08-17 | | 12 tasks, two independent red roots. |
| implementation | 2026-08-17 | | TDD: the red run captured and committed before the fix. |
| verification | 2026-08-17 | | Every planned activity ran. One replan, recorded below. |
| needs-review | 2026-08-17 | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| this branch's PR | The whole work item — the spec chain, the change, the docs. | open |

## Progress entries

### 2026-08-17 — read the ticket, then decision-088

- **Phase:** requirements-definition
- **Did:** the ticket is one sentence, and the option it asks for looked like one that
  already exists (`routing.tmux.sessionPerPr`). Read issue-253 and decision-088, merged the
  day before, and found that D1 had turned the same-repository half of that option into a
  **rule** — deliberately, with the reason written down: *"a knob for it would be a
  documented way to reproduce the bug."*
- **Decided:** this ticket is its author overruling D1 and D4 of a decision they accepted
  yesterday. That is their call to make, so the work is to build the knob **safely**, not to
  re-argue 088. Posted that reading on the ticket before writing anything, with the option
  table showing that both current values collapse the case being asked about.
- **Next:** separate what 088 established into the claim that is negotiable (which pull
  requests are candidates) and the claim that is not (two conversations never share a tree).

### 2026-08-17 — the invariant, and the trap under it

- **Phase:** design
- **Did:** traced `_endpoint_for` → `_spawn_endpoint` → `_endpoint_cwd` → `Workspace.prepare`
  and found the design already had the shape needed: 088 D2 put "a session needs a tree" at
  a seam of its own. Only `_endpoint_for`'s answer was hard-coded.
- **Found (the important part):** naïvely making the collapse optional would have shipped a
  *new* wrong-tree bug. `ensure_worktree` swallows a failed branch checkout and falls back to
  a **detached default-branch** worktree. For a same-repository pull request the work item's
  own session already holds that branch, so `git worktree add -B` fails every time — and the
  fallback returns a **distinct path**, which sails past `_endpoint_cwd`'s existing
  `_same_path` guard. The-loop would have announced a session for pull request #N sitting on
  `main`.
- **Decided:** `Workspace.prepare(require_branch=True)`, passed for a same-repository
  endpoint only. Recorded as [decision-092](../../decisions/decision-092.md) D4, and it is
  why `always` is honestly documented as needing `strategy: clone`.

### 2026-08-17 — red, then green

- **Phase:** implementation
- **Did:** wrote the failing tests first and committed them alone
  (`3a71828`): 28 failed, 173 passed across `test_routing.py`, `test_workspace.py` and
  `test_configschema.py`. Evidence in [`evidence/red.md`](evidence/red.md).
- **Then:** the three modes and their two derived questions in `TmuxConfig`; one clause in
  `_endpoint_for`; `require_branch` through `prepare` / `ensure_worktree` /
  `ensure_workitem_clone` / `_prepare_workspace` / `_endpoint_cwd`; the schema leaf.
- **Note on the schema:** the design first said `anyOf`. `configschema.py` is a hand-written
  validator whose supported-keyword set is asserted by a test, so `anyOf` would have meant
  implementing a combinator to say what `type: ["string", "boolean"]` + `enum` already says.
  Changed to the union, and the design records why.
- **Fixed while green:** three call sites outside the diff's subject —
  `StubWorkspace.prepare` in `test_trust_integration.py`, a `_prepare_workspace` lambda
  double in `test_routing.py`, and two `TmuxConfig(session_per_pr=False)` constructions that
  pyright rejected once the field became a `str`. The last two now say `"never"`, which is
  what they meant.

### 2026-08-17 — verification

- **Phase:** verification
- **Ran:** every activity in [`testing-plan.md`](testing-plan.md). Whole suite 2,308 passed
  / 1 skipped; `make lint` (776 markdown files, 0 errors), `make format-check`, `make
  typecheck` (0 errors), `make validate` (7 configs valid), docs↔schema parity green.
- **Replanned, with the reason:** T2 was planned to run in
  `test_webhook_routing_integration.py`. Its `server_factory` builds no git origin, so the
  scenarios would have needed the `make_origin` helpers duplicated into it. They run in
  `test_workspace.py` instead, beside
  `test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout`, which is the same shape:
  dispatcher in-process, faked tmux, **real** git. They keep their Gherkin docstrings. The
  matrix and the environment section were updated to say so rather than left describing the
  plan that was not executed.
- **Corrected:** the plan's Verification-results row said "13 failed" for the red run before
  the run existed; the actual count is 28, and the file now says 28.

## Capability docs

- [`docs/capabilities/webhook-triggers.md`](../../capabilities/webhook-triggers.md) — the
  routing behaviour is restated as the invariant (a session needs a tree, in every mode)
  plus the three-mode choice, replacing the two bullets that stated the collapse as a rule.
  A history row for issue-258 was added.
- [`docs/capabilities/process-graph.md`](../../capabilities/process-graph.md) — which pull
  requests have a session to drive an inner `pdlc-pr-loop` from is now the mode, not
  "cross-repository only".

## Documentation

- [`docs/config/cli/routing-options.md`](../../config/cli/routing-options.md) — the
  `tmux.sessionPerPr` section rewritten for three values, with the mode table, the
  `always` + `strategy: clone` obligation in a warning box, and an upgrade note for the
  booleans.
- [`docs/cli/state.md`](../../cli/state.md) — what a `pullRequests[]` entry means now that
  three modes decide whether it carries a conversation.
- [`.the-loop/cli-config.yaml`](../../../.the-loop/cli-config.yaml) and
  [`skills/the-loop/templates/cli-config.yaml`](../../../skills/the-loop/templates/cli-config.yaml)
  — the key is now stated explicitly with its three values commented, in this repository's
  own config and in the one `/the-loop:init` scaffolds.
- [`cli/the_loop/eventlog.py`](../../../cli/the_loop/eventlog.py) — the `session.pr_spawned`
  and `session.pr_session_declined` descriptions (read by `the-loop events --explain`) say
  which pull requests reach them under which mode, and name the new decline case.
- [`cli/the_loop/graph/pdlc-pr-loop.yaml`](../../../cli/the_loop/graph/pdlc-pr-loop.yaml) —
  the header comment, which told the reader an inner loop is a cross-repository thing.
- `README.md` and the skill's `reference/` docs: **not changed, and here is the reason.**
  Neither describes `sessionPerPr` or how many sessions a pull request gets — the CLI
  daemon's routing configuration is documented in `docs/config/cli/`, which is where the
  change landed. A blank would not have been an answer; this is the answer.

## Decisions

- [decision-092](../../decisions/decision-092.md) — *How many sessions a work item's pull
  requests get is the operator's choice — the tree is not.* Refines decision-088 D1 and D4;
  D2, D3 and D5 stand and are what make the choice affordable. Numbered 092 because 089–091
  were taken by work merged on 2026-08-16.

## Deviations from the standard gates

- **`phase-selection` was not posted as a checklist on the ticket.** This work item runs in
  a one-shot cloud session, not under the CLI daemon, so there is no session to wait for a
  reply into. The owner's own act — filing the ticket and pointing a session at a designated
  branch — is the declaration, and the phases actually walked are listed above. The reading
  of an otherwise-empty ticket was still posted first, so the gate's *purpose* (a human
  states what is wanted before code is written) is served by a comment rather than by a
  checklist.
- **Critic review not run.** `reviews.criticReviewCount` is 3, but `reviews.critics` is
  empty in this repository — there is no second harness configured to run one. Self-review
  was run and its findings are in the diff (the `anyOf` → `type`+`enum` change, the
  `require_branch` narrowing to same-repository only, and the `None`-is-not-a-typo case in
  the fail-closed test all came out of it).
- **Human sign-off is pending, as it must be.** Risk tier 4 — the diff touches
  `.the-loop/cli-config.schema.json`, a `sensitivePaths` entry — so `autonomy.tiers."4"` is
  `human-approves-pr`, and `security.review.humanSignOffMinTier: 4` additionally requires a
  named human security sign-off. Both are requested on the pull request. Nothing here
  completes autonomously.
