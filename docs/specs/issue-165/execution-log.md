---
type: execution-log
workItem: issue-165
phase: needs-review          # not-started | brainstorming | requirements-definition | design | test-planning | tasks-breakdown | implementation | verification | needs-review | complete
status: in-progress          # in-progress | complete
---

# Execution Log: write the-loop's artifacts for a human reader

> Append-only log of progress. Mirrors the `loop:<phase>` label on
> [issue #165](https://github.com/MadaraUchiha-314/the-loop/issues/165).

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| brainstorming | 2026-08-06 | — | Literature survey (issue bullet 5) recorded in `brainstorm.md` |
| requirements-definition | 2026-08-06 | pending (PR) | 5 requirements; risk tier raised to 4 by `sensitivePaths` |
| design | 2026-08-06 | pending (PR) | Skill + config + template markers + parity test |
| test-planning | 2026-08-06 | pending (PR) | 4 of 11 matrix rows in scope |
| tasks-breakdown | 2026-08-06 | pending (PR) | 7 tasks |
| implementation | 2026-08-06 | — | |
| verification | 2026-08-06 | — | Every in-scope activity ticked; results and evidence recorded |
| needs-review | 2026-08-06 | pending (PR) | 3 self-review rounds; critic rounds unavailable; security review passed, human sign-off pending. the owner's review round then removed length budgets — see below |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| #168 | all tasks (1–7) | open |

## Progress entries

### 2026-08-06 — spec chain authored and locked

- **Phase:** tasks-breakdown → implementation
- **Did:** surveyed the prior art the ticket asked for (four skills, two style
  traditions) and recorded it in `brainstorm.md`; derived requirements, design, testing
  plan and tasks. Settled the shape: a bundled skill carries the judgement, the config
  carries the policy, the templates carry the budget, a parity test catches drift.
- **Checkpoint/tests:** none yet — no code written.
- **Next:** task 1, land `cli/tests/test_writing_parity.py` red.
- **Blockers:** none. Two open questions raised for the reviewer on the PR.

### 2026-08-06 — implementation complete

- **Phase:** implementation → verification
- **Did:** tasks 1–6. Test first and red, then the skill, the schema and both configs,
  the template markers, the operating-model wiring, the docs fold-in.
- **Checkpoint/tests:** `make test`, `make lint`, `make format-check`, `make typecheck`,
  `make validate` — see `evidence/`.
- **Next:** task 7, execute the testing plan and record results.
- **Blockers:** none.

### 2026-08-06 — verification complete

- **Phase:** verification → needs-review
- **Did:** executed every in-scope activity of `testing-plan.md`, ticked them, filled the
  results table, committed the evidence. Verification itself produced the T11 finding —
  the `tasks` budget was unreachable from its own template — which became P6 and a
  corrected budget rather than a note.
- **Checkpoint/tests:** all green; see `testing-plan.md` §Verification results.
- **Next:** self-review rounds, then the human gate (risk tier 4).
- **Blockers:** named human security sign-off required
  (`security.review.humanSignOffMinTier: 4`) — requested in the PR briefing.

### 2026-08-06 — owner review: length budgets removed

- **Phase:** needs-review (iterating on the PR, per the artifact-iteration invariant)
- **Did:** the owner rejected per-artifact word budgets on PR #168. Removed them from the
  schema, both configs, the eight templates, the skill and the test; replaced the budget
  markers with a pointer naming the governing skill; rewrote requirements R2, the design,
  the testing plan and decision-061 to match, and added P3's guard against budgets
  returning unremarked. Also fixed the `gate` CI failure: `brainstorm.md` had renamed the
  `Problem / opportunity` section the process graph requires.
- **Checkpoint/tests:** `make check` green; `the-loop check issue-165 --recompute` now
  reaches `requirements-approval` (WAIT — the normal state of an open PR).
- **Next:** the human gate.
- **Blockers:** approval + named security sign-off (risk tier 4).

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | 3 new findings, all fixed | this PR |
| 2 | self | the-loop | 2 new findings, both fixed | this PR |
| 3 | self | the-loop | zero new — stop (`reviews.stopOnNoNewFindings`) | this PR |
| — | critic | — | unavailable (`reviews.critics: []` — none configured, so the round does not count toward `criticReviewCount`) | — |
| 4 | security | the-loop checklist | pass; human sign-off pending | this PR |
| 5 | human (owner) | @MadaraUchiha-314 | 1 finding — budgets rejected; implemented | [PR #168](https://github.com/MadaraUchiha-314/the-loop/pull/168) |

**Round 1 — measuring this work item's own artifacts against the budgets it ships.** Three
findings, in order of severity:

1. **The `tasks` budget was unreachable.** 200 words, against a `tasks.md` template whose
   own guidance prose is 274 — every `tasks.md` would have opened over budget, and an
   unreachable budget teaches authors to ignore the reachable ones. Budget raised to 400,
   and **P6** added so the class of defect is a red build rather than a discovery.
2. **A wrapped EARS criterion was only half-excluded.** The counter matched the first line
   and counted the indented continuation, so a long `SHALL` cost words — exactly the
   pressure D3 exists to prevent. The counter now skips an item's continuation lines.
3. **Two artifacts were over budget** — `requirements.md` at 682/500 and `design.md` at
   1017/900. Cut with the skill's own revise pass rather than excused; final numbers in
   `evidence/budgets.txt`.

**Round 2 — reading the test as a reviewer would.** Two findings:

1. **P2 hardcoded the skill name** `the-loop:writing` while the schema also declares it as
   `writingStyle.skill`'s default. Two sources for one string. The test now reads the
   schema, so a rename is one edit.
2. **P5 scanned too little.** It covered `skills/`, `commands/`, `rules/` and `README.md`
   but not `docs/` — where the published site lives, and where "everything presented to the
   user" mostly is. Widened to `docs/`, explicitly excluding `docs/specs/` (the historical
   record — a build that can go red over the style of a committed spec is the "a style pass
   rewrites a record" abuse case) and `docs/operating-model/reference/` (a build-time copy
   of a tree already scanned).

**Round 3:** no new findings. `pyright` caught one typing slip during verification
(`Dict[str, object]` where the values are indexed) — fixed, and it is a check result rather
than a review finding.

**Round 5 — the owner's review on PR #168. One finding, and it removed a third of the
change:**

> We don't know the scope of each work item, so how can we put budgets on requirements.md
> or design.md? Let's not enforce budgets.

Accepted without argument, because round 1's own findings were the evidence for it: three
of the eight budgets had to be renegotiated before the change could even merge. Removed
the `budgets` block from the schema and both configs, replaced each template's
`<!-- writing: budget=N -->` marker with a pointer naming the governing skill, cut P2/P3/P6
down to a pointer-parity pair, and dropped the word counter. What survives is
scope-independent: the spine, the revise pass, the density test, diagram-first, the formal
carve-out and the tells catalogue.

P3 gained a second assertion in exchange — `writingStyle.budgets` must stay **absent**, so
re-adding length limits is a decision someone records rather than a detail that arrives
beside an unrelated schema edit. Rationale and evidence:
[decision-061](../../decisions/decision-061.md) §D2.

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no
  security-review skill invoked for a docs/test change with no runtime path).
- **Outcome:** pass. No new attack surface: nothing added is reachable at runtime, the
  test performs filesystem reads with no `eval`/subprocess/network, and every added config
  key is declarative — none becomes an argv the way `reviews.critics[]` does. Both abuse
  cases from `requirements.md` have a mechanism and a test (P5's glob boundary; the gates
  themselves for section deletion).
- **Human sign-off:** pending — effective tier 4 (`autonomy.sensitivePaths` matched
  `.the-loop/harness-config.yaml` and `harness-config.schema.json`), which is ≥
  `security.review.humanSignOffMinTier`. Requested in the PR briefing.

## Final validation evidence

Every acceptance criterion maps to a green check, recorded in
[`testing-plan.md`](testing-plan.md) §Verification results with the exact command and the
committed artifact under [`evidence/`](evidence/):

- **R1** (bundled skill) — P1: `skills/writing/SKILL.md` parses, `reference/tells.md`
  present. R1.4 (register, don't vendor) — the three surveyed skills are registered under
  `externalTools` in this repository's own config, with notes recording what was and was
  not taken from each; the shipped template keeps its minimal starter registry.
- **R2** (the contract reaches the author) — P2 and P3: eight human-read templates, each
  naming the skill the schema declares. R2.2 (no length limits) is asserted by P3's second
  half; `evidence/budgets.txt` is the record of the rejected approach that produced it.
- **R3** (diagram-first) — asserted by review, not by the test (R5.3). `design.md` and
  `tasks.md` for this work item each carry one.
- **R4** (formal carve-out) — the five registers are enum values in the schema; the skill
  states the carve-out; this work item's own EARS criteria are unchanged in form.
- **R5** (config + test) — `make validate` on both configs, plus the absent-block and
  rejected-key cases; P1–P4 green in `make test`.
- **NFR** — no new dependency; `SKILL.md` stays short enough to read in full before use.
