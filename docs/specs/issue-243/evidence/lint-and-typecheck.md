# Lint, format and type checks

Testing-plan row **T7**, the same commands CI runs (`make check`).

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
226 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2 "**/*.md"
Summary: 0 error(s)

$ uv run python scripts/validate_config.py
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```
