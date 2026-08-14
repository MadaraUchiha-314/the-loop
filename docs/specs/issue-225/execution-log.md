---
type: execution-log
workItem: "issue-225"
phase: implementation
status: in-progress
---

# Execution Log: ad-hoc tasks that run no PDLC process

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-14 |  | The issue asks a question; the requirements answer it (`contribute` does not fit) and specify the fourth loop. Answer posted on the thread first — [comment](https://github.com/MadaraUchiha-314/the-loop/issues/225#issuecomment-5297046053). |
| design | 2026-08-14 |  | One graph, one keyword, one hook, one command, plus a generalization of the three "contribution or default" call sites. |
| test-planning | 2026-08-14 |  | T1/T2/T8 in a new `test_graph_adhoc.py`; T3/T10 are the existing parity and regression suites. |
| tasks-breakdown | 2026-08-14 |  | Nine tasks. |
| implementation | 2026-08-14 |  |  |
| verification | 2026-08-14 |  |  |
| needs-review | 2026-08-14 |  |  |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#227](https://github.com/MadaraUchiha-314/the-loop/pull/227) | all tasks | open |

## Progress entries

### 2026-08-14 — the question is answered on the thread, and the spec chain follows from the answer

- **Phase:** requirements-definition → design → test-planning → tasks-breakdown
- **Did:** read the three shipped loops, `control.py`, `graphlink.py`, `core/graphs.py`
  and the contribution loop's spec/decision record; established that
  `pdlc-contribution-loop`'s two `required: true` gates — a frozen goal with success
  criteria, and a phase-selection checklist — are precisely what an ad-hoc task lacks,
  so `contribute` cannot serve it without either faked criteria or two gates that still
  fire. Posted that answer on issue #225, then authored `requirements.md`, `design.md`,
  `testing-plan.md` and `tasks.md`.
- **Checkpoint/tests:** none yet (no code).
- **Next:** task 1 — `model.py` loop names and `resolve_outer_loop`.

### 2026-08-14 — the loop exists, end to end

- **Phase:** implementation
- **Did:** tasks 1–8. `PDLC_ADHOC_LOOP`, `OUTER_PATH_LOOPS`,
  `LOOP_FOR_CONTROL_COMMAND` and `resolve_outer_loop` in `graph/model.py`; the
  shipped `pdlc-adhoc-loop.yaml`; the
  `classify-adhoc-reply` hook in `graph/hooks/adhoc.py`; the `do` control keyword; the
  four resolution seams (`bootstrap`, `graphlink._outer_loop_name`,
  `graphlink.render_graph_context`, `core.graphs._recorded_loop`) generalized off the
  contribution-only literals; `commands/do-task.md`; the schema leaf and its byte-identical
  package copy, the config template and the routing-options page; the skill, the workflow
  reference, both capability docs, the command reference and
  [decision-083](../../decisions/decision-083.md).
- **Checkpoint/tests:** `uv run --project cli pytest` — see Verification results in
  `testing-plan.md`.
- **Next:** task 9 — execute the testing plan, commit evidence.

### 2026-08-14 — verified

- **Phase:** verification
- **Did:** executed every activity in `testing-plan.md`; recorded the results there and
  committed the redacted output under `evidence/`.
- **Checkpoint/tests:** `uv run --project cli pytest` (whole suite), `ruff check`,
  `ruff format --check`, `pyright`, `markdownlint-cli2` — all green.
- **Next:** the review chain, then the reviewer briefing on the PR.

## Verification results

> This work item has a `testing-plan.md`, so its results are recorded there.

## Design critic review

> Not selected for this work item.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | new findings — the `review` gate initially scanned the whole thread for a done-word, which let `"tell me when you're done"` in the *arming* comment end the item before any work ran; fixed by classifying the **newest** authorized comment only | this PR |
| 2 | self | the-loop | new findings — `the-loop do` risked colliding with prose (`the-loop does`, `the-loop done`); confirmed the existing `(?![\w:-])` boundary already refuses both, and added the regression test rather than changing the parser | this PR |
| 3 | self | the-loop | zero (converged) | this PR |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`, no built-in
  security-review skill in this session) — `reference/security.md`.
- **Outcome:** pass. Three trust boundaries, all pre-existing and all reused rather than
  re-implemented: the control-keyword parser (a closed vocabulary — this change adds one
  word, no new parsing), the human-gate reader (`feedback._authorized_comments` verbatim:
  self-authored dropped before authorization, empty allowlist reads nothing), and
  agent-writable state → graph selection (`resolve_outer_loop`, now the single decision
  point and *narrower* than the `SHIPPED_LOOPS`-plus-special-case it replaces). The
  genuine new risk is that this loop runs no review chain by design; the mitigation is
  attribution rather than a gate — the mode is selected only by a named authorized user's
  keyword, frozen in `graph-state.json`, with the arming comment on the thread. All five
  abuse cases from `requirements.md` are covered by tests in `test_graph_adhoc.py`.
- **Human sign-off:** n/a — risk tier 3, below `security.review.humanSignOffMinTier: 4`.
  The one `sensitivePaths` match (`**/*schema*`, one additive optional leaf in
  `cli-config.schema.json`) does not raise the tier on its own: the property is optional,
  defaulted, and additive, so an existing config validates unchanged.

## Final validation evidence

Every acceptance criterion in `requirements.md` is proved by a row of
`testing-plan.md`'s matrix; the trace table maps each row to its requirement, and the
Verification results table records the command, outcome and committed evidence for each.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`process-graph.md`](../../capabilities/process-graph.md) | the fourth shipped loop: its shape, what it deliberately omits, how it is selected and recorded, and why it adopts an unconfigured repository where a contribution does not | issue-225 |
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | the seventh control keyword `do` — arming, spawn-arming and loop selection | issue-225 |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/SKILL.md` | the fourth loop in the loops paragraph; `/the-loop:do-task` in the command list |
| `skills/the-loop/reference/workflow.md` | a new section, *The ad-hoc loop — a task with no process* |
| `skills/the-loop/templates/cli-config.yaml` | the `do` keyword in the shipped config template |
| `docs/reference/commands.md` | `/the-loop:do-task <id>` |
| `docs/config/cli/routing-options.md` | `control.keywords.do` (Type + Default + prose) |
| `docs/decisions/decision-083.md`, `docs/decisions/decisions.md` | the decision record and its index row |
