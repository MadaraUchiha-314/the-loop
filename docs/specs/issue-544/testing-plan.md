---
type: testing-plan
phase: test-planning
workItem: "issue-544"
status: approved             # draft | in-review | approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Testing plan: make what the-loop writes easy to read and review

## The short version

We prove the change in three ways. Automated tests cover the one piece of code: the
experiment rows, from checklist to prompt. A parity test pins the card heading in every
template. A dogfood review shows the new guidance works by applying it to this work
item's own artifacts.

The rows that carry the weight are **T1**, **T2** and **T8**. The rest are either
small or `n/a` with a reason. Every command is the project's own `make` target or
`pytest`, the same commands CI runs.

**What to check:** that each requirement has a row (see the trace), and that no row
needs a service or credential.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | Experiment rows: render, parse, the `explainer` dependency, state round-trip, prompt line, terminal `choices:`, Slack's settings classification, the request-review focus line | `cd cli && uv run python -m pytest -q tests/test_explainer_experiments.py tests/test_selection_layout.py tests/test_graphlink.py` |
| T2 | Integration (scenario) | yes | An authorized `the-loop execute` with an experiment ticked reaches the `spec-explainer` prompt; one without `explainer` does not | `cd cli && uv run python -m pytest -q tests/test_explainer_experiments_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API change; the control-plane OpenAPI is untouched | | |
| T4 | End-to-end | n/a — T2 drives the real hook, runtime and prompt renderer end to end inside the CLI; a live GitHub round-trip adds network, not coverage | | |
| T5 | UI / visual | yes | The explainer page's Slides and Flashcards tabs render, step, flip and fit at phone width | headless Chromium screenshots of the filled template (see environment) |
| T6 | Snapshot | yes | The writing parity test: every human-read template opens with `## The short version`, `design.md`'s template has the new sections, no length limit appears, and no P0 tell is present | `cd cli && uv run python -m pytest -q tests/test_writing_parity.py` |
| T7 | Performance / load | n/a — two checklist rows and static guidance; no hot path changes | | |
| T8 | Security / abuse case | yes | One negative test per boundary in `design.md` § Security design (see the trace below) | in T1 and T2 |
| T9 | Accessibility | yes | Slides and Flashcards controls are `<button>`s, keyboard-operable, with `aria-pressed` on the card and a live counter | manual keyboard walk of the filled template, recorded |
| T10 | Migration / upgrade | yes | Work items already in flight: a state file without `explainerExperiments` loads unchanged, and an old-shape `design.md` still passes the `design` node's gate | in T1: the `design` node's section check runs on a committed old-shape design (`docs/specs/issue-538/design.md`) and on the new template |
| T11 | Manual exploratory | yes | Dogfood review: this work item's own artifacts follow the new guidance, and a self-review with the standing checks finds no code-level detail in `design.md` and no process references in new production-code comments | recorded in `evidence/self-review.md` |
| T12 | Full suite (CI parity) | yes | Nothing else regressed | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R8 AC 1 | the checklist renders `explainer-slides` and `explainer-flashcards` unticked, inside the explainer section |
| T1 | R8 AC 2 | a ticked row freezes `explainerExperiments` and the confirmation names it |
| T1 | R8 AC 5 | an experiment ticked with `explainer` unticked is dropped, and the confirmation says why |
| T1 | R8 AC 6 | absent, unticked or unreadable rows mean off; an unknown `explainer-*` token is ignored |
| T1 | R8 AC 7 | Slack classifies every `explainer-*` row as a setting |
| T1 | R8 AC 3–4 | the prompt names the experiments at `spec-explainer` and `code-explainer` only |
| T1 | R3 AC 9 | the `design-approval` review request carries the focus line; other gates' messages are unchanged |
| T2 | R8 AC 2–3 | `Scenario: an authorized execute with explainer-slides ticked reaches the spec-explainer prompt` |
| T2 | R8 AC 5 | `Scenario: an experiment ticked without the explainer never reaches a prompt` |
| T5, T9 | R8 AC 3–4 | the prototype's states: Slides 1/N, Slides last, Flashcard question, Flashcard answer, phone width |
| T6 | R2 AC 1, 3, 6; R3 AC 1, 5 | parity cases on every template |
| T8 | Abuse case 1 | `Scenario: an unauthorized commenter's ticked experiment row is never frozen` (T2) |
| T8 | Abuse case 2 | the template's data blocks are rendered as text: a slide whose title contains `<img src=x onerror=…>` shows as literal text (T5, plus a unit check that the template's engine never assigns markup) |
| T8 | Abuse case 3 | unchanged issue-536 rule; covered by its existing tests, re-run in T12 |
| T8 | Abuse case 4 | guidance only: the reference text says "fall back to mermaid" and names no install step (T6 parity case) |
| T10 | R3 AC 8, NFR backward compatibility | state without the key round-trips; the `design` node's gated sections validate on both an old-shape and a new-shape design |
| T11 | R1, R2, R4, R5, R6, R7 | the guidance is applied to this work item's own artifacts and reviewed |
| T12 | all | the full suite |

## Verification environment

- **Repositories:** this one only.
- **Services / containers:** none.
- **Fixtures & data:** the existing selection and graph test fixtures; a filled copy of
  the explainer template with this work item's spec as sample content (the design
  prototype is the starting point).
- **Credentials:** none.
- **Bring-up:** `make install-dev`. **Tear-down:** none.
- **Browser for T5/T9:** the local `chromium --headless=new`. The chrome-devtools
  connection timed out during design, so headless screenshots are the plan.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T6, T12 | test summary (counts, duration) and the scenario table | `verification.md` |
| T5 | a screenshot per state; slides and flashcards are each a flow, so one animated GIF each | `ui/slides-*.png`, `ui/flashcards-*.png`, `ui/slides.gif`, `ui/flashcards.gif` |
| T9 | the keyboard walk, step by step | `verification.md` § Accessibility |
| T10 | the T1 cases by name, with their outcome | `verification.md` |
| T11 | the dogfood self-review round | `self-review.md` |

## Verification activities

- [x] T1 — `cd cli && uv run python -m pytest -q tests/test_explainer_experiments.py tests/test_selection_layout.py tests/test_graphlink.py`
- [x] T2 — `cd cli && uv run python -m pytest -q tests/test_explainer_experiments_integration.py`
- [x] T6 — `cd cli && uv run python -m pytest -q tests/test_writing_parity.py`
- [x] T5 — capture the filled template's states with `chromium --headless=new --screenshot`
- [x] T9 — walk the Slides and Flashcards tabs by keyboard only, and record each step
- [x] T10 — the backward-compatibility cases inside T1 pass (state without the key; old- and new-shape `design.md` against the `design` node's section check)
- [x] T11 — run a self-review round with the standing checks, and record it
- [x] T12 — `make check`

## Verification results

Run on 2026-11-18. Every planned activity ran and passed. Detail, screenshots and the
keyboard walk are in [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | the T1 command, with the session's `THE_LOOP_*` variables unset | pass — 99 passed | [verification.md § Test runs](evidence/verification.md#test-runs-t1-t2-t6-t10-t12) |
| T2 | the T2 command | pass — 3 scenarios | same |
| T6 | the T6 command | pass — 23 passed (P1–P10) | same |
| T5 | the filled template driven by Playwright on the local Chromium (the planned `--screenshot` flag cannot click, and the flows need clicks) | pass — every state in light and dark, phone width without overflow, the abuse-case title rendered as text with no dialog | [verification.md § UI](evidence/verification.md#ui-t5), [`ui/`](evidence/ui/) |
| T9 | keyboard-only walk, 15 steps, focus and ARIA state read after each | pass — every step as expected | [verification.md § Accessibility](evidence/verification.md#accessibility-t9) |
| T10 | five named cases inside T1 | pass | [verification.md § Test runs](evidence/verification.md#test-runs-t1-t2-t6-t10-t12) |
| T11 | dogfood self-review with both standing checks | pass — zero findings | [self-review.md](evidence/self-review.md) |
| T12 | `make check`, clean environment | pass — exit 0, 7,043 passed | [verification.md § Test runs](evidence/verification.md#test-runs-t1-t2-t6-t10-t12) |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.

### 2026-11-18 — approved

**@MadaraUchiha-314** wrote:

approved
