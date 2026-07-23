---
type: execution-log
workItem: issue-63
phase: implementation
status: complete
---

# Execution Log: split the-loop's config into CLI config and plugin config

> Append-only log of progress for the user's visibility.

## 2026-07-23 — implementation

- Added `.the-loop/cli-config.schema.json` (CLI config: `version` + `webhooks.ghWebhook`).
- Removed the `webhooks` block from `.the-loop/config.schema.json` and sharpened its
  description to name the plugin/CLI split.
- Added `cli/the_loop/config.py` resolving the CLI config
  (`$THE_LOOP_CLI_CONFIG` → `$XDG_CONFIG_HOME/the-loop/config.yaml`) with a deprecating
  fallback to the legacy per-repo `webhooks:` block; wired `gh_webhook.py` to it.
- Added `.the-loop/templates/cli-config.yaml`; stripped `webhooks:` from this repo's
  `.the-loop/config.yaml` and the init template, leaving pointer comments.
- Updated `.the-loop/manifest.yaml`, root + CLI READMEs, decision-021 + index, new
  `configuration` capability doc, and `cli` / `webhook-triggers` capability docs.
- Added `cli/tests/test_config.py` (7 tests).

### Self-check

- `uv run pytest cli` → **83 passed** (76 prior + 7 new).
- `uv run ruff check cli` → clean.
- `uv run pyright` on new/changed CLI modules → 0 errors.
- Both schemas + the CLI config template parse.
