# Evidence — lint, types and schema (issue-174)

The repository's own quality gates, run from the root on the work item's branch. These are
the same commands CI runs (`pre-commit run --all-files`), so a local pass is a CI pass.
Output contains tool names, counts and file paths only.

## `make check` — the whole gate

```console
$ make check
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 451 file(s)
Summary: 0 error(s)
uv run ruff format --check cli hooks
170 files already formatted
uv run pyright cli
0 errors, 0 warnings, 0 informations
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
uv run pytest
1424 passed, 1 skipped in 50.04s
```

## T6 — markdownlint over every changed file

`markdownlint` runs over the whole tree (451 files), so every file this work item touched is
covered by the run above. One finding was raised during implementation and fixed:

```console
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 4 error(s)
docs/specs/issue-174/testing-plan.md:85:1  MD049/emphasis-style  Expected: asterisk; Actual: underscore
docs/specs/issue-174/testing-plan.md:85:19 MD049/emphasis-style  Expected: asterisk; Actual: underscore
docs/specs/issue-174/testing-plan.md:91:19 MD049/emphasis-style  Expected: asterisk; Actual: underscore
docs/specs/issue-174/testing-plan.md:91:52 MD049/emphasis-style  Expected: asterisk; Actual: underscore
```

`_Not yet executed._` → `*Not yet executed.*`; clean thereafter.

## The site's rendering constraints

`docs/capabilities/documentation.md` records three constraints the VitePress build cannot
check for itself (`markdown.html: false`, `ignoreDeadLinks: true`, and VitePress's slugify).
Checked by inspection on every page this work item changed:

| Constraint | Result |
|------------|--------|
| No raw HTML in any page | Pass — the only markup added is fenced `mermaid` and `text` blocks, plus `<br/>` **inside** mermaid node labels, which the Vue template compiler never sees because fenced code is not compiled |
| No em dash in a heading (it survives into the anchor id) | Pass — every heading added uses plain words; the em dashes are all in prose and table cells |
| Same-page fragment links target dot-free `##` headings | Pass — this work item adds no same-page fragment links |

Link resolution is verified in [`docs-review.md`](docs-review.md), because
`ignoreDeadLinks: true` means the build does not catch a broken internal link.
