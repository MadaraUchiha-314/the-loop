# Evidence — lint, format and types

The repository's own gates (`hooks.prePush: [lint, typecheck, unit-test]`), run on this
branch.

## `make lint`

Ruff over `cli` and `hooks`, then markdownlint over every markdown file in the repository —
including the four spec artifacts and the decision record added here.

```text
All checks passed!
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 723 file(s)
Summary: 0 error(s)
```

## `make format-check`

```text
uv run ruff format --check cli hooks
226 files already formatted
```

## `make typecheck`

```text
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

`_endpoint_cwd` returns `Optional[str]`, and pyright confirms the `None` branch is handled
at its one call site before the value reaches `TmuxRunner.spawn`.
