# Lint, format, types and config validation (issue-270)

```console
$ uv run ruff check cli hooks
All checks passed!

$ uv run ruff format --check cli hooks
247 files already formatted

$ uv run pyright cli
0 errors, 0 warnings, 0 informations

$ npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 817 file(s)
Summary: 0 error(s)

$ uv run python scripts/validate_config.py
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Clean on the first run of each; nothing was reformatted or suppressed.
