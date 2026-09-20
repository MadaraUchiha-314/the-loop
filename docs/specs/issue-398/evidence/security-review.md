---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Security review: a logo for the-loop (issue-398)

## Security review (gate)

- **Mechanism:** the harness's built-in `security-review` skill, run against
  `git diff origin/main...HEAD` (28 files under `docs/specs/issue-398/`), with the
  repository's own model (`reference/security.md`, `design.uiArtifacts.selfContained`)
  as context; then the-loop checklist against the same diff.
- **Outcome:** pass — **no findings** at HIGH or MEDIUM.
- **Findings:** none. Candidates examined and rejected, in the skill's words:
  1. *XXE / unsafe XML parsing* — `generate.py` parses only the in-memory string its
     own `render()` returned, never the on-disk file (which is byte-compared); stdlib
     `xml.etree` does not resolve external entities (a `SYSTEM` entity probe raised
     `ParseError`). No attacker-controlled data reaches the parser.
  2. *Path traversal on write* — every output name is a hard-coded slug; `argv` is only
     tested for `--check` membership and never used as a path.
  3. *XSS / HTML injection in the generated gallery and SVGs* — the interpolated strings
     are constants in the script; the generated output was enumerated element by
     element: no `on*=` handler, no `<script>`, no `javascript:`, no `url(`/`@import`/
     `src=`; all 35 `href` values are `#fragment` references to the gallery's own
     `<symbol>`s.
  4. *Output-directory argument in `screenshots.mjs`* — operator-controlled, local,
     writes only PNGs, reads only files beside itself; not referenced by CI, hooks or
     any package script.
  5. *Chromium `--no-sandbox` in `screenshots.mjs`* — new to the repository (the
     dashboard's script does not pass it); rendered content is repo-local, generated,
     script-free, loaded via `file://` and `data:`; run by hand only. LOW,
     defense-in-depth. **Taken anyway:** the flag is now passed only when
     `CHROMIUM_NO_SANDBOX=1` is set, so a developer with a working sandbox never
     disables it; the evidence records why this container needed it (root).
  6. *`CHROMIUM_PATH` → `executablePath`* — the pre-existing convention; operator
     environment, not a new surface.
  7. *Checker weaknesses* (case-sensitive tokens, no `on*=` guard) — the checker
     validates the generator's own output and the on-disk files are byte-compared
     against it; anyone able to plant a bypass could edit the checker. Not a trust
     boundary.
  8. *Secrets / PII* — none in the diff; the PNGs carry only `IHDR/IDAT/IEND` chunks
     (no metadata); the one absolute path is a browser install location.
  9. *SVG as `<img>` via `data:`, gallery via `file://`* — an `<img>` cannot run script
     regardless, and the gallery carries none.
- **Checklist (the-loop):** authorization — n/a, no principal; untrusted input — none
  (the generator has no inputs; the screenshot script reads only sibling files);
  disclosure — static content, no data; secrets, logging, new calls — none. The
  requirements' one abuse case (an embedded SVG executes and loads nothing) is pinned by
  `generate.py --check` (T1/T8).
- **Human sign-off:** n/a (risk tier 2).
