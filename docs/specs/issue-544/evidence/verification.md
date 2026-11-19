---
type: evidence
workItem: "issue-544"
---

<!-- Written per the `the-loop:writing` skill. -->

# Verification: make what the-loop writes easy to read and review

## The short version

Every activity in `testing-plan.md` ran and passed. The full suite (`make check`) is green
in a clean environment: 7,043 tests, plus lint, format, types and markdownlint. The
explainer page's Slides and Flashcards tabs render, step, flip and fit at phone width, in
light and dark themes. A slide whose title holds an `<img onerror>` payload shows it as
text and fires nothing. The whole walk works by keyboard alone.

The plan's results table holds the per-activity outcome; this file holds the detail.

## Test runs (T1, T2, T6, T10, T12)

All on 2026-11-18, from `cli/`, with this session's `THE_LOOP_*` variables unset so the
operator's own CLI config cannot leak into the tests (CI has none).

| Row | Command | Outcome |
|---|---|---|
| T1 | `uv run python -m pytest -q tests/test_explainer_experiments.py tests/test_selection_layout.py tests/test_graphlink.py` | 99 passed |
| T2 | `uv run python -m pytest -q tests/test_explainer_experiments_integration.py` | 3 passed |
| T6 | `uv run python -m pytest -q tests/test_writing_parity.py` | 23 passed (P1–P10) |
| T10 | the five backward-compatibility cases below, inside T1 | 5 passed |
| T12 | `make check` (repository root) | exit 0; 7,043 passed; ruff, pyright and markdownlint clean |

**Scenarios (T2):**

| Scenario | Outcome |
|---|---|
| an authorized execute with explainer-slides ticked reaches the spec-explainer prompt | pass |
| an experiment ticked without the explainer never reaches a prompt | pass |
| an unauthorized commenter's ticked experiment row is never frozen | pass |

**Backward compatibility (T10):**

| Case | Outcome |
|---|---|
| `test_state_without_the_key_loads_unchanged` | pass |
| `test_a_hand_edited_unknown_value_is_dropped_on_load` | pass |
| `test_the_design_gate_sections_validate_on_old_and_new_designs[old-shape]` (`docs/specs/issue-538/design.md`) | pass |
| `…[new-shape]` (`docs/specs/issue-544/design.md`) | pass |
| `…[new-template]` (`skills/the-loop/templates/design.md`) | pass |

Snapshot changes, reviewed: the two handoff checklist goldens and the Jira checklist
goldens gain exactly the experiments lead-in and two unticked rows; the Jira PR-briefing
goldens follow the new briefing template.

**Environment note.** Run with this session's environment, 22 tests about the poller,
instances, `ask` and critic policy fail, because `THE_LOOP_CLI_CONFIG` points at the
operator's real config. With the variables unset they pass (109 passed), and the change
touches none of them.

## UI (T5)

The explainer template, filled with this work item's slides and cards, captured with
Playwright driving the local Chromium (the chrome-devtools connection timed out during
design).

| State | Light | Dark |
|---|---|---|
| Slide 1 / 4 | [png](ui/slides-1-light.png) | [png](ui/slides-1-dark.png) |
| Slide 3, the abuse-case title | [png](ui/slides-3-light.png) | [png](ui/slides-3-dark.png) |
| Slide 4 / 4, Next disabled | [png](ui/slides-4-light.png) | [png](ui/slides-4-dark.png) |
| Card 1, question / answer | [q](ui/flashcards-1-question-light.png) · [a](ui/flashcards-1-answer-light.png) | [q](ui/flashcards-1-question-dark.png) · [a](ui/flashcards-1-answer-dark.png) |
| Phone width (390px) | [slides](ui/slides-phone.png) · [cards](ui/flashcards-phone.png) | |

Flows: [slides.gif](ui/slides.gif), [flashcards.gif](ui/flashcards.gif).

- **Abuse case 2:** slide 3's title `<img src=x onerror=alert(1)>` rendered as text; the
  panel holds 0 `img` elements and no dialog fired during the run.
- **Phone width:** no horizontal overflow.
- Every card click set `aria-pressed="true"`; the last slide's Next is disabled.

## Accessibility (T9)

Keyboard only, from page load. Each row is one step.

| Keys | Expected | Focused | Selected tab | Live counter | Card `aria-pressed` |
|---|---|---|---|---|---|
| Tab | first tab focused | button#tab-spec[role=tab] "Spec explainer" | tab-spec |  | None |
| ArrowRight ArrowRight ArrowRight ArrowRight | Slides tab selected | button#tab-slides[role=tab] "Slidesexperiment" | tab-slides | Slide 1 / 4 | None |
| Tab | slide deck focused | div "slide deck" | tab-slides | Slide 1 / 4 | None |
| ArrowRight | slide 2 | div "slide deck" | tab-slides | Slide 2 / 4 | None |
| ArrowLeft | slide 1 | div "slide deck" | tab-slides | Slide 1 / 4 | None |
| Tab | Next (Previous is disabled on slide 1) | button "Next" | tab-slides | Slide 1 / 4 | None |
| Enter | slide 2 | button "Next" | tab-slides | Slide 2 / 4 | None |
| Shift+Tab | Previous, now enabled | button "Previous" | tab-slides | Slide 2 / 4 | None |
| Shift+Tab Shift+Tab | deck, then Slides tab | button#tab-slides[role=tab] "Slidesexperiment" | tab-slides | Slide 2 / 4 | None |
| ArrowRight | Flashcards tab selected | button#tab-cards[role=tab] "Flashcardsexperiment" | tab-cards | Card 1 / 3 | false |
| Tab | card focused | button "Question" | tab-cards | Card 1 / 3 | false |
| Space | card flipped to the answer | button "Answer" | tab-cards | Card 1 / 3 | true |
| Enter | card flipped back | button "Question" | tab-cards | Card 1 / 3 | false |
| Tab | Next | button "Next" | tab-cards | Card 1 / 3 | false |
| Enter | card 2 | button "Next" | tab-cards | Card 2 / 3 | false |

Every step matched its expectation.

## Dogfood review (T11)

Recorded in [`self-review.md`](self-review.md), round 1.
