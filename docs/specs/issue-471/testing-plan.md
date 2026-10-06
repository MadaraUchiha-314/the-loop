---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#471"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: publish a work item's spec chain as one Claude artifact

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (gate render) | yes | the outer loop's checklist carries an unticked `claude-artifact` row and the "`claude` harness only" note; a contribution's carries neither | `cli/tests/test_claude_artifact.py` |
| T2 | Unit (gate resolve) | yes | ticked + default harness `claude` → `claudeArtifact: true`; ticked + chosen harness `codex` → `false` and the confirmation names `codex`; ticked + unknown harness → `true`; unticked → `false` and "markdown files only"; never a skip, opt-in or refusal; a contribution's reply carrying the row → `false` | same |
| T3 | Unit (state) | yes | `claudeArtifact` round-trips; absent, `"true"`, `1` read as `false` | same |
| T4 | Unit (runtime freeze) | yes | a selection through `Runtime` records `claudeArtifact` in state and in the decision record | same |
| T5 | Unit (prompt) | yes | the graph block carries the publish line for an outer-loop item with `claude_artifact`, and not for a PR, contribution, ad-hoc, review item or `false` | same |
| T6 | Unit (Slack mirror) | yes | `selection_rows` puts `claude-artifact` in `others`, not `phases`; the pin test asserts the constants agree | `cli/tests/test_selection_control.py` |
| T7 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint | repository checks |
| T8 | Security | yes (review) | authorization unchanged, boolean-only read, no gate answer from an artifact, no CLI publication | `evidence/security-review.md` |
| T9 | Integration (Gherkin) | n/a | no new ingress or seam; the gate's existing Gherkin integration paths are unchanged and run in T7 | |
| T10 | Manual (publish an artifact) | n/a | publishing is a Claude Code session tool, outside the CLI; the CLI's contract ends at the prompt line (T5) | |
| T11 | UI / accessibility / snapshot / migration / performance | n/a | no UI; the state key is additive and absent reads as `false`, so no migration; one boolean per selection | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1–R1.4 | T1, T2 |
| R1.5 | T6 |
| R2.1–R2.5 | T2 |
| R3.1, R3.2 | T3, T4 |
| R3.3 | T7 (archive suite) |
| R4.1, R4.2 | T5 |
| R4.3–R4.5 | review of the skill text (`evidence/self-review.md`) |

## Verification environment

This checkout, Python via `uv`, the repository's own `make` targets. No service, fixture
or credential beyond the test doubles the suite already uses.

## Not covered by an automated test

Whether a Claude Code session publishes a good page from the prompt line. That is the
session's behaviour under the skill, judged on the first work item that ticks the box.
