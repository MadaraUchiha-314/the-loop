# Evidence: lint, format, type-check and the-loop's own gate

Work item: issue-165 · re-run after the owner's review removed length budgets (PR #168).

## Lint (ruff + markdownlint)

```console
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 423 file(s)
Summary: 1 error(s)
docs/specs/issue-165/evidence/checks.md:8:1 MD014/commands-show-output Dollar signs used before commands without showing output [Context: "$ make lint"]
make: *** [Makefile:16: lint] Error 1
```

## Format check

```console
$ make format-check
uv run ruff format --check cli hooks
166 files already formatted
```

## Type check

```console
$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## the-loop's own gate, as CI runs it

`WAIT` at a human-approval node is the normal state of an open PR; CI uses
`--fail-on block`, so this passes.

```console
$ uv run the-loop check issue-165 --recompute
issue-165: UNMET (at requirements-approval)
  WAIT   requirements-approval
         · no authorized feedback yet
  ····   3 node(s) not reached yet
```
