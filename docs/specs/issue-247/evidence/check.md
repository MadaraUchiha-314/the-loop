---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#247"
---

# Evidence: the repository gates (issue-247, T13)

Every target `make check` runs, which is what CI runs (`hooks.prePush`, CI parity).
Run from the project root after the fix, the tests, the spec chain, the decision doc
and the capability-doc edits were all in place.

## `uv run ruff check cli hooks`

```console
All checks passed!
```

## `uv run ruff format --check cli hooks`

```console
229 files already formatted
```

## `uv run pyright cli`

```console
0 errors, 0 warnings, 0 informations
```

## `uv run python scripts/validate_config.py`

```console
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

## `npx --yes markdownlint-cli2@0.18.1 "**/*.md"`

The target this work item exists for — every markdown file in the repository, including
the four spec artifacts, the evidence files and the decision doc this branch adds.

```console
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 748 file(s)
Summary: 0 error(s)
```

## `uv run --project cli python -m pytest -q cli`

```console
2225 passed, 1 skipped in 130.59s (0:02:10)
```
