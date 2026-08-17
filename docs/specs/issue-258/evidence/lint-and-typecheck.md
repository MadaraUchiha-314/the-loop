# Evidence — lint, format, typecheck, config validation, docs parity (T12)

The `make` targets CI runs, on the tree this pull request proposes. `hooks.preCommit` /
`hooks.prePush` are `[lint, typecheck, unit-test]` and pre-commit runs the same tools, so
this is the CI-parity check the-loop's own `reference/tooling.md` requires.

## Raw output

```text
### make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 775 file(s)
Summary: 0 error(s)

### make format-check
uv run ruff format --check cli hooks
235 files already formatted

### make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations

### make validate
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

### docs<->schema parity
........                                                                 [100%]
8 passed in 0.09s
```

## What each gate proves for this work item

| Gate | Why it is here |
|---|---|
| `ruff check` | the new module-level constants, the parse function and the `require_branch` plumbing carry no unused import, shadow or undefined name |
| `markdownlint` (775 files) | the spec chain, the decision and every documentation page edited here pass the project's markdown rules — including the two long tables in `routing-options.md` and the capability page |
| `ruff format --check` | the tree matches the formatter, so pre-commit will not rewrite it under a reviewer |
| `pyright` | `TmuxConfig.session_per_pr` is a `str` and every construction site was updated to pass one. Two test call sites were passing `False` positionally-by-keyword; they now say `"never"`, which is what they meant. The registry's `session_for(session_per_pr=...)` stays a **boolean** on purpose — policy is the caller's — and typechecks as one |
| `validate_config.py` | this repository's own `.the-loop/cli-config.yaml` (now stating `sessionPerPr: cross-repository` explicitly) and the shipped template both validate against the changed schema |
| `test_docs_parity.py` | P3/P4/P5 — the documented `tmux.sessionPerPr` option still exists in the schema, every schema leaf is still documented, and the option's heading still states Type and Default. This is the gate that would have caught a schema change shipped without a doc change |
| `test_config_schema_parity.py` | `.the-loop/cli-config.schema.json` and the packaged copy under `cli/the_loop/schemas/` are **byte**-identical after the edit |

No secret, token, hostname or personal datum appears above: it is tool banners, file counts
and repository-relative paths.
