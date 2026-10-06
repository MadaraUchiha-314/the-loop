---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#472"
status: in-review
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: make the phase-selection comment easier to read

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md). The
> results are in [`evidence/verification.md`](evidence/verification.md).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (layout) | yes | the shipped outer loop's checklist opens with the `##` title and the quick start, has the phase and settings group headings and a `####` heading per offered question, each opened by an emoji no other heading uses, and ends with the "Ready?" section, the marker and the stamp | `cli/tests/test_selection_layout.py` |
| T2 | Unit (defaults and details) | yes | every setting section has a `**Default:**` line before its rows; every `<details>` is balanced and holds no row; the explanations kept from before are present | same |
| T3 | Unit (contract) | yes | the rows are byte-identical in shape and order to the graph's lists; `selection_rows` reads the same phases, surface, others and `always` (only the protected phases) | same |
| T4 | Unit (contribution) | yes | a contribution's checklist has no surface or artifact section and says why, under the settings group | same |
| T5 | Unit (Slack digest) | yes | `to_mrkdwn` and `condense` drop `<details>` tags and draw `<summary>` as bold; HTML in a code span or fence is left alone | `cli/tests/test_channels_digest.py` |
| T6 | Regression (full suite + hooks) | yes | ruff, ruff format, pyright, all CLI tests, markdownlint | repository checks |
| T7 | Rendered evidence | yes | the before and after comments, committed as markdown so GitHub renders them | `evidence/checklist-before.md`, `evidence/checklist-after.md` |
| T8 | Security | yes (review) | no authorization, parse or freeze path changed; no HTML a reader can inject reaches the comment | `evidence/security-review.md` |
| T9 | Integration (Gherkin) | n/a | no new ingress or seam; the gate's integration paths run unchanged in T6 | |
| T10 | UI / accessibility / snapshot / migration / performance | n/a | the-loop has no product UI; the comment's headings and plain-text summaries are screen-reader friendly by construction; no state changes | |

## Requirement trace

| Requirement | Tests |
|-------------|-------|
| R1.1–R1.3 | T1 |
| R1.4 | T4 |
| R2.1–R2.5 | T1, T2, T7 |
| R3.1–R3.3 | T3, T6 |
| R3.4 | T5 |

## Verification environment

This checkout, Python via `uv`, the repository's own `make` targets. GitHub is the tests'
fake. No service or credential is needed.
