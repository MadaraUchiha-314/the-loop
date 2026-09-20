---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Security review: a logo for the-loop (issue-398)

## Security review (gate) — round 2

- **Mechanism:** the harness's built-in `security-review` skill, re-run against the
  round-2 diff (`git diff origin/main...HEAD`, 29 files under `docs/specs/issue-398/`,
  with the round-1 → round-2 delta of the two scripts read separately), with the
  repository's own model (`reference/security.md`, `design.uiArtifacts.selfContained`)
  as context; then the-loop checklist against the same diff.
- **Outcome:** pass — **no findings** at HIGH or MEDIUM.
- **Findings:** none. Candidates examined and rejected, in the skill's words:
  1. *XXE / unsafe XML parsing* — the parser is fed the in-memory string `render()`
     just produced from script constants; the on-disk file is only byte-compared, never
     parsed; an in-memory probe confirmed stdlib `xml.etree` raises on a `SYSTEM` entity
     and fetches nothing for an external DTD.
  2. *Injection into generated SVG/HTML* — every interpolated value is a hard-coded
     constant (`mask_id`, hex fills or `currentColor`, prose with only `'`, `—`, `·`,
     `°`); every element and attribute name in the six generated files was enumerated:
     SVGs contain only `svg, title, desc, style, path` (+ `mask, rect` in the knot); no
     `<script>`, no `on*=` handler, no `javascript:`/`data:`/`xlink`, no `<a>`, `<set>`,
     `<animate>`, `<foreignObject>`, `<image>`; all 35 `href` values are fragments and
     the single `url()` is `#option-2-knot-weave`.
  3. *Path traversal / arbitrary write* — fixed output names under the script's own
     directory; `argv` only tested for `--check`.
  4. *`screenshots.mjs` out-dir* — operator-run, writes only `<basename>.png` from
     `readdirSync` entries, reads only sibling files; not referenced by CI, hooks or any
     package script.
  5. *Chromium `--no-sandbox`* — passed only when the operator sets the variable (the
     round-1 mitigation, verified in source); rendered content is repo-local,
     script-free, `file://` and `data:` inside an `<img>`.
  6. *`<mask>` / `mask="url(#…)"` / `<use href="#…">`* (new in round 2) — local fragment
     references; a mask loads, fetches and executes nothing.
  7. *Secrets / PII* — none in the added text; all twelve PNGs carry only
     `IHDR/IDAT/IEND` chunks.
  8. *RNG* — `random.Random(398_5)` seeds a wobble; not a cryptographic use.
- **Defense-in-depth notes from the skill, all taken:**
  - *The checker was a case-sensitive token scan* (`HREF='…'`, an `on*=` handler or
    an `<animate>` would have passed it). Now the standalone SVGs are checked from their
    **parsed tree against an allowlist** of element names (`svg, title, desc, style,
    path, mask, rect`) and attribute names, a `mask` must reference a fragment, and a
    stylesheet may not `@import` or reference anything outside the file; the gallery
    (HTML) keeps a case-insensitive token scan and a fragment-only rule for `href`/`url`.
    A negative probe (`evidence/automated-tests.md` § T8) shows a planted `<script>`,
    an `onclick`, an `<image href="http…">` and an `@import` each fail.
  - *`CHROMIUM_NO_SANDBOX` honoured any truthy value* — now `=== "1"`, the documented
    contract.
  - *Duplicate ids in the gallery* (each `<symbol>` shared its id with its `<section>`;
    `<use>` resolved to the first) — the sections are now `…-card`.
- **Checklist (the-loop):** authorization — n/a, no principal; untrusted input — none
  (the generator has no inputs; the screenshot script reads only sibling files);
  disclosure — static content, no data; secrets, logging, new calls — none. The
  requirements' one abuse case (an embedded SVG executes and loads nothing) is pinned by
  `generate.py --check` (T1/T8), now as a parsed allowlist rather than a grep.
- **Human sign-off:** n/a (risk tier 2).

## Security review (gate) — round 1

The same skill on the round-1 diff (commit `079092a`): no findings; its one note —
Chromium's sandbox switched off unconditionally in `screenshots.mjs`, unlike the
dashboard's script — was taken then (the flag became opt-in) and tightened above.
