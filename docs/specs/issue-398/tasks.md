---
type: tasks
phase: tasks-breakdown
workItem: "github:MadaraUchiha-314/the-loop#398"
status: approved
approvedBy: ["the-loop"]
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Tasks: a logo for the-loop — the Ensō, in colourways, to choose from

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
- [x] **D1 — present for the pick.** Push, open the PR with the reviewer briefing as its
      body, comment on the ticket with the gallery, the SVGs and the PR, and rest the
      label at `loop:needs-review`. _Depends on:_ C1 · _Requirements:_ R4.3, R4.4 ·
      _Test:_ T11 (the owner's, on the ticket).

### Round 2 — after the owner's review of round 1

> _"Over stressed on the hand drawn part; no character."_ The design-artifacts loop:
> fold the feedback into the artifact and re-present.

- [x] **E1 — the brush and the weave.** `brush()` (nib angle, contrast, pressure, lifts),
      `enso_brush()`, `by_arc_length()`, `catmull_points()`, `woven()` with numeric
      `crossings()` and a `<mask>`, `arrowhead()`; `outline()` clamps the offset to the
      local curvature and fills `nonzero`. _Depends on:_ A1 · _Requirements:_ R2.1
      (revised) · _Test:_ T1.
- [x] **E2 — five marks with a character each.** `option_loop_word`, `option_knot`,
      `option_flick`, `option_clip`, `option_enso`, iterated on the rendering (fill
      rule and curvature clamp for holes at tight curls; contrast down from 0.5–0.6 to
      0.32–0.45; the brush reading progress along the stroke; knot gap 3.0 → 2.2; a
      plain chevron the stroke ends inside; ensō bases 16/13/9.5). Budget 40 → 64 kB.
      _Depends on:_ E1 · _Requirements:_ R1.1–R1.3 (sharpened), R2 · _Test:_ T1, T5.
- [x] **E3 — the record.** `design.md` (round-2 overview, components, inventory with
      round 1 marked superseded, review comments), `requirements.md` (R1/R2.1 wording,
      budget, review comments), `testing-plan.md` results re-run, this file, the
      evidence files, the screenshots re-captured. _Depends on:_ E2 · _Test:_ T12.
- [x] **E4 — re-present.** Push; reply on the PR review with round 2; edit the ticket's
      presentation comment in place (the round-1 image links point at files that no
      longer exist); label back to `loop:needs-review`. _Depends on:_ E3 ·
      _Requirements:_ R4.3, R4.4 · _Test:_ T11.

### Round 3 — after the owner's pick

> _"I am leaning towards this [the Ensō]. Remove all others. Present some more colors
> and gradient options for this."_

- [x] **F1 — the paint layer.** `Variant` rows (a paint per ring, an optional sweep);
      `flat_ring`; `travelling_ring` — the stroke in 20 pieces cut on its own Bézier
      segments (`edges`, `segment`, `piece`), each a step further in OKLab
      (`to_oklab`/`from_oklab`/`mix`); a `<linearGradient>` sweep; per-piece
      dark-scheme fills for a ramp that touches ink. The other four marks and their
      machinery removed. _Depends on:_ E1 · _Requirements:_ R1.4, R2.2, R3.4 · _Test:_
      T1.
- [x] **F2 — ten colourways.** Seven flat (the original; ink; ink with a clay centre;
      warm; cool; earth; mauve), two travelling (dusk → clay; ink → accent, running
      dry), one sweep — iterated on the rendering (seams stepped, then corners rounded,
      then cut on the stroke's own curves). _Depends on:_ F1 · _Requirements:_ R1.4 ·
      _Test:_ T1, T5.
- [x] **F3 — the checker widened by exactly what a gradient needs.** `linearGradient`,
      `stop`, `class`, `gradientUnits`, `x1`–`y2`, `offset`, `stop-color`; any `url(`
      value must be a fragment. Probe re-run. _Depends on:_ F1 · _Test:_ T1, T8.
- [x] **F4 — the record.** `design.md` (round-3 overview, components, inventory with
      rounds 1–2 superseded, review comments), `requirements.md` (R1 reframed, review
      comments), `testing-plan.md` results re-run, this file, the evidence files, the
      screenshots re-captured. _Depends on:_ F2, F3 · _Test:_ T12.
- [x] **F5 — re-present.** Push; reply in the review thread; update the PR description;
      edit the ticket's presentation comment in place; label back to
      `loop:needs-review`. _Depends on:_ F4 · _Requirements:_ R4.3, R4.4 · _Test:_
      T11.

## Dependency graph (DAG)

```text
A1 → A2 → B1 → B2 → C1 → D1 ─(review)─→ E1 → E2 → E3 → E4 ─(pick)─→ F1 → F2 → F4 → F5
A1 → A3 ────────────↗                                                 F1 → F3 ──↗
```

## Checkpoints

- After A3: `python3 docs/specs/issue-398/design/generate.py --check` green.
- After B2: the twelve PNGs exist and the dark-scheme `<img>` captures show the light ink.
- After C1: markdownlint on `docs/specs/issue-398/**/*.md`, ruff on the generator, and a
  regeneration leaving the tree clean (T6) — recorded in `evidence/automated-tests.md`.
- D1 is the hand-off: nothing after it is this PR's to tick.

## Review comments

None yet.
