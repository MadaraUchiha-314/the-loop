---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Security review: a logo for the-loop (issue-398)

## Security review (gate) — round 3

- **Mechanism:** the harness's built-in `security-review` skill, re-run against the
  round-3 diff (`git diff origin/main...HEAD`, 44 paths, all under
  `docs/specs/issue-398/`, with the round-2 → round-3 delta of the generator read in
  full), with the repository's own model (`reference/security.md`,
  `design.uiArtifacts.selfContained`, `.github/workflows/the-loop-gate.yml`) as
  context; then the-loop checklist against the same diff.
- **Outcome:** pass — **no findings** at HIGH or MEDIUM.
- **Findings:** none. What the skill verified, in its words:
  1. `generate.py --check` green on the eleven files; the tree stayed clean.
  2. Every element and attribute in the ten committed SVGs enumerated with
     `xml.etree`: elements exactly `{svg, title, desc, style, path, linearGradient,
     stop}`, attributes exactly the allowlist; the only `url()` is the sweep's
     `fill="url(#enso-10-sweep-sweep)"`; every `<style>` is the dark-scheme media rule
     and `.class{fill:#rrggbb}` rules; every fill and stop colour a hex or
     `currentColor`.
  3. The gallery enumerated with `html.parser`: no script, link, object, embed, iframe,
     image, foreignObject, animate, form, base or `meta http-equiv`; no `on*=` handler;
     no `javascript:`/`data:`/`xlink`/`@import`; all 70 `href` values are fragments;
     inline styles carry only constant backgrounds; no duplicate id.
  4. All 22 PNGs carry only `IHDR/IDAT/IEND` chunks.
  5. No token, key, PEM, e-mail, home path or credential string in the diff.
  6. Data flow: the generator's only input is `--check` on argv; every interpolated
     value is a constant or a clamped hex derived from one; output names are the fixed
     `VARIANTS` slugs under the script's directory; the checker parses the in-memory
     render, never the on-disk file.
  7. The widened checker probed in memory: external fills, `href`/`xlink:href` on a
     gradient, `style=`, handlers, `<a>`, `<animate>`, `@import`, spaced and
     upper-cased `url(` in a stylesheet all refused; a legitimate `class` and the sweep
     pass.
- **Candidates rejected:** XSS via the gallery or SVGs (no script, handler, link or
  external reference exists; constants only); external loads via `<linearGradient>`,
  `fill="url(#…)"`, `<use href="#…">` (fragments; `gradientUnits` has no fetch
  semantics); the stylesheet as a vector (media rule and class fills only); path
  traversal (fixed names, script directory); command injection (no subprocess, no
  `eval`; `screenshots.mjs` unchanged); RNG (a visual seed); dependencies (stdlib only).
- **Defense-in-depth notes from the skill, both taken:**
  - *The attribute `url(` rule was case-sensitive and anchored*: `fill="URL(http…)"` or
    a leading space would have passed the SVG allowlist. Now every allowlisted
    attribute value is run through the same case-insensitive, whitespace-tolerant
    fragment-only rule as the stylesheet; the probe (`evidence/automated-tests.md`
    § T8) plants `URL(http…)` and a fill with a leading space, and both are refused.
  - *The gallery scan lacked parity with the SVG allowlist*: handlers, `<object>`,
    `<embed>`, `<link>`, `<base>` and `<meta http-equiv>` were not refused. Now they
    are — a case-insensitive `on*=` rule and six more tokens — and the probe covers
    a handler, an `<object>` and a `<meta http-equiv>`.
- **Checklist (the-loop):** authorization — n/a, no principal; untrusted input — none
  (the generator has no inputs; the screenshot script reads only sibling files);
  disclosure — static content, no data; secrets, logging, new calls — none. The
  requirements' one abuse case (an embedded SVG executes and loads nothing) is pinned by
  `generate.py --check` (T1/T8) as a parsed allowlist, probed.
- **Human sign-off:** n/a (risk tier 2).

## Security review (gate) — round 2

The same skill on the round-2 diff (commit `c653abb`): no findings; its three notes —
a parsed allowlist instead of a token scan, `CHROMIUM_NO_SANDBOX` honoured only as
`"1"`, unique gallery ids — were taken then.

## Security review (gate) — round 1

The same skill on the round-1 diff (commit `079092a`): no findings; its one note —
Chromium's sandbox switched off unconditionally in `screenshots.mjs` — was taken then
(the flag became opt-in).
