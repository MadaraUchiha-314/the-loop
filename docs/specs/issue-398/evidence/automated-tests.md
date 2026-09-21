---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Evidence: automated checks (issue-398)

Run from the repository root on the branch of the delivering PR. Rows refer to
[`testing-plan.md`](../testing-plan.md). **Round 3** (2026-09-21, after the owner's pick)
re-ran every row; **round 4** (2026-09-21, the adoption) added the build and whole-repo
lint rows; the red→green records of rounds 1 and 2 are kept below.

## T1 — the generator's checker

Round 3, on the final files:

```
$ python3 docs/specs/issue-398/design/generate.py --check
ok — 11 files match, well-formed, self-contained, titled
exit=0
```

Round 1, before the first render — the checker against an empty folder:

```
$ python3 docs/specs/issue-398/design/generate.py --check
FAIL option-1-gimbal.svg: missing
FAIL option-2-one-line.svg: missing
FAIL option-3-coil.svg: missing
FAIL option-4-rings.svg: missing
FAIL option-5-planetary.svg: missing
FAIL logo-options.html: missing
check exit=1
```

Round 2, first render against the round-1 budget:

```
$ python3 docs/specs/issue-398/design/generate.py --check
FAIL option-1-loop.svg: over 40 KB
FAIL option-2-knot.svg: over 40 KB
FAIL option-3-flick.svg: over 40 KB
FAIL option-4-clip.svg: over 40 KB
FAIL option-5-enso.svg: over 40 KB
check exit=1
```

Round 1 also had two intermediate reds worth keeping: the coil and planetary marks over
the size budget (58 903 and 51 515 bytes, brought under by fewer samples and dropped
chevrons), and the first token list flagging the SVG namespace URL (`contains 'http:'`)
— the check reads the parsed tree against an allowlist now.

## T6 — a regeneration leaves the tree clean

```
$ python3 docs/specs/issue-398/design/generate.py && git diff --exit-code --stat -- docs/specs/issue-398/design/
wrote enso-1-ink-dusk-clay.svg (41.9 kB)
wrote enso-2-ink.svg (41.9 kB)
wrote enso-3-ink-ink-clay.svg (41.9 kB)
wrote enso-4-clay-ochre-ink.svg (41.9 kB)
wrote enso-5-dusk-sage-ink.svg (41.9 kB)
wrote enso-6-sage-ochre-clay.svg (41.9 kB)
wrote enso-7-mauve-dusk-clay.svg (41.9 kB)
wrote enso-8-dusk-to-clay.svg (48.6 kB)
wrote enso-9-running-dry.svg (52.9 kB)
wrote enso-10-sweep.svg (42.2 kB)
wrote logo-options.html (452.5 kB)
exit=0
```

## T5 — the rendered evidence

```
$ CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome CHROMIUM_NO_SANDBOX=1 \
  node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots
gallery-light
gallery-dark
enso-1-ink-dusk-clay-paper
enso-1-ink-dusk-clay-slate
enso-10-sweep-paper
enso-10-sweep-slate
enso-2-ink-paper
enso-2-ink-slate
enso-3-ink-ink-clay-paper
enso-3-ink-ink-clay-slate
enso-4-clay-ochre-ink-paper
enso-4-clay-ochre-ink-slate
enso-5-dusk-sage-ink-paper
enso-5-dusk-sage-ink-slate
enso-6-sage-ochre-clay-paper
enso-6-sage-ochre-clay-slate
enso-7-mauve-dusk-clay-paper
enso-7-mauve-dusk-clay-slate
enso-8-dusk-to-clay-paper
enso-8-dusk-to-clay-slate
enso-9-running-dry-paper
enso-9-running-dry-slate
```

Playwright 1.63.0 with the Chromium already installed for the dashboard's evidence
script; resolved through a `node_modules` link beside the script, removed afterwards.
`CHROMIUM_NO_SANDBOX=1` because this container runs as root: Playwright adds the flag
for a root user itself (a run without the variable produced the same captures), so the
variable only makes explicit what happens here anyway; on a machine with a working
sandbox the flag is never passed. The `-slate` captures are `<img>` embeddings under
an emulated dark scheme: the flat-ink colourways show the light ink, the running-dry
colourway shows its dark-scheme piece fills, so each standalone file's own media rules
are what is proved. Files: [`../design/screenshots/`](../design/screenshots/).

## T8 — the abuse case, probed

The checker validates each standalone SVG from its **parsed tree against an allowlist**
(elements `svg, title, desc, style, path, linearGradient, stop`; a fixed attribute set;
any attribute value that references something must be a `#fragment`, case-insensitively
and whatever the spacing; a stylesheet may not `@import` or reference anything outside
the file) and scans the HTML gallery case-insensitively for the same absences, for
event-handler attributes, and with a fragment-only rule for `href`/`url`. A planted
script, handler, image, external fill (in any spelling) and import each fail; fragments
pass; on the gallery side a handler, an `<object>` and a `<meta http-equiv>` are refused
and an ordinary `class="option"` is not:

```
$ python3 - <<'PY'
import sys; sys.path.insert(0, "docs/specs/issue-398/design")
import generate as g, xml.etree.ElementTree as ET
bad = g.render()["enso-10-sweep.svg"].replace(
    "</svg>",
    '<script>alert(1)</script><path d="M0 0" fill="URL(http://x/y)" onclick="x()"/>'
    '<path d="M0 0" fill=" url( http://x/y )"/><image href="http://x/y.png"/>'
    '<style>@import url(http://x/a.css)</style></svg>')
print("\n".join(g.svg_problems("probe.svg", ET.fromstring(bad))))
def gallery_flags(html):
    return (any(t.lower() in html.lower() for t in g.FORBIDDEN)
            or bool(g.HANDLER.search(html)) or bool(g.EXTERNAL_REF.search(html)))
for planted in ("<a HREF='http://x'>", '<use href="#ok"/>', 'url(#mask)', '<div onclick="x()">',
                '<object data="x">', '<meta http-equiv="refresh">', '<span class="option">'):
    print(f"{planted!r:32} -> {'flagged' if gallery_flags(planted) else 'ok'}")
PY
probe.svg: element <script> is not in the allowlist
probe.svg: fill reference 'URL(http://x/y)' is not a fragment
probe.svg: attribute 'onclick' on <path> is not in the allowlist
probe.svg: fill reference ' url( http://x/y )' is not a fragment
probe.svg: element <image> is not in the allowlist
probe.svg: attribute 'href' on <image> is not in the allowlist
probe.svg: the stylesheet references something outside the file
"<a HREF='http://x'>"            -> flagged
'<use href="#ok"/>'              -> ok
'url(#mask)'                     -> ok
'<div onclick="x()">'            -> flagged
'<object data="x">'              -> flagged
'<meta http-equiv="refresh">'    -> flagged
'<span class="option">'          -> ok
```

## T9 — titles and contrast

`<title>`/`<desc>` presence is T1's assertion. Contrast (WCAG relative luminance), from
the snippet below; the palette is unchanged between rounds:

```
$ python3 - <<'PY'
def lum(h):
    r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
def cr(a, b):
    la, lb = sorted([lum(a), lum(b)], reverse=True); return (la + 0.05) / (lb + 0.05)
P, S = "#f5f0e6", "#22252a"
for name, h in [("ink", "#3f3a33"), ("ink-on-slate", "#e9e3d7"), ("sage", "#8a9c84"),
                ("dusk", "#7f93a5"), ("clay", "#c48a6c"), ("ochre", "#c7a86b"), ("mauve", "#9d8a9f")]:
    print(f"{name:14s} on paper {cr(h, P):5.2f}:1   on slate {cr(h, S):5.2f}:1")
PY
ink            on paper  9.92:1   on slate  1.36:1
ink-on-slate   on paper  1.13:1   on slate 12.03:1
sage           on paper  2.58:1   on slate  5.25:1
dusk           on paper  2.79:1   on slate  4.85:1
clay           on paper  2.57:1   on slate  5.27:1
ochre          on paper  2.00:1   on slate  6.77:1
mauve          on paper  2.81:1   on slate  4.81:1
```

The ink is swapped per ground (9.9:1 on paper, 12.0:1 on slate). The accents are
decorative loops, never text; the ink-free colourways (6, 7, 8, 10) rely on them alone
and are the ones to weigh against a dark ground.

## T12 — lint

```
$ uv run ruff format --check --line-length 88 docs/specs/issue-398/design/generate.py
1 file already formatted
exit=0
$ uv run ruff check --select E,F,W,I,UP,B --line-length 88 docs/specs/issue-398/design/generate.py
All checks passed!
exit=0
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-398/**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: docs/specs/issue-398/**/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 9 file(s)
Summary: 0 error(s)
exit=0
```

`docs/specs/*/design/**` is excluded from markdownlint by the repository's config (the
artifact is the contract), which is why the generator and the gallery are linted by hand
above rather than by the hook.

## T4a — the docs site builds with the mark

```
$ cd docs && bun install --frozen-lockfile && bun run docs:build
+ vitepress@1.6.4

127 packages installed [3.48s]
The language 'cron' is not loaded, falling back to 'txt' for syntax highlighting.

(!) Some chunks are larger than 500 kB after minification. Consider:
- Using dynamic import() to code-split the application
- Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
- Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.

The language 'cron' is not loaded, falling back to 'txt' for syntax highlighting.
[32m✓[0m building client + server bundles...
- rendering pages...
[32m✓[0m rendering pages...
build complete in 118.73s.
exit=0
```

The built output carries `favicon.svg`, `logo-light.svg`, `logo-dark.svg` and
`apple-touch-icon.png` at its root, and `index.html` links the favicon
(`<link rel="icon" href="/the-loop/favicon.svg" type="image/svg+xml">`) and the nav logo.
The build's two warnings (a `cron` fence with no grammar; chunk size) predate this work
item and are unrelated to it.

## T4b — the dashboard lints and builds with its favicon

```
$ cd ui && bun install --frozen-lockfile && bun run lint && bun run build

183 packages installed [3.33s]
$ oxlint --type-aware
rendering chunks...
computing gzip size...
dist/index.html                   2.05 kB │ gzip:  0.95 kB
dist/assets/index-DCKic1t0.css   20.77 kB │ gzip:  5.13 kB
dist/assets/index-eunMrwJY.js   310.84 kB │ gzip: 95.69 kB │ map: 1,338.35 kB
✓ built in 1.34s
exit=0
```

`dist/favicon.svg` is present and `dist/index.html` carries
`<link rel="icon" href="favicon.svg" type="image/svg+xml" />`.

## T12 (round 4) — every Markdown file, as the hook lints it

```
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/** !docs/specs/*/design/**
Linting: 1307 file(s)
Summary: 0 error(s)
exit=0
```

## T13 — the adopted surfaces, rendered

`design/screenshots/site-home-light.png` and `site-home-dark.png`: the built site's home
page under each appearance, captured by `screenshots.mjs --site` against
`bun run docs:preview --port 4173` — nav logo, hero image and favicon link in place.
`docs/assets/the-loop-logo-1024.png` viewed at size: the mark on its paper ground with
an 8 % inset, the square Slack expects.
