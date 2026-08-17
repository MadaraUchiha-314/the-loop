# Lint, format and type checks — clean

```
$ make format-check
uv run ruff format --check cli hooks
246 files already formatted

$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations

$ make validate
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

```
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
Summary: 0 error(s)   # full run recorded after this file was finalized
```
