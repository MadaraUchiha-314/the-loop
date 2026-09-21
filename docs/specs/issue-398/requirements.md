---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#398"
status: approved             # draft | in-review | approved
approvedBy: ["the-loop"]     # tier-2 design deliverable: autonomous-complete per the skill's risk tiers; the acceptance is the ticket's own seven bullets, copied verbatim into R1–R4
collaborators: [designer, engineer]   # no designer role is assigned in collaborators.yaml, so the owner (@MadaraUchiha-314) plays the designer — the review-the-rendering step is what matters, not the title
overrides: {}
riskTier: 2                  # docs/specs/issue-398/** only — no code, no config, no sensitive path; the one human act is an aesthetic choice, not an approval of behaviour
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: a logo for the-loop — the Ensō, chosen and adopted

> Phase 1 of 4 (requirements → design → testing plan → tasks). A tier-2 work item:
> the four files are short and locked together, and the loop completes on its own
> after the review loop — except for the one thing only a human can do here, which is
> to **pick**. Source: [issue-398](https://github.com/MadaraUchiha-314/the-loop/issues/398).

## Introduction

the-loop has no mark. Its README opens on a name and an Excalidraw workflow diagram;
the docs site's hero is text; the plugin manifests carry no icon. The ticket asks for
a logo in a hand-drawn register with muted colours, built on the one idea the project
is named for — **inner, outer and many loops working together** — presented as three to
five options that each explore a *different* concept, preferably as SVG rather than a
raster image.

This work item delivers the options and the means to iterate them, and — since the
owner's pick on 2026-09-21 widened it (R5, *Review comments*) — the **adoption** of the
chosen mark across the user-facing surfaces. The choice itself stayed the owner's,
recorded on the pull request.

## Requirements

### R1 — five options, five concepts → *(round 3)* one mark, in colourways

**User story:** As the owner, I want several genuinely different logo concepts side by
side, so that I am choosing between ideas rather than between shades of one idea.
*(Sharpened after the review of round 1: different is not enough — each option has to
have a **character**, a personality a person could name, not only a distinct geometry.)*

#### Acceptance criteria (EARS)

1. The deliverable SHALL contain between three and five logo options; this work item
   delivers five. *(Superseded by the owner's round-2 review, below: the mark is
   chosen — the Ensō — and the deliverable is now that one mark in colour and gradient
   options; round 3 delivers ten.)*
2. Each option SHALL be built on a **distinct visual concept** of *inner, outer and many
   loops working together* — a different structural relationship between the loops,
   not a colour, size or tilt variation of another option. The concept SHALL be named
   in one sentence per option.
3. Every option SHALL contain at least three loops, with at least one visibly *inside*
   or *carried by* another, so the inner/outer relationship reads without a caption.
4. *(Round 3)* Every colourway SHALL be the same mark — the round-2 Ensō's geometry,
   unchanged — differing only in paint: flat palettes from the shared palette, and
   gradients, of which at least one travels along each stroke and at least one spans
   the mark.

### R2 — hand-drawn, muted

**User story:** As the owner, I want the mark to look drawn by a hand, not extruded by
a tool, so that it matches the project's voice.

#### Acceptance criteria (EARS)

1. Every loop SHALL be drawn with a line a hand made — a brush's pressure and angle
   giving it a width that varies along its path — rather than a geometrically exact
   stroke. *(Revised after the owner's review of round 1, below: the hand shows in
   the brush, not in a wobble; a tremor reads as unsure, not as drawn.)*
2. Every colour used SHALL be muted: a desaturated palette on a paper-toned background,
   with no pure primaries and no saturated accent.
3. The set SHALL share one palette, so the five options read as a family and any one
   of them can be adopted without re-choosing colours.

### R3 — SVG, self-contained, reproducible

**User story:** As the owner, I want the logo as SVG I can read, scale and edit, so that
it is a source rather than a picture.

#### Acceptance criteria (EARS)

1. Each option SHALL be one standalone `.svg` file with no external reference: no
   font, no linked image, no script, no network fetch.
2. Each SVG SHALL render identically at favicon size (16 px) and at hero size (≥ 256 px)
   from the same file, and the presentation SHALL show both.
3. Each SVG SHALL be **generated**, not traced: a checked-in, stdlib-only script SHALL
   produce every file deterministically from named parameters (seed, wobble, widths,
   colours), so that "more wobble" or "swap the accent" is a parameter change and a
   re-run, never a redraw. Running the script twice SHALL produce byte-identical files.
4. Each SVG SHALL carry a `<title>` and a `<desc>` so the mark is named to assistive
   technology, and SHALL read on both a light and a dark background (a
   `prefers-color-scheme: dark` override for the ink, accents mid-toned enough for
   either).

### R4 — presented for a decision

**User story:** As the owner, I want to look at the rendered options, not their markup,
and to record my pick where the paper trail lives.

#### Acceptance criteria (EARS)

1. The options SHALL be presented in one self-contained HTML gallery under
   `docs/specs/issue-398/design/` that shows each mark on paper and on slate, at four
   sizes down to 16 px, and beside the name `the-loop` as a lockup, with the concept
   sentence and what each element stands for.
2. Rendered screenshots of the gallery SHALL be committed under
   `design/screenshots/` as evidence, so the options are reviewable from the PR
   without a browser.
3. WHEN the options are pushed THEN the ticket SHALL receive one comment linking the
   gallery, the SVGs and the PR and asking for the pick; the pick — and any feedback
   to iterate on — SHALL be a ticket comment, and the iteration SHALL be an edit to the
   generator's parameters and a re-run, never a second copy of an option.
4. The ticket SHALL rest at `loop:needs-review` once the options are presented: the
   item is waiting on a human decision, which no review round can substitute for.

### R5 — the chosen mark, adopted *(added by the owner's pick, 2026-09-21)*

**User story:** As the owner, having chosen a colourway, I want every place a reader
meets the-loop to carry it, so that the repository, the site and the Slack app read as
one thing.

#### Acceptance criteria (EARS)

1. The root `README.md` SHALL open with the mark, legible on GitHub's light and dark
   themes (a `<picture>` with a source per scheme).
2. The docs site SHALL carry the mark as its nav logo, its home-page hero image and its
   favicon, following the site's own theme toggle, and SHALL build with them.
3. The CLI's PyPI page (`cli/README.md`) SHALL open with the mark as a raster, since that
   renderer takes no SVG from a repository.
4. The control-plane dashboard SHALL carry the mark as its favicon and SHALL build with it.
5. The Slack app SHALL have the mark as its icon: a square raster on the paper ground at
   the size Slack expects, plus the manual upload step in the Slack guide, because Slack's
   manifest format carries no icon.
6. Every adopted file SHALL be **generated** by the same script as the options and pinned
   by its `--check`, so the adopted mark cannot drift from its source; the rasters SHALL
   come from the design folder's screenshot script.
7. The two capability docs the adoption touches (`documentation`, `channels`) SHALL
   record it, and `evidence/documentation.md` SHALL list every user-facing file changed.

## Non-functional requirements

- **Size.** Each SVG under 64 kB (round 1 budgeted 40 kB; a brush stroke needs denser
  sampling than a wobbled ellipse); the gallery under 500 kB (round 1 budgeted 300 kB
  for five marks; round 3 carries ten colourways, one symbol each); screenshots as PNG
  at 1× device pixel ratio, so the spec folder stays reviewable in a diff.
- **Toolchain.** The generator runs on the repository's Python (3.11) with the standard
  library only; screenshots come from the Chromium the repository already drives for
  the dashboard's evidence (`ui/scripts/screenshots.mjs`'s approach), so nothing new is
  installed to reproduce either.
- **No lint drift.** `docs/specs/*/design/**` is already excluded from markdownlint;
  the generator is kept `ruff`-clean anyway so it can be moved without surprise.

## Security considerations

- **Actors & trust:** the owner (reviewer and decider) and this session. No end user,
  no runtime, no service: everything delivered is static content under `docs/specs/`.
- **Trust boundaries & data:** none crossed. The SVGs and the gallery contain no
  script, no external reference and no fetched content, so they cannot execute or
  load anything when opened, embedded in a README, or previewed by a Markdown renderer.
  No secret, token, hostname or personal datum appears in any generated file or
  screenshot (the generator has no inputs beyond its own constants).
- **Abuse cases (EARS):**
  1. WHEN an SVG is embedded by a consumer (README, docs site, a third-party viewer)
     THEN it SHALL contain no `<script>`, no `<foreignObject>`, no `href` to any URL and
     no `<image>` — pinned by the generator's `--check` mode, which refuses to pass a
     file carrying any of them.
- **Fail closed:** `--check` exits non-zero on any malformed, non-deterministic,
  untitled or non-self-contained file, so a hand edit that breaks the invariants is
  caught before the PR is green.

## Out of scope

- **The plugin manifests** (`.claude-plugin/`, `.cursor-plugin/`): neither format has an
  icon field today; nothing to carry the mark. *(Adoption of the mark elsewhere moved
  into scope as R5 on the owner's pick.)*
- **Changing the Slack app's `background_color`** in the shipped manifest to the paper
  ground: cosmetic, and the manifest is pinned by tests and mirrored in the guide;
  left for a later touch.
- **A wordmark / typeface.** The gallery shows a lockup in the system monospace only to
  judge proportion; choosing type is part of adoption.
- **A raster export pipeline** (PNG/ICO sizes for stores and favicons) — adoption.
- **Animation.** One option lends itself to a draw-on animation; noted in `design.md`
  as an idea for adoption, not delivered here.

## Open questions

None for the spec. The one open question — *which option?* — is the deliverable's
purpose, raised as the ticket comment R4.3 requires, and answered there.

## Review comments

- **2026-09-20 · @MadaraUchiha-314 (owner, designer) · [PR #403 review](https://github.com/MadaraUchiha-314/the-loop/pull/403#pullrequestreview-5261761922)**
  — *"I think you over stressed on the hand drawn part. there's no character to these
  logos."* Recorded here because it changes what R1.2 and R2.1 ask for: the character
  clause on R1, the brush-not-wobble wording on R2.1, and the 64 kB budget are the
  edits; round 2 of the options is the response (`design.md` § Review comments).
- **2026-09-21 · @MadaraUchiha-314 (owner, designer) · [PR #403 review comment on `option-5-enso.svg`](https://github.com/MadaraUchiha-314/the-loop/pull/403#discussion_r4058557797)**
  — *"I am leaning towards this. Remove all others. Present some more colors and
  gradient options for this."* The pick, and a new ask: R1.1 is superseded (one mark,
  not three to five) and R1.4 is added (colourways of one unchanged geometry); the
  four other marks are removed. Round 3 of the artifacts is the response
  (`design.md` § Review comments).
- **2026-09-21 · @MadaraUchiha-314 (owner, designer) · [PR #403 review comment on `enso-5-dusk-sage-ink.svg`](https://github.com/MadaraUchiha-314/the-loop/pull/403#discussion_r4058602461)**
  — *"I choose this. Update all documentation and the github README to have this. The
  slack app also must have this as it's logo."* The pick — colourway 5, dusk · sage ·
  ink — and the adoption, which the first version of this document had placed out of
  scope as a follow-up. Folded in as **R5** and as round 4 of the artifacts: the README,
  the docs site, the PyPI README, the dashboard and the Slack guide carry the mark; the
  Slack icon itself is a manual upload the guide now describes.
