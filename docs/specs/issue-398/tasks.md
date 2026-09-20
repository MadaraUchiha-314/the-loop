---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#398"
status: approved
approvedBy: ["the-loop"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: a logo for the-loop — five hand-drawn SVG options to choose from

> Phase 4 of 4. Each task names the requirement it satisfies and the testing-plan row
> that proves it. For a design deliverable the "test" is the generator's own checker and
> the rendered evidence; the checker was run red (six `missing`) before the first render
> and green after it.

## Task list

- [x] **A1 — the generator's core.** `design/generate.py`: `Wobble`, `trace`, `pen`,
      `outline`, `spline`; curves `ellipse`, `circle`, `epitrochoid`; `stroke`, `dot`;
      `svg_file` with `currentColor` ink, `<title>`/`<desc>`, the one dark-scheme rule.
      _Depends on:_ none · _Requirements:_ R2.1, R3.1, R3.3, R3.4 · _Test:_ T1
      (`generate.py --check`, red → green).
- [x] **A2 — the five options.** `option_gimbal`, `option_one_line`, `option_coil`,
      `option_rings`, `option_planetary`: one concept sentence, the element meanings, the
      geometry, a fixed seed each. Iterated on the rendering (coil: 12 → 16 → 18 loops,
      d 1.9 → 1.5; one line: d 1.75 → 2.15; gimbal: inner ring shrunk; planetary:
      chevrons dropped — they were illegible below 48 px). _Depends on:_ A1 ·
      _Requirements:_ R1.1–R1.3, R2.2, R2.3 · _Test:_ T1, T5.
- [x] **A3 — the checker.** `--check`: bytes match, well-formed, titled, no forbidden
      token, non-fragment `href` refused, ≤ 40 000 bytes, deterministic; exit 1 on any
      failure. _Depends on:_ A1 · _Requirements:_ R3.1, R3.3, abuse case 1 · _Test:_ T1,
      T8.
- [x] **B1 — the gallery.** `gallery()` → `design/logo-options.html`: self-contained, no
      script; palette row; per option — paper board, slate board, 96/48/24/16 px, the
      lockup, the concept, the meanings, how it is drawn; one `<symbol>` per option (two
      for the blended one) and `<use>` everywhere else. _Depends on:_ A2 ·
      _Requirements:_ R4.1, R3.2 · _Test:_ T1 (self-containment), T5.
- [x] **B2 — the screenshot evidence.** `design/screenshots.mjs` (Playwright + the
      Chromium the dashboard's evidence script already uses): the gallery in both
      schemes, each SVG as an `<img>` on paper (light) and slate (dark) →
      `design/screenshots/*.png`. _Depends on:_ B1 · _Requirements:_ R4.2, R3.4 ·
      _Test:_ T5.
- [x] **C1 — the spec chain and its evidence.** `requirements.md`, `design.md` (with
      the UI/UX inventory), `testing-plan.md` (results filled at verification),
      this file; `evidence/` — automated tests, self-review, security review,
      documentation, reviewer briefing. _Depends on:_ A3, B2 · _Test:_ T12
      (markdownlint).
- [ ] **D1 — present for the pick.** Push, open the PR with the reviewer briefing as its
      body, comment on the ticket with the gallery, the SVGs and the PR, and rest the
      label at `loop:needs-review`. _Depends on:_ C1 · _Requirements:_ R4.3, R4.4 ·
      _Test:_ T11 (the owner's, on the ticket).

## Dependency graph (DAG)

```text
A1 → A2 → B1 → B2 → C1 → D1
A1 → A3 ────────────↗
```

## Checkpoints

- After A3: `python3 docs/specs/issue-398/design/generate.py --check` green.
- After B2: the twelve PNGs exist and the dark-scheme `<img>` captures show the light ink.
- After C1: markdownlint on `docs/specs/issue-398/**/*.md`, ruff on the generator, and a
  regeneration leaving the tree clean (T6) — recorded in `evidence/automated-tests.md`.
- D1 is the hand-off: nothing after it is this PR's to tick.

## Review comments

None yet.
