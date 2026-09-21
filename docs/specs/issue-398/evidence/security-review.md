---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Security review: a logo for the-loop (issue-398)

## Security review (gate) — round 4 (the adoption)

- **Mechanism:** the harness's built-in `security-review` skill, run against the
  adoption delta (`git diff 07d94e5 HEAD`: one commit, 25 text files and two rasters —
  the README's and the CLI README's inline HTML, `config.mts` `head` and `logo`,
  `index.md`'s hero, `ui/index.html`'s favicon link, the generator's adoption layer,
  `screenshots.mjs --assets` / `--site`, seven SVGs under `docs/assets/`, `docs/public/`
  and `ui/public/`), with the whole branch, the site-and-dashboard deploy workflow
  (`.github/workflows/docs.yml`), `cli/pyproject.toml` and the markdownlint config as
  context; then the-loop checklist against the same diff.
- **Outcome:** pass — **no findings** at HIGH or MEDIUM.
- **Findings:** none. What the skill verified, in its words:
  1. `target(name)` is called only with the `VARIANTS` slugs and the literal
     `ADOPTED_FILES` keys — seven fixed relative paths, no `..`; `main()` reads argv
     only for `--check`; no environment variable, no stdin; `REPO` derives from the
     script's own resolved location.
  2. `--check` compares the on-disk bytes with the render and parses the render, never
     the file on disk: a tampered file fails the equality check.
  3. Every adopted SVG holds exactly `svg, title, desc, path ×3` (plus one `<style>`
     with the dark-scheme colour rule on the three self-switching files), attributes
     exactly `xmlns viewBox color role aria-labelledby id d fill`; zero hits for a
     script, a handler, `foreignObject`, `href`, `url(`, `@import`, `http` outside the
     namespace, `xlink`, an entity, a doctype, CDATA, `javascript:`, `data:` and every
     fetching element.
  4. The README block is the static `<picture>` pattern GitHub's sanitiser permits, its
     sources relative and proxied; the alt text carries no quote or bracket. The PyPI
     README's one `<img>` points at a host the repository owner controls, and an image
     cannot execute there.
  5. `config.mts`, `index.md` and `ui/index.html` carry string literals bound as
     escaped attributes, pointing at same-origin static files.
  6. `screenshots.mjs --site` navigates a fresh, credential-less headless context to a
     URL the developer typed; nothing in CI or any package script invokes the file.
     `--assets` builds a `data:` image from a repository file (an image context
     executes nothing) and writes two literal paths.
  7. Both rasters: valid PNG, 1024 × 1024 and 180 × 180, chunks `IHDR/IDAT/IEND` only,
     zero bytes after `IEND`.
  8. No manifest or lockfile changed; nothing is fetched at build or run time; no
     token, key, e-mail or credential in the diff.
- **Candidates rejected:** path traversal (fixed names, a root derived from the script);
  a hostile on-disk file (never parsed); XSS via the SVGs or the READMEs (static, no
  active content, sanitised where rendered); SSRF via `--site` (the developer's own
  argument, no caller); supply chain (no dependency change, no remote load).
- **Defense-in-depth notes from the skill — three taken, one recorded:**
  - *`REPO = HERE.parents[3]` trusts the script's depth*: a copy of the file elsewhere
    would create `docs/` and `ui/` four levels up from wherever it sat. Taken:
    `target()` leaves the design folder only when `.the-loop/harness-config.yaml`
    (`REPO_MARKER`) is at that root, and exits before any write otherwise; the probe
    (`automated-tests.md` § T8, round 4) shows the refusal from `/tmp`.
  - *`--check` pinned the SVGs but not the two rasters the Slack icon and the
    apple-touch icon actually ship.* Taken as a structural check rather than a hash —
    a Chromium render is not byte-identical across builds, and a hash would fail on
    every legitimate re-render: `png_problems()` requires the PNG signature, the
    expected square, only the `IHDR/IDAT/IEND` chunks (a text or private chunk could
    carry anything) and nothing after `IEND`. The probe plants a `tEXt` chunk, a
    trailer, a wrong size, a truncation and an SVG in disguise; each is refused.
  - *`--site` could one day be wired to an externally influenced value.* Taken: the
    script exits (code 2) before launching a browser unless the URL's host is loopback
    — the docs preview (`bun run docs:preview`) is the only thing it is for.
    `http://example.com/` is refused; `http://127.0.0.1:…` passes the rule.
  - *The PyPI image points at the mutable `main` ref, and the file is absent there
    until this PR merges.* Recorded, not taken: PyPI reads the CLI README at publish
    time, no release is cut from this branch, and a reference that tracks `main` is
    what lets a later change of the mark reach every release page — both ends are the
    owner's. Should the mark ever change in a way an old release page must not follow,
    that one line is the place to pin a tag.
- **Checklist (the-loop):** authorization — n/a, no principal; untrusted input — none
  new (the generator's inputs are unchanged; `--site` is a developer's argument, now
  loopback-only); disclosure — static content, no data; secrets, logging, new calls —
  none; new surfaces — the README, the site's `head`, the dashboard's favicon link, all
  static references to same-origin files. The requirements' abuse case (an embedded SVG
  executes and loads nothing) holds for the adopted files by the same `--check`
  (T1/T8), and the two rasters carry nothing beyond image data.
- **Human sign-off:** n/a (risk tier 2).

## Security review (gate) — round 3

The same skill on the round-3 diff (commit `fd6c1b9`, the Ensō in ten colourways): no
findings; its two notes — the fragment-only rule applied case-insensitively to every
allowlisted attribute value, and handlers, `<object>`, `<embed>`, `<link>`, `<base>` and
`<meta http-equiv>` refused in the gallery scan — were taken then (commit `07d94e5`),
with the T8 probe covering both.

## Security review (gate) — round 2

The same skill on the round-2 diff (commit `c653abb`): no findings; its three notes —
a parsed allowlist instead of a token scan, `CHROMIUM_NO_SANDBOX` honoured only as
`"1"`, unique gallery ids — were taken then.

## Security review (gate) — round 1

The same skill on the round-1 diff (commit `079092a`): no findings; its one note —
Chromium's sandbox switched off unconditionally in `screenshots.mjs` — was taken then
(the flag became opt-in).
