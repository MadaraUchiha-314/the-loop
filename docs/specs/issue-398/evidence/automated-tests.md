---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Evidence: automated checks (issue-398)

Run from the repository root on 2026-09-20, on the branch of the delivering PR. Rows
refer to [`testing-plan.md`](../testing-plan.md). **Round 2** (after the owner's review
of round 1) re-ran every row; round 1's outputs are kept below where the red→green
record lives there.

## T1 — the generator's checker (red first, then green)

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

Round 2, on the final files (budget 64 kB, `requirements.md` NFR):

```
$ python3 docs/specs/issue-398/design/generate.py --check
ok — 6 files match, well-formed, self-contained, titled
exit=0
```

Round 1 also had two intermediate reds worth keeping: the coil and planetary marks over
the size budget (58 903 and 51 515 bytes, brought under by fewer samples and dropped
chevrons), and the first token list flagging the SVG namespace URL (`contains 'http:'`)
— the check refuses a non-fragment `href` or `url(` instead.

## T6 — a regeneration leaves the tree clean

```
$ python3 docs/specs/issue-398/design/generate.py && git diff --exit-code --stat -- docs/specs/issue-398/design/
wrote option-1-loop.svg (50.6 kB)
wrote option-2-knot.svg (46.2 kB)
wrote option-3-flick.svg (42.1 kB)
wrote option-4-clip.svg (39.3 kB)
wrote option-5-enso.svg (41.9 kB)
wrote logo-options.html (231.2 kB)
exit=0
```

## T5 — the rendered evidence

```
$ CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome CHROMIUM_NO_SANDBOX=1 \
  node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots
gallery-light
gallery-dark
option-1-loop-paper
option-1-loop-slate
option-2-knot-paper
option-2-knot-slate
option-3-flick-paper
option-3-flick-slate
option-4-clip-paper
option-4-clip-slate
option-5-enso-paper
option-5-enso-slate
```

Playwright 1.63.0 with the Chromium already installed for the dashboard's evidence
script; resolved through a `node_modules` link beside the script, removed afterwards.
`CHROMIUM_NO_SANDBOX=1` because this container runs as root: Playwright adds the flag
for a root user itself (a run without the variable produced the same twelve captures),
so the variable only makes explicit what happens here anyway; on a machine with a
working sandbox the flag is never passed. The `-slate` captures are `<img>` embeddings
under an emulated dark scheme and show the light ink, so each standalone file's own
`prefers-color-scheme` rule is what is proved; the knot's mask-carved weave renders on
both grounds. Files: [`../design/screenshots/`](../design/screenshots/).

## T8 — the abuse case, probed

The checker validates each standalone SVG from its **parsed tree against an allowlist**
(elements `svg, title, desc, style, path, mask, rect`; a fixed attribute set; a `mask`
must reference a fragment; a stylesheet may not `@import` or reference anything
outside the file) and scans the HTML gallery case-insensitively for the same absences
with a fragment-only rule for `href`/`url`. A planted script, handler, image and import
each fail; fragments pass:

```
$ python3 - <<'PY'
import sys; sys.path.insert(0, "docs/specs/issue-398/design")
import generate as g, xml.etree.ElementTree as ET
bad = g.render()["option-1-loop.svg"].replace(
    "</svg>",
    '<script>alert(1)</script><path d="M0 0" fill="url(http://x/y)" onclick="x()"/>'
    '<image href="http://x/y.png"/><style>@import url(http://x/a.css)</style></svg>')
print("\n".join(g.svg_problems("probe.svg", ET.fromstring(bad))))
for html in ("<a HREF='http://x'>", '<use href="#ok"/>', "url(#mask)", "url( http://x )"):
    print(f"{html!r:28} -> {'flagged' if g.EXTERNAL_REF.search(html) else 'ok'}")
PY
probe.svg: element <script> is not in the allowlist
probe.svg: attribute 'onclick' on <path> is not in the allowlist
probe.svg: element <image> is not in the allowlist
probe.svg: attribute 'href' on <image> is not in the allowlist
probe.svg: the stylesheet references something outside the file
"<a HREF='http://x'>"        -> flagged
'<use href="#ok"/>'          -> ok
'url(#mask)'                 -> ok
'url( http://x )'            -> flagged
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

The ink is swapped per ground (9.9:1 on paper, 12.0:1 on slate). Round 2 uses ink,
dusk and clay; the accents are decorative loops, never text, and every option's
silhouette is carried by ink.

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
