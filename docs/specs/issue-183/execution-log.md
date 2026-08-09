---
type: execution-log
workItem: issue-183
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
# repos: not declared — this work item contributes to ONE repository (the-loop itself),
# so `await-inner-loops` behaves exactly as it did before this change. The key it
# introduces is exercised by tests and by evidence/multirepo-scenario.md, not by dogfooding
# a second repository the-loop does not have.
---

# Execution Log: multi-repo work items — the outer loop stays in the origin repo

> Append-only log of progress. Checked in at `docs/specs/issue-183/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-09 | — (see Blockers) | run in-session; the full chain was walked, no phase declared away — this change moves a security boundary (event routing) and touches the config schema |
| requirements-definition | 2026-08-09 | pending (PR) | four requirements: the topology, the declared surface, artifacts always land, declared repos as a gate. Risk tier 4 (schema + routing boundary) |
| design | 2026-08-09 | pending (PR) | four facts added to a model that already had the right shape; no node, edge or artifact changes in the graph — decision-069 |
| test-planning | 2026-08-09 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-09 | pending (PR) | 10 tasks; 1→2/3, 5→6, then docs, integration, capability docs, verification |
| implementation | 2026-08-09 | — | T1–T9 |
| verification | 2026-08-09 | — | T10; every planned activity ran, red recorded before green |
| needs-review | 2026-08-09 | pending | 3 self-review rounds; critic rounds unavailable (no critic configured in `reviews.critics`) |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#184](https://github.com/MadaraUchiha-314/the-loop/pull/184) | the whole work item — T1–T10, in `MadaraUchiha-314/the-loop` (this work item's origin **and** only contributing repository) | open |

## Progress entries

### 2026-08-09 — spec chain

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket against the shipped harness and found four places that assume a
  work item lives in one repository — the router dropping a qualified cross-repo closing
  reference, an inner loop keyed by PR number alone, artifact iteration requiring a pull
  request, and `await-inner-loops` unable to tell "no contribution needed" from "the
  contribution was never opened". Wrote `requirements.md` (R1 topology, R2 the declared
  surface, R3 artifacts always land, R4 the declared-repos gate), `design.md` (the four
  facts, the two state layouts, the trust boundaries), `testing-plan.md` and `tasks.md`.
- **Checkpoint/tests:** none — spec phase.
- **Next:** implement T1–T2.
- **Blockers:** none.

### 2026-08-09 — implementation (T1–T9)

- **Did:** `repo_state_key` + the repo-qualified `inner_loop_state_dir` and `declared_repos`
  in `graph/hooks/loops.py`, with `await_inner_loops` widened to hold on a declared
  repository that has no loop (and to **block** on a malformed declaration); `pr_repo`
  threaded through `build_runtime` → `core/graphs` → the six `graph` verbs (`--pr-repo`,
  added by one shared helper) → the API bodies and the OpenAPI contract → `graphlink`
  (including the state **lock** directory, so two repositories' PR #7 do not contend);
  `linked_work_items` in the router, returning refs so a qualified cross-repo reference can
  name the repository it belongs to; `workflow.outerLoop.surface` in the schema, in
  `harness_config` (+ two `READS` rows) and into the runtime config, rendered into the
  assignment and the prompt context alongside a cross-repo `--pr-repo` claim command. Then
  the rules: `SKILL.md`, `reference/workflow.md`, `reference/collaboration.md`, both graph
  YAML headers, the execution-log and harness-config templates, `docs/config/harness-config.md`
  and `docs/cli/commands/graph.md`.
- **Checkpoint/tests:** `uv run --directory cli pytest -q` → 1520 passed, 1 skipped.
- **Next:** capability docs, the decision record, then verification.
- **Blockers:** none.

### 2026-08-09 — verification (T10)

- **Did:** executed `testing-plan.md`. Reverted the twelve changed source files to `HEAD`
  with the new tests in place to record the red (15 failures + one collection error — the
  import of `declared_repos`), restored them for green, and scripted the ticket's own
  scenario end to end against the shipped router, runtime and hooks.
- **Checkpoint/tests:** full suite 1520 passed / 1 skipped (one pre-existing tmux test flaked once and passed on re-run — recorded in the plan); ruff, ruff format, pyright,
  markdownlint (479 files) and `validate_config.py` all clean. Evidence under `evidence/`.
- **Next:** review chain.
- **Blockers:** none.

## Verification results

Recorded in [`testing-plan.md`](testing-plan.md) § Verification results, against the matrix
rows it planned — this section stays as the template left it, because `test-planning` was
walked rather than declared away.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | new findings — `linked_issue_numbers` had become dead weight as a numbers-only view; kept deliberately as the same-repo narrowing, with a test pinning it, rather than deleted (three call sites in other projects could rely on it) | this PR |
| 2 | self | the-loop (this session) | new findings — `await-inner-loops` originally *waited* on a malformed `repos:` entry, which waits forever; changed to `block`, with the reason written into the message and a test | this PR |
| 3 | self | the-loop (this session) | zero new findings (converged) — the surface line, the claim suffix and the state path each have one expression, and the two path-building call sites both go through `repo_state_key` | this PR |
| — | critic | none configured | **unavailable** — `reviews.critics` is empty in this repository, so no critic round ran; it does not count toward `criticReviewCount` | — |

## Security review (gate)

- **Mechanism:** the-loop's checklist (`security.review.mechanism: auto`; no security-review
  skill is available in this session)
- **Outcome:** pass, with two boundaries newly enforced and one widened:
  - **Repository name → filesystem path (new).** `repo_state_key` accepts
    `[A-Za-z0-9._-]+` segments only, at least two, never `.`/`..`, and **raises rather than
    sanitizes** — a rewritten name would file one repository's state under another's. Every
    path-building call site goes through it (`inner_loop_state_dir`, `build_runtime`,
    `graphlink`'s lock directory, the `--pr-repo` argument). Eight negative cases, plus the
    same values through the CLI/core boundary.
  - **Payload → work-item ref (widened).** A qualified closing reference now names a work
    item in another repository. It materialises only as a `WorkItemRef` (parsed fields, no
    payload string reaching a path, a command or a prompt), and the two boundaries that
    actually gate the blast radius are untouched: the ingress (an event only arrives from a
    repository the operator's receiver or poll source covers) and arming (`_awaiting_start`
    still drops an unstarted work item — tested).
  - **No new secret, subprocess, template or network call.** The new state files record a
    repository name and a pull-request number; the assignment/prompt lines are composed from
    the-loop's own vocabulary plus one of two literals.
  - **Fail-closed everywhere it is ambiguous:** unknown surface → `pull-request`; unknown
    origin repository → the gate waits and says what would fix it; unreadable inner state →
    unfinished; malformed `repos:` → block.
- **Human sign-off:** **pending** — the effective risk tier is 4 (the change touches
  `.the-loop/harness-config.schema.json`, a `sensitivePaths` entry), and
  `security.review.humanSignOffMinTier` is 4, so a named human must sign off on the PR
  before this work item can complete. Not waived by this session.

## Final validation evidence

Every acceptance criterion of `requirements.md` is proved by a committed artifact:

| Requirement | Proof |
|---|---|
| R1.1–R1.4 (topology, state layout, back-compat) | `evidence/tests.md` (T1, T10), `evidence/multirepo-scenario.md` steps 2–3 |
| R1.5 (cross-repo routing) | `evidence/tests.md` (T1 router cases), scenario step 1 |
| R1.6 + abuse cases 1–2 (path boundary) | `evidence/tests.md` (T8), scenario step 8 |
| R2.1–R2.3 (the declared surface and its fallbacks) | `evidence/tests.md` (T1, T12), scenario step 2 |
| R2.6–R2.7 (the session is told; the inner loop has no surface) | `evidence/tests.md` (T1), scenario steps 2 and 7 |
| R3.1–R3.3 (artifacts always checked in and landed) | rules in `SKILL.md`, `reference/workflow.md`, `reference/collaboration.md`; gated as a record by `## Pull requests` above |
| R4.1–R4.4 (declared repositories as a gate) | `evidence/tests.md` (T1, T2, T8), scenario steps 4–6 |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`process-graph.md`](../../capabilities/process-graph.md) | new behaviour block: where each loop runs, the repo-qualified inner-loop state, the validated repository name, cross-repo linkage, the declared-repos gate, and `workflow.outerLoop.surface`; the graph-verb bullet gained `--pr-repo`/`prRepo` | issue-183 row added |
| [`spec-workflow.md`](../../capabilities/spec-workflow.md) | the chain now has a **place** (the origin repository) and a declared iteration surface; `repos:` named as a gate input | issue-183 row added |
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | the linked-issue rule reversed for qualified cross-repo references, with what it does *not* widen stated | issue-183 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | the *Two loops* section gained "and they run in named places" — the origin repository, one PR per contributing repository, and the surface option; the CLI cheat-sheet gained `--pr-repo` |
| `docs/index.md` | the *Two loops, one process* feature card names where each loop runs |
| `docs/guide/how-it-works.md` | a consequence bullet for the loops' locations and the outer surface |
| `docs/config/harness-config.md` | new option section for `workflow.outerLoop.surface`; the CLI-read table grew from six keys to eight |
| `docs/cli/commands/graph.md` | `--pr-repo` documented beside `--pr`, with the `repos:` declaration and what the gate does with it |
| `skills/the-loop/SKILL.md` | a new operating rule for the multi-repo topology, and the artifact-iteration rule rewritten around the declared surface |
| `skills/the-loop/reference/workflow.md` | new section *Several repositories, one work item*, including the surface table |
| `skills/the-loop/reference/collaboration.md` | rule 2 rewritten: a durable, reviewable surface — the PR **or** the ticket — never a terminal |
| `skills/the-loop/templates/execution-log.md` | the optional `repos:` front-matter key, and the PR table's multi-repo shape |
| `skills/the-loop/templates/harness-config.yaml` | `workflow.outerLoop.surface` with its default |
| `docs/api-specs/openapi/the-loop.v1.yaml` | `prRepo` on the five graph bodies and the `graphShow` query |
| `docs/decisions/decision-069.md` (+ index, and pointers from 051 and 065) | the decision record; decision-051 §5's invariant amended in place |
