# Lint, format and typecheck

The same commands `hooks.prePush` and CI run.

```console
$ uv run ruff check cli/
All checks passed!

$ uv run ruff format --check cli/
222 files already formatted

$ uv run pyright cli/the_loop/poller/
0 errors, 0 warnings, 0 informations

$ npx markdownlint-cli2@0.18.1 "docs/specs/issue-246/**/*.md" "docs/capabilities/webhook-triggers.md"
Summary: 0 error(s)
```
