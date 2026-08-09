---
type: execution-log
workItem: issue-185
phase: needs-review          # not-started | phase-selection | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: the contribution loop — joining existing work items

> Append-only log of progress. Checked in at `docs/specs/issue-185/execution-log.md`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-08-09 | — (see Blockers) | run in-session; the full chain was walked, no phase declared away — this change adds a control keyword (trust boundary) and touches the cli-config schema |
| requirements-definition | 2026-08-09 | pending (PR) | five requirements: the third graph, no-goal-no-start, trigger parity, intervention-sized phases, done-means-criteria-met. Risk tier 4 |
| design | 2026-08-09 | pending (PR) | one graph + the smallest selection seams; auto-detection explicitly rejected — joining is a declared decision (decision-070) |
| test-planning | 2026-08-09 | pending (PR) | reviewed with the design, one gate for both (decision-060 D2) |
| tasks-breakdown | 2026-08-09 | pending (PR) | 9 tasks; T1 → {T2,T3,T4} → T5 → T6 → {T7,T8} → T9 |
| implementation | 2026-08-09 | — | T1–T8 |
| verification | 2026-08-09 | — | T9; every planned activity ran, red recorded before green |
| needs-review | 2026-08-09 | pending | 3 self-review rounds below; critic rounds unavailable (no critic configured in `reviews.critics`) |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| (opened from branch `claude/github-issue-185-9utd4r`) | the whole work item — T1–T9, in `MadaraUchiha-314/the-loop` (origin and only contributing repository) | open |

## Progress entries

### 2026-08-09 — spec chain, implementation and verification

- **Phase:** requirements-definition → verification
- **Did:** wrote the four-artifact chain; shipped `pdlc-contribution-loop.yaml` (14
  nodes, 2 required gates, 2 skip sets), the goal gate (`hooks/goal.py`:
  `post-goal-request` + `classify-goal`), the `contribute` control keyword (arming +
  spawn-arming at both dispatcher seams, schema property), durable loop choice
  (`GraphState.loop`, `build_runtime(loop=…)`, GraphLink state-first resolution,
  `core/graphs.py` verbs), the `contribute-to` plugin command, the `contribution.md`
  template, and the docs sweep (README, guides, SKILL, workflow reference, two
  capability docs, config reference, decision-070).
- **Red → green:** three reds during TDD, all fixed in code, never by weakening a
  test: the goal parser rejected `**Goal:**` (bold wrapping the colon); the thread
  path dropped authorized goals because the GitHub API returns bare logins while
  allowlists conventionally carry `@` (normalised on that path only); and the walk
  test exposed both at once. See `evidence/tests.md`.
- **Next:** reviewer briefing on the PR; human review.

## Review cycles

| Round | Reviewer | Findings | Outcome |
|-------|----------|----------|---------|
| self-1 | the-loop (session) | stale "four commands" prose in `control.py` and a dispatcher comment left wrong by the widened vocabulary — fixed; confirmed the poller's `parse_command` call needs no change | fixed in-place |
| self-2 | the-loop (session) | a session spawned for a contribution item was still steered to `/the-loop:work-on` by the spawn template; gave the two human gates `command: contribute-to` so the rendered graph context names the right command — and confirmed `graph complete` routes through `advance`, so goal freezing works on the claim path too | fixed in-place |
| self-3 | the-loop (session) | history-table row initially landed above the separator row in `process-graph.md` (broken table) — fixed; pyright signature drift in two test fakes injecting `_build_runtime` — fixed; checked `checkmarks: complete` cannot trip on the template's comments | fixed in-place |
| critic-1..3 | — | not run: `reviews.critics` is empty in this repository's config (no critic harness configured); recorded per the escalation rule rather than silently skipped | n/a |

## Security review (gate)

Per `reference/security.md` and the requirements' threat model:

- **New attack surface:** one word in an existing fixed vocabulary (`contribute`), one
  new comment-reading gate (`classify-goal`). Both sit strictly behind the existing
  guards: self-authored-marker drop, then named-actor `authorizedUsers` check;
  ambiguity (two different keywords) still refuses outright. Verified by tests
  (`test_an_unauthorized_goal_is_not_read`, `test_a_self_authored_goal_is_not_read`,
  `test_contribute_plus_another_command_is_refused`).
- **Parsed text is data, never a destination:** the goal reaches graph state, a
  confirmation comment and an artifact section; no argv, path, label or routing
  target derives from it. Routing stays with declared edges.
- **Agent-writable state cannot choose arbitrary graphs:** `GraphState.loop` is
  honoured only for shipped names, at all three read sites (bootstrap, GraphLink,
  core verbs) — each fail-closed to the default and covered by a test.
- **Fail-closed defaults hold:** no goal → wait forever; empty `authorizedUsers` → no
  goal accepted; integration outage → wait, never a guess.
- **Schema change** (`keywords.contribute`) matches `sensitivePaths` → risk tier 4,
  human PR approval required before completion. **Gate: pass**, with the human
  sign-off pending on the PR (tier 4 ≥ `humanSignOffMinTier`).

## Final validation evidence

All planned verification activities ran; results in
[testing-plan.md § Verification results](testing-plan.md) and raw output in
[evidence/tests.md](evidence/tests.md): new suite 33/33, full suite 1558 passed /
1 skipped (pre-existing), ruff clean, pyright 0 errors, markdownlint 0 issues across
the 16 changed/added markdown files.

## Capability docs

- [process-graph](../../capabilities/process-graph.md) — the third loop's behaviour
  block (goal gate, one artifact, durable loop choice) + history row.
- [webhook-triggers](../../capabilities/webhook-triggers.md) — the widened control
  vocabulary + history row.

## Documentation

User-facing surfaces updated in this PR, per the issue-174 gate:

- `README.md` and `docs/guide/what-is-the-loop.md` — "Two loops" became **three**,
  with the contribution loop described.
- `docs/guide/how-it-works.md` — the shipped-graph list and repo layout.
- `skills/the-loop/SKILL.md` — the graph paragraph and the commands list
  (`/the-loop:contribute-to`).
- `skills/the-loop/reference/workflow.md` — new § *The contribution loop*.
- `docs/config/cli/routing-options.md` — `control.keywords.contribute` reference.
- New: `commands/contribute-to.md`, `skills/the-loop/templates/contribution.md`,
  `docs/decisions/decision-070.md` (+ index row).
