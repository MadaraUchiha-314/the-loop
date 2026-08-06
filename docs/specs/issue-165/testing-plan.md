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
| T1 | Unit | yes | `test_writing_parity.py` P1–P4: skill present and parsing, every human-read template points at it, the pointer names the skill the schema declares and no length limits have returned, no P0 tell in shipped prose | `make test` |
| T2 | Integration (scenario) | n/a — the change adds no runtime path. Nothing is dispatched, routed or spawned; there is no cross-module behaviour to document with a Gherkin scenario. | | |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface added. `docs/api-specs/openapi` is untouched. | | |
| T4 | End-to-end | n/a — no user-invocable flow. The skill is read by an agent, not executed. | | |
| T5 | UI / visual | n/a — no user-facing surface (`design.uiArtifacts` produces nothing for docs/CLI work). | | |
| T6 | Snapshot | n/a — no rendered output to freeze. | | |
| T7 | Performance / load | n/a — filesystem reads in a test; no runtime cost. | | |
| T8 | Security / abuse case | yes | the abuse cases in `design.md` §Security design: a style pass cannot rewrite a record (P4's glob excludes `docs/specs/` and `evidence/`), and a missing or wrong-skill pointer fails rather than skips | `make test` |
| T9 | Accessibility | n/a — no UI. | | |
| T10 | Migration / upgrade | yes | a project scaffolded before this change has no `writingStyle` block; schema defaults must make absence and default the same state | `make validate` |
| T11 | Manual exploratory | yes | read the rendered `SKILL.md` and one human-read template as a reviewer would, and confirm the contract is findable without reading the spec | manual |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.3 | the writing skill exists, front-matter parses, `reference/tells.md` present |
| T1 | R2.1 | every human-read template names the governing skill |
| T1 | R2.1, R5.1 | the pointer names the skill `writingStyle.skill` declares |
| T1 | R2.2, R5.1 | `writingStyle.budgets` is absent — length limits cannot return unremarked |
| T1 | R5.2 | no P0 tell in shipped prose — `skills/`, `commands/`, `rules/`, `README.md` and `docs/` minus the historical (`docs/specs/`) and generated trees |
| T8 | R2.4, abuse case 2 | human-read templates still carry their gated sections |
| T8 | abuse case 1 | P4's scan excludes `docs/specs/` and `evidence/` |
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
| T1, T8 | pytest summary for the new test plus the full suite | `unit.md` |
| T10 | `make validate` output (both configs against the schema) | `validate.md` |
| all | `make lint` + `make typecheck` + `make format-check` output, plus the-loop's own gate | `checks.md` |
| T11 | the manual read-through finding | Verification results, below |

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py`
- [x] T1/T8 — `make test` (full suite: no regression from the schema and template edits)
- [x] T10 — `make validate`, plus the absent-block and rejected-key cases
- [x] all — `make lint`, `make format-check`, `make typecheck`
- [x] T11 — read `skills/writing/SKILL.md` and `skills/the-loop/templates/design.md` as a
      reviewer; record whether the contract is findable without the spec

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run --project cli python -m pytest -q cli/tests/test_writing_parity.py` | 21 passed | [`evidence/unit.md`](evidence/unit.md) |
| T1/T8 | `make test` | 1349 passed, 1 skipped | [`evidence/unit.md`](evidence/unit.md) |
| T10 | `make validate` + a config with `writingStyle` removed, an unknown key under `writingStyle`, and a typo'd formal register | both configs valid; the pre-issue-165 shape still validates; the unknown key and the typo'd register are both rejected | [`evidence/validate.md`](evidence/validate.md) |
| all | `make lint`, `make format-check`, `make typecheck` | ruff clean · markdownlint 0 errors over 420 files · pyright 0 errors | [`evidence/checks.md`](evidence/checks.md) |
| T11 | read `SKILL.md` and `templates/design.md` as a reviewer | the contract is visible where the artifact is authored (first lines of the template) and names the skill governing it; no need to open the spec | this table |
| — | the budget experiment that preceded the current design | recorded for the record: it is what showed the numbers to be unworkable | [`evidence/budgets.md`](evidence/budgets.md) |

**T11 finding, and what it cost the design.** Verification measured every artifact this PR
ships against the budgets it then proposed, and three of them did not hold: `tasks: 200`
was unreachable from its own 274-word empty template, `requirements.md` ran 682/500 and
`design.md` 1017/900. The numbers were corrected and a sixth assertion added to keep
budgets reachable — and then the owner rejected budgets outright on PR #168, for the
underlying reason those corrections were evidence of. Length limits are gone; the record
of the experiment is [`evidence/budgets.md`](evidence/budgets.md) and
[decision-061](../../decisions/decision-061.md) §D2.

**Not executed:** none. Every in-scope activity ran, and re-ran after the budgets were
removed.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
