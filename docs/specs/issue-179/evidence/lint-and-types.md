# Evidence — lint, types and config validation (issue-179)

The same commands CI runs, from this repository's checkout on 2026-08-08.

```console
$ uvx ruff check cli
All checks passed!

$ uvx ruff format --check cli
171 files already formatted

$ uv run --directory cli pyright
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml
```

Markdown, over every document this work item touched (the spec chain, the two decision
records and their index, the capability doc, the skill and its references, the command
doc and the CLI doc):

```console
$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-179/*.md" "docs/decisions/decision-06*.md" \
    "docs/capabilities/process-graph.md" "skills/the-loop/**/*.md" "commands/verify-work.md" \
    "docs/cli/commands/graph.md"
markdownlint-cli2 v0.18.1 (markdownlint v0.38.0)
Linting: 48 file(s)
Summary: 0 error(s)
```
