# Evidence — checks, config validation and the gate (issue-157)

> Run from the repository root on 2026-08-06. These are the same commands CI runs
> (`make check`), so local and CI cannot disagree.

## T10 — `make validate`

```text
uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Nothing this work item changes is configured, which is the claim: both shipped
configs and both templates still validate untouched.

## all — `make lint`

```text
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Finding: **/*.md !**/node_modules/** !cli/node_modules/** !**/.venv/** !docs/.vitepress/dist/** !docs/.vitepress/cache/** !docs/operating-model/reference/**
Linting: 436 file(s)
Summary: 0 error(s)
```

## all — `make format-check`

```text
uv run ruff format --check cli hooks
166 files already formatted
```

## all — `make typecheck`

```text
uv run pyright cli
0 errors, 0 warnings, 0 informations
```

## the-loop's own gate

`uv run --project cli the-loop check issue-157 --recompute`:

```text
issue-157: UNMET (at requirements-approval)
  WAIT   requirements-approval
         · no authorized feedback yet
  ····   2 node(s) not reached yet
```

WAIT at `requirements-approval` is the normal state of an open PR: the human gate
has had no authorized feedback yet.
