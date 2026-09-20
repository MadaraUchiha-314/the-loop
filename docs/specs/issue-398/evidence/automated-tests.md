---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#398"
---

# Evidence: automated checks (issue-398)

Run from the repository root on 2026-09-20, on the branch of the delivering PR. Rows
refer to [`testing-plan.md`](../testing-plan.md).

## T1 — the generator's checker (red first, then green)

Before the first render — the checker against an empty folder:

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

On the final files:

```
$ python3 docs/specs/issue-398/design/generate.py --check
ok — 6 files match, well-formed, self-contained, titled
exit=0
```

Two intermediate red runs are worth recording: the first size budget was breached by the
coil (58 903 bytes at 720 samples → 396 samples, 38 597 bytes) and the planetary mark
(51 515 → 37 815 bytes once the chevrons went and the samples dropped); and the first
token list flagged the SVG namespace URL (`contains 'http:'`) — the check now refuses any
`href` that is not a `#fragment` instead.

## T6 — a regeneration leaves the tree clean

```
$ python3 docs/specs/issue-398/design/generate.py && git diff --exit-code --stat -- docs/specs/issue-398/design/
wrote option-1-gimbal.svg (30.3 kB)
wrote option-2-one-line.svg (25.4 kB)
wrote option-3-coil.svg (38.6 kB)
wrote option-4-rings.svg (27.6 kB)
wrote option-5-planetary.svg (37.8 kB)
wrote logo-options.html (197.7 kB)
exit=0
```

## T5 — the rendered evidence

```
$ CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome \
  node docs/specs/issue-398/design/screenshots.mjs docs/specs/issue-398/design/screenshots
gallery-light
gallery-dark
option-1-gimbal-paper
option-1-gimbal-slate
option-2-one-line-paper
option-2-one-line-slate
option-3-coil-paper
option-3-coil-slate
option-4-rings-paper
option-4-rings-slate
option-5-planetary-paper
option-5-planetary-slate
```

Playwright 1.63.0 with the Chromium already installed for the dashboard's evidence
script; resolved through a `node_modules` link beside the script, removed afterwards.
The `-slate` captures are `<img>` embeddings under an emulated dark scheme and show the
light ink, so each standalone file's own `prefers-color-scheme` rule is what is proved.
Files: [`../design/screenshots/`](../design/screenshots/).

## T9 — titles and contrast

`<title>`/`<desc>` presence is T1's assertion. Contrast (WCAG relative luminance), from
the snippet below:

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
decorative loops, never text; every option has an ink element or an overlap that carries
the silhouette.

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
