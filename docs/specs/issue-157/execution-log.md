---
type: execution-log
workItem: issue-157
phase: needs-review              # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress              # in-progress | complete
---

# Execution Log: `the-loop install`/`upgrade` supports the Cursor plugin

> Append-only log of progress. Mirrors the `loop:<phase>` label on
> [issue #157](https://github.com/MadaraUchiha-314/the-loop/issues/157).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-06 | pending (PR) | 5 requirements; risk tier 3 (runs `git`, but only when a human types the command) |
| design | 2026-08-06 | pending (PR) | A `BINARIES` entry + one planner; the clone demoted from design to fallback |
| test-planning | 2026-08-06 | pending (PR) | 5 of 11 matrix rows in scope; T4 `n/a` **with the reason** — a real e2e needs a Cursor this environment does not have |
| tasks-breakdown | 2026-08-06 | pending (PR) | 7 tasks |
| implementation | 2026-08-06 | — | Tests red first, then the component; no new dependency |
| verification | 2026-08-06 | — | Every in-scope activity ticked; T11 run against the real command |
| needs-review | 2026-08-06 | pending (PR) | 3 self-review rounds; critic rounds unavailable (`reviews.critics` empty); security review passed — no human sign-off required at tier 3 |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (this branch) | all tasks (1–7) | open |

## Review cycles

`reviews.selfReviewCount: 3`, `reviews.criticReviewCount: 3`,
`stopOnNoNewFindings: true`.

| Round | Kind | Findings | Action |
|-------|------|----------|--------|
| 1 | self — the new code, line by line | **F1.** `CURSOR_PLUGIN_PARENT`'s comment claims the code and `docs/guide/installation.md` "cannot drift", but nothing enforced it — a claim in a comment holding itself up. **F2.** The testing plan traced T2 to R1.4 ("one component's skip does not stop another") and no test asserted it for Cursor. | Both fixed: `test_the_documented_clone_path_is_the_one_the_code_uses` reads the guide and asserts the path appears in it; `test_a_skipped_cursor_does_not_stop_the_other_components` runs `claude`+`cursor` with `git` absent and asserts `applied`/`skipped` and exit 0. |
| 2 | self — requirement trace, R1–R5 against the tests | None new. Every acceptance criterion maps to a named test in the trace table, and each one was re-read against its assertion rather than its title. | — |
| 3 | self — docs and the artefacts a human reads | None new. The five places claiming Cursor was unsupported (`install.md`, `upgrade.md`, `cli/installation.md`, `guide/installation.md`, `README.md`) are updated; the two capability docs carry current behaviour plus a history row; decision-057's deferral is marked discharged rather than quietly edited. | — |
| — | critic | **Not run.** `reviews.critics` is empty in `.the-loop/harness-config.yaml` and no second harness is installed in this environment (`cursor-agent` is absent — the same fact this work item is about). Recorded rather than reported as passed. | Escalated to the PR: the human review round is the substitute. |

Self-review stopped at round 3 with no new findings, per `stopOnNoNewFindings`.

## Security review (gate)

`security.review.required: true`, `mechanism: auto`, `humanSignOffMinTier: 4`. Risk tier
**3**, so **no named human security sign-off is required**; the checklist below is the
gate.

| Boundary (requirements § Security considerations) | Verdict | Where it is held |
|---|---|---|
| §1 the marketplace value becomes a **URL** | pass | `plan()` validates any component in `BINARIES` before a planner runs; `cursor` is in `BINARIES`. Proved by the parameterised refusal test (including a `--upload-pack=`-shaped value) and by the real run in `evidence/operator-view.md` (exit 2, nothing created). |
| §2 subprocess construction | pass | `git` resolved via `env.which`, invoked as an argv list through the module's single `_run`; `--` separates options from the URL. |
| §3 confined writes | pass | One path, `cursor_plugin_dir(env)`, under the operator's home. No delete, no overwrite; an occupied non-checkout directory is asserted byte-identical after `execute` at both unit and integration level. |
| §4 scope confusion | pass | `--scope project` short-circuits to `skipped` before any step is built — there is no code path from a project-scoped request to a user-level clone. |
| §5 privilege | pass | No elevation, no `sudo`; nothing outside `env.home` or the named project directory. |

**New attack surface:** running `git` — a binary the operator already has and the
documented route already uses — against one URL derived from a validated value, into one
path in their home directory. No credentials read or written, no network endpoint, no new
parser, no input the operator did not type. Stated, not implied.

## Progress entries

### 2026-08-06 — requirements authored

- **Phase:** not-started → requirements-definition
- **Did:** read the ticket, #152's spec chain and decision-057 § *Cursor, parked*.
  Attempted the ticket's own first step (`cursor-agent plugin --help`) and could not run
  it: no `cursor-agent` on any reachable machine, and `cursor.com/docs` +
  `forum.cursor.com` still return HTTP 403 from this environment — the same wall the
  ticket recorded in February. Wrote the requirements to be correct under either answer
  (R5 makes the surface a runtime question) and raised the unanswered question on the
  ticket rather than blocking on it.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** design.
- **Blockers:** none. One open question recorded (the `--help` output), non-blocking by
  construction.

### 2026-08-06 — spec chain locked, implementation complete

- **Phase:** requirements-definition → … → verification
- **Did:** derived design, testing plan and tasks; then tasks 1–6. Tests red first
  (22 failing on a `cursor` that `resolve_components` still rejected), then the component:
  a `BINARIES` entry, `plan_cursor`, `_cursor_clone_steps`, and `plan()`'s hard-wired
  `else: plan_claude` replaced by a `PLANNERS` mapping. Then the five docs that said
  Cursor was unsupported, both capability docs, decision-064, and decision-057's deferral
  marked discharged.
- **Checkpoint/tests:** `make check` green (lint, format-check, typecheck, validate,
  1366 tests) — see `evidence/`.
- **Next:** task 7, execute the testing plan.
- **Blockers:** none.

### 2026-08-06 — verification complete

- **Phase:** verification → needs-review
- **Did:** executed every in-scope activity of `testing-plan.md`, ticked them, filled the
  results table and committed the evidence. T11 was run against the **real** command on
  this machine (`--help`, three `--dry-run` routes, one refused `--from`) rather than read
  off the code, which is what produced the finding that the docs had to answer "which
  route runs on my machine" with a table rather than prose.
- **Checkpoint/tests:** all green; see `testing-plan.md` § Verification results.
- **Next:** self-review rounds, then the human gate (risk tier 3 → human-approves-PR).
- **Blockers:** none. Critic rounds cannot run here (`reviews.critics` is empty and no
  second harness is installed) — recorded above rather than claimed.
