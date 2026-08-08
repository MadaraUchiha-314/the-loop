# Evidence: lint, types, formatting, config validation

> All commands are the same ones the pre-commit hooks and CI run.

```text
$ uvx ruff check cli
All checks passed!

$ uvx ruff format --check cli
170 files already formatted

$ uv run --directory cli pyright
0 errors, 0 warnings, 0 informations

$ uv run python scripts/validate_config.py
VALID   .the-loop/harness-config.yaml
VALID   .the-loop/collaborators.yaml
VALID   skills/the-loop/templates/harness-config.yaml
VALID   skills/the-loop/templates/collaborators.yaml
VALID   .the-loop/cli-config.yaml
VALID   skills/the-loop/templates/cli-config.yaml

$ npx --yes markdownlint-cli2@0.18.1 "docs/specs/issue-177/*.md" \
    "docs/decisions/decision-067.md" "docs/capabilities/process-graph.md" \
    "docs/cli/commands/graph.md" "skills/the-loop/reference/workflow.md" \
    "skills/the-loop/SKILL.md" "commands/init.md"
Linting: 11 file(s)
Summary: 0 error(s)
```
