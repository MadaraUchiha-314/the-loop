---
type: testing-plan
phase: test-planning
workItem: issue-165
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: write the-loop's artifacts for a human reader

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content.** Review the commands like code. No credentials are
> involved — every command reads this repository and nothing else.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `test_writing_parity.py` P1–P6: skill present, markers well-formed, markers == schema defaults, skill and every template within their own budgets, no P0 tell in shipped prose | `make test` |
| T2 | Integration (scenario) | n/a — the change adds no runtime path. Nothing is dispatched, routed or spawned; there is no cross-module behaviour to document with a Gherkin scenario. | | |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface added. `docs/api-specs/openapi` is untouched. | | |
| T4 | End-to-end | n/a — no user-invocable flow. The skill is read by an agent, not executed. | | |
| T5 | UI / visual | n/a — no user-facing surface (`design.uiArtifacts` produces nothing for docs/CLI work). | | |
| T6 | Snapshot | n/a — no rendered output to freeze. | | |
| T7 | Performance / load | n/a — filesystem reads in a test; no runtime cost. | | |
| T8 | Security / abuse case | yes | the abuse cases in `design.md` §Security design: a style pass cannot rewrite a record (P5's glob excludes `docs/specs/` and `evidence/`), and a malformed marker fails rather than skips | `make test` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | a project scaffolded before this change has no `writingStyle` block; schema defaults must make absence and default the same state | `make validate` |
| T11 | Manual exploratory | yes | read the rendered `SKILL.md` and one budgeted template as a reviewer would, and confirm the contract is findable without reading the spec | manual |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3 | the writing skill exists, front-matter parses, `reference/tells.md` present |
| T1 | R2.1 | every budgeted template declares a well-formed marker |
| T1 | R2.1, R5.1 | marker values equal the schema's `writingStyle.budgets` defaults |
| T1 | R1.2, NFR | `SKILL.md` prose is within its own declared budget |
| T1 | R2.1, R2.3 | every template's own prose fits the budget it declares — a budget the scaffold busts is unreachable |
| T1 | R5.2 | no P0 tell in shipped prose — `skills/`, `commands/`, `rules/`, `README.md` and `docs/` minus the historical (`docs/specs/`) and generated trees |
| T8 | R2.4, abuse case 2 | budgeted templates still carry their gated sections |
| T8 | abuse case 1 | P5's scan excludes `docs/specs/` and `evidence/` |
| T10 | R5.1 | `.the-loop/harness-config.yaml` and the shipped template both validate against the schema |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none.
- **Fixtures & data:** none — the test reads checked-in files.
- **Credentials:** none. No command here touches a secret.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | pytest summary for the new test plus the full suite | `unit.txt` |
| T10 | `make validate` output (both configs against the schema) | `validate.txt` |
| all | `make lint` + `make typecheck` + `make format-check` output | `checks.txt` |
| T11 | the manual read-through finding | Verification results, below |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py`
- [x] T1/T8 — `make test` (full suite: no regression from the schema and template edits)
- [x] T10 — `make validate`, plus the absent-block and rejected-key cases
- [x] all — `make lint`, `make format-check`, `make typecheck`
- [x] T11 — read `skills/writing/SKILL.md` and `skills/the-loop/templates/design.md` as a
      reviewer; record whether the budget and the skill are findable without the spec
- [x] extra — measure every artifact this PR ships against the budgets it introduces

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py` | 21 passed | [`evidence/unit.txt`](evidence/unit.txt) |
| T1/T8 | `make test` | 1349 passed, 1 skipped | [`evidence/unit.txt`](evidence/unit.txt) |
| T10 | `make validate` + a config with `writingStyle` removed, an unknown budget key, and a typo'd formal register | both configs valid; the pre-issue-165 shape still validates; the unknown key and the typo'd register are both rejected | [`evidence/validate.txt`](evidence/validate.txt) |
| all | `make lint`, `make format-check`, `make typecheck` | ruff clean · markdownlint 0 errors over 420 files · pyright 0 errors | [`evidence/checks.txt`](evidence/checks.txt) |
| T11 | read `SKILL.md` and `templates/design.md` as a reviewer | the budget is visible where the artifact is authored (first lines of the template) and names the skill governing it; no need to open the spec. Finding recorded below. | this table |
| extra | `prose_words()` over every artifact this PR ships | all inside budget after one revise pass; two overruns found and cut | [`evidence/budgets.txt`](evidence/budgets.txt) |

**T11 finding (fixed during verification):** the first draft set `tasks: 200` against a
`tasks.md` template whose own guidance prose is 274 words — every `tasks.md` would have
opened over budget. The budget is now 400, and **P6** was added so an unreachable budget is
a red build rather than a discovery. Two further overruns (`requirements.md` at 682,
`design.md` at 1017) were cut rather than excused; see `evidence/budgets.txt`.

**Not executed:** none. Every in-scope activity ran.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
