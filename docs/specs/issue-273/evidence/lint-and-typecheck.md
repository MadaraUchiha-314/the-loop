# Static analysis (issue-273)

`make lint` runs `ruff check` and `markdownlint-cli2` over the whole tree; `make
format-check` is the separate CI-parity target for `ruff format`; `make typecheck` runs
`pyright` over `cli`. `scripts/validate_config.py` is run
alongside them because the spec chain adds files under `docs/specs/` and the harness config
schema is a `sensitivePaths` entry worth re-checking even when untouched.

## Output

```console
$ make lint
uv run ruff check cli hooks
All checks passed!
npx --yes markdownlint-cli2@0.18.1 "**/*.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 837 file(s)
Summary: 0 error(s)

$ make format-check
uv run ruff format --check cli hooks
250 files already formatted

$ make typecheck
uv run pyright cli
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   cli/the_loop/harness-config.default.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Two first-run failures were fixed rather than waived:

- **MD038** on a `testing-plan.md` table cell that wrapped a scenario name containing a
  backticked `` `pending` `` inside another code span, producing spaces inside the outer
  span. The inner backticks were dropped.
- **`ruff format`** on `graphlink.py` and `test_graphlink.py` — the new multi-line
  condition and one new assertion were wrapped differently from the formatter's choice.
  `make lint` does not catch this (`format-check` is its own target, and the pre-commit
  hook is what runs it), so it was run explicitly.
