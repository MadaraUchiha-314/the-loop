# Evidence: lint, formatting and type checks (issue-167)

Same commands the pre-commit/pre-push hooks and CI run (`hooks.preCommit`,
`hooks.prePush`) — no CI-only variant.

## ruff

```console
$ uv run --directory cli ruff check .
All checks passed!

$ uv run --directory cli ruff format --check .
166 files already formatted
```

Two files were reformatted by `ruff format` during implementation
(`the_loop/graph/hooks/artifacts.py`, `tests/test_graph_parity.py`) and the reformatted
versions are what is committed.

## pyright

```console
$ uv run --directory cli pyright
0 errors, 0 warnings, 0 informations
```

## markdownlint

Every markdown file this work item adds or edits, through the project's own config:

```console
$ npx markdownlint-cli2 "docs/specs/issue-167/*.md" "docs/decisions/decision-063.md"
markdownlint-cli2 v0.23.2 (markdownlint v0.41.1)
Linting: 6 files
Summary: 0 issues in 0 files
```
