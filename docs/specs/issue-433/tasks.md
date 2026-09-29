---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#433"
status: approved
approvedBy: ["the-loop"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: two bugs in the `hooks[]` declaration loader

> Phase 4 of 4. Each task names the acceptance criterion it satisfies and the
> testing-plan row that proves it. Bug 2 is fixed in the same change as bug 1 because it
> is the reason bug 1 was invisible: a fixed bug 1 alone would leave the next non-string
> key raising the same `TypeError`.

- [x] **A0 — reproduce.** Run the ticket's three snippets on `main`; confirm the `True`
      key from `yaml.safe_load`, the `TypeError` from `read_declaration`, and the
      `could not read … TypeError` from `the-loop hooks`. *AC:* R2.3 · *Test:* T5.
- [x] **A1 — normalise the key.** `declaration.py` gains `_normalise_keys`, called in
      `_read_entry` after the `name` check and before the unknown-key check: `True → "on"`,
      every other key kept; both spellings together refused with a message naming the
      entry. *AC:* R1.1–R1.3 · *Test:* T1, T2.
- [x] **A2 — make the refusal total.** `unknown` is sorted by `repr` and rendered with
      `repr`, so the refusal is a `HooksConfigError` for any key type and names every
      offending key. *AC:* R2.1, R2.2 · *Test:* T3.
- [x] **B1 — regression tests, loader.** `test_lifecycle_declaration.py`: the documented
      entry through `yaml.safe_load` with its premise pinned; quoted `"on"` and the
      both-spellings refusal; non-string unknown keys, parametrised, and the mixed-type
      case. *Deps:* A1, A2 · *AC:* R1.4, R2.3 · *Test:* T1–T3, T5.
- [x] **B2 — regression test, command.** `test_hooks_cmd.py`: the ticket's reproduction
      through a real YAML file and `the-loop hooks --format json`. *Deps:* A1 ·
      *AC:* R1.5 · *Test:* T4.
- [x] **C1 — docs.** `docs/config/cli/hooks-options.md` § `hooks[].on` says both
      spellings load and why; `docs/capabilities/lifecycle-hooks.md` gains the requirement
      under *Declaration and loading* and a history row. The guide, the shipped commented
      example and the JSON schema are unchanged on purpose (`bugfix.md` § Out of scope).
      *Deps:* A1, A2 · *Test:* T8.
- [x] **D1 — verify and record.** Full suite from `cli/`, `ruff`, `pyright`,
      `markdownlint`; `evidence/verification.md` with raw output including the negative
      control; `self-review.md`, `security-review.md`, `documentation.md`,
      `reviewer-briefing.md`. *Deps:* A1–C1 · *Test:* T5–T8.
