---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Self-review: a logo for the-loop (issue-398)

> `the-loop critic policy` on this machine: `selfReviewCount: 3`, `criticReviewCount: 3`,
> stop on no new findings, escalate on a repeat; `the-loop critic list` — "No critics
> configured", so the critic rounds are **unavailable** and do not count. Each round of
> the design (round 1, then round 2 after the owner's review) got three self passes: the
> diff, then the rendering and the file as a consumer meets it, then the final diff once
> more. The third pass found nothing new each time, which is the stop rule.

## Review cycles — round 1

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (diff read) | new findings | (a) every SVG used the same `<title>`/`<desc>` ids (`t`, `d`) — a clash the moment two are inlined in one page → ids are `<slug>-title` / `<slug>-desc`; (b) the checker read and wrote files in the locale encoding, so an em dash would fail under a `C` locale → `encoding="utf-8"` on both; (c) the gallery inlined each mark seven times (1.4 MB) → one `<symbol>` per option, `<use>` everywhere else (198 kB); (d) the self-containment check listed `http:` as a forbidden token and flagged the SVG namespace URL → replaced by a regex refusing any `href` that is not a `#fragment`, plus the element and `src=` tokens | this PR |
| 2 | self (rendering + consumer read) | new findings | (e) the planetary chevrons were illegible below 48 px → dropped; (f) the coil at 12 loops read as a doily → five variants rendered side by side, 18 loops chosen; (g) the one-line mark's inner loops too small to read as loops → d 1.75 → 2.15; (h) `NODE_PATH` does not resolve ES-module imports → the script's install note and the plan's bring-up corrected; (i) the standalone file's dark rule would go global if a consumer inlined the markup → one sentence in `design.md` | this PR; design.md |
| 3 | self (final diff) | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |

## Human review — round 1 → round 2

| Reviewer | Where | Finding | Disposition |
|----------|-------|---------|-------------|
| @MadaraUchiha-314 (owner, designer) | [PR #403 review](https://github.com/MadaraUchiha-314/the-loop/pull/403#pullrequestreview-5261761922) | *"I think you over stressed on the hand drawn part. there's no character to these logos."* | round 2: the hand moves from wobble and overdraw into a brush (nib angle, pressure, lifts); five marks with a personality each replace the five structures; R1/R2.1 and the size budget amended in `requirements.md` § Review comments |

## Review cycles — round 2

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (rendering read) | new findings | (j) white slivers inside strokes at tight curls and self-crossings — the `evenodd` fill rule carving holes where the outline polygon crosses itself, and offsets folding back past the centre of curvature → default `nonzero` fill, and the half-width clamped to 0.85 × the local circumradius; (k) the ensō's inner rings drawn thin — the brush profile read the circle's global parameter instead of progress along the drawn arc → `stroke()` hands the brush local progress; `woven()` keeps the global mapping its over-segments need; (l) hairline sections from nib contrast of 0.5–0.6 → 0.32–0.45 with a higher floor; (m) the knot's weave gaps too wide → gap 3.0 → 2.2; (n) the flick's arrowhead small, with the stroke poking through its notch → a plain chevron 30 × 28 the stroke ends inside (u 0.955 → 0.94); (o) ensō bases 16 / 12 / 8.5 → 16 / 13 / 9.5 | this PR |
| 2 | self (diff read) | new findings | (p) all five over the round-1 40 kB budget (39–63 kB) — a brush stroke needs ~2 px sampling → budget 64 kB in the checker and in `requirements.md`, with the reason; (q) two `zip()`s without `strict=` (ruff B905) → `strict=False`, the pairs are offset on purpose; (r) `url(` was a forbidden token but the knot's mask needs `mask="url(#…)"` → the external-reference regex admits `url(#` and refuses any other `url(`, the same rule as `href` | this PR |
| 3 | self (final diff + gallery, after the security review's notes were taken) | new finding | (s) the rewritten fragment-only regex let `href="#ok"` through as *external* — with the quote optional, the lookahead could skip it and see the quote instead of the `#` → the lookahead allows an optional quote before the `#`; the negative probe (`automated-tests.md` § T8) pins both directions. The cap of three rounds is reached with this fixed and verified; nothing was found repeating. | this PR |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |

## Human review — round 2 → round 3

| Reviewer | Where | Finding | Disposition |
|----------|-------|---------|-------------|
| @MadaraUchiha-314 (owner, designer) | [PR #403 review comment on `option-5-enso.svg`](https://github.com/MadaraUchiha-314/the-loop/pull/403#discussion_r4058557797) | *"I am leaning towards this. Remove all others. Present some more colors and gradient options for this."* | round 3: the Ensō alone, its geometry frozen, in ten colourways — seven flat, two travelling gradients, one sweep; the four other marks removed; R1.1 superseded and R1.4 added in `requirements.md` § Review comments |

## Review cycles — round 3

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (rendering read) | new findings | (t) the travelling gradient's pieces stepped at every seam — each piece computed its own edge normals from its own few samples → the pieces are cut from **one** set of edges; (u) the pieces then showed tick marks along the edges — a closed Catmull-Rom spline per piece rounded its four corners → each piece is built from the stroke's **own Bézier segments** along its edges (`segment`, `piece`) with straight cuts across and a one-sample overlap, so adjacent pieces share an identical curve; (v) mauve was the one palette colour no colourway used → colourway 7 (mauve · dusk · clay) | this PR |
| 2 | self (diff + budget read) | new findings | (w) the gallery (ten symbols) is 452 kB against the requirements' 300 kB budget written for five marks → the NFR raised to 500 kB with the reason, in `requirements.md`; (x) the allowlist needed exactly `linearGradient`, `stop`, `class` and seven gradient attributes, and a `fill="url(…)"` that is not a fragment had no rule → any `url(` value must be `url(#`, pinned by the probe | this PR |
| 3 | self (final diff + gallery, both schemes) | zero (converged) | — | — |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |

## Human review — round 3 → round 4

| Reviewer | Where | Finding | Disposition |
|----------|-------|---------|-------------|
| @MadaraUchiha-314 (owner, designer) | [PR #403 review comment on `enso-5-dusk-sage-ink.svg`](https://github.com/MadaraUchiha-314/the-loop/pull/403#discussion_r4058602461) | *"I choose this. Update all documentation and the github README to have this. The slack app also must have this as it's logo."* | the pick (colourway 5, marked approved in the inventory) and the adoption, added as R5 and delivered as round 4: generated brand assets, README, docs site, PyPI README, dashboard, Slack guide, capability docs |

## Review cycles — round 4

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (surface read) | new findings | (y) a self-switching SVG follows the OS scheme, but GitHub and the docs site switch themes on their own → fixed-ink light/dark files for those two surfaces, the self-switching file only where the OS decides (favicons); (z) VitePress does not base-prefix `head` entries → the favicon and apple-touch paths carry `/the-loop/` by hand, verified in the built `index.html`; (aa) `screenshots.mjs --assets` would have created a directory named `--assets` (the out-dir argument was `argv[2]`) → the arguments are parsed, and the out dir is made only for a capture run | this PR |
| 2 | self (build + lint read) | new findings | (ab) PyPI renders no SVG from a repository → the CLI README takes the 1024 px raster from `main`; (ac) a whole-repo markdownlint run from inside `ui/` swept `node_modules` because the config lives at the root → re-run from the root: 1307 files, 0 errors; the build directories and installs are git-ignored, verified with `git check-ignore` | this PR |
| 3 | self (final diff, both builds' output) | zero (converged) | — | — |
| 4 | self (final diff, after the security review's notes were taken) | zero (converged) | the three hardenings — the root guard, the raster check, the loopback rule — re-verified by T1, T6 and the T8 probes; nothing repeating | this PR |
| — | critic | unavailable | no critic CLI configured on this machine | `the-loop critic list` |
