# Evidence: the repository's own gates (issue-212)

Testing-plan row **T14**. The same commands CI runs (`Makefile`, via pre-commit) — local ==
CI is the rule (`hooks.preCommit`/`prePush`).

## Lint

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
223 files already formatted
```

Seven files needed `ruff format` on first pass (the five new modules plus two test files);
formatted and re-checked, as recorded above.

## Type check

```console
$ uv run pyright cli
0 errors, 0 warnings, 0 informations
```

One error surfaced and was fixed rather than suppressed: the new router-parity assertion
read `.operation_id` off `BaseRoute`, which does not declare it. Narrowed with
`isinstance(route, APIRoute)` — the same narrowing FastAPI itself does.

## Markdown

```console
$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 671 file(s)
Summary: 0 error(s)
```

## Config validation

```console
$ uv run python scripts/validate_config.py
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

No schema changed in this work item — no CLI-config key was added, removed or moved — so
this row is a confirmation rather than a check of new content.

## Tests

Full run in [`regression.md`](regression.md): **2098 passed, 1 skipped**.
