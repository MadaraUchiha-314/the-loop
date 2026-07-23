---
type: tasks
phase: tasks-breakdown
workItem: issue-63
status: approved
approvedBy: ["@MadaraUchiha-314 (issue #63)"]
overrides: {}
---

# Tasks: split the-loop's config into CLI config and plugin config

> Phase 3 of 3. Derives from [`design.md`](design.md).

## Task DAG

- **T1 — CLI config schema.** Add `.the-loop/cli-config.schema.json` (top-level
  `version` + `webhooks.ghWebhook`). _(no deps)_
- **T2 — Trim plugin schema.** Remove `webhooks` from `.the-loop/config.schema.json`;
  update its top-level description. _(no deps)_
- **T3 — CLI config loader.** Add `cli/the_loop/config.py` with `cli_config_path`,
  `load_cli_config`, `load_gh_webhook_config` (+ legacy fallback + deprecation warning).
  _(after T1)_
- **T4 — Wire commands.** Point `gh_webhook.py::_load_config_defaults` at the loader.
  _(after T3)_
- **T5 — Templates + repo config.** Add `.the-loop/templates/cli-config.yaml`; strip the
  `webhooks:` block from `.the-loop/config.yaml` and `.the-loop/templates/config.yaml`,
  leaving pointer comments. _(after T1)_
- **T6 — Manifest.** Register the new schema + template in `.the-loop/manifest.yaml`.
  _(after T1, T5)_
- **T7 — Docs.** Root + CLI READMEs; new `configuration` capability doc; update `cli` /
  `webhook-triggers` capability docs; `decision-021` + decisions index. _(after T3)_
- **T8 — Tests.** `cli/tests/test_config.py`; run pytest + ruff + pyright green.
  _(after T4)_

## Ready-to-ship gate

- [x] All tasks complete; `pytest` (cli), `ruff`, `pyright` green.
- [x] Both JSON schemas parse; template YAML parses.
- [x] Capability docs updated in this PR (`configuration`, `cli`, `webhook-triggers`).
- [x] Backward-compat path exercised by a test.
