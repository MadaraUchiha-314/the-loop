---
type: tasks
phase: tasks-breakdown
workItem: issue-143
status: approved
approvedBy: []
overrides: {}
---

# Tasks: the CLI installs the-loop's own plugin before a spawned session starts

> Phase 3 of 3 (requirements → design → tasks). Derived from the locked
> [`design.md`](./design.md).

## Task list

- [x] 1. Unit-pin the writer's contract (red)
  - New `cli/tests/test_harness_plugins.py`: exact-shape write into a fresh settings file;
    idempotence; existing marketplace / existing `false` enablement untouched; non-object
    container and malformed `marketplaceRepo` → `ok=False` with the file untouched; empty
    repo → plugin only; `$CLAUDE_CONFIG_DIR` honoured; `PluginConfig.from_mapping`.
  - _Depends on:_ none
  - _Requirements:_ AC R1.1, R1.2, R2.1–R2.5, R3.2
  - _Test:_ `uv run pytest cli/tests/test_harness_plugins.py` (red — module absent)

- [x] 2. Integration-pin the pre-spawn step (red)
  - `cli/tests/test_trust_integration.py`: a scenario asserting the plugin keys are in the
    settings file **when the harness process starts**, and that `workspace.trusted` names
    the file. Gherkin docstring + `Requirement:` link, per `testing.gherkinDocstrings`.
  - _Depends on:_ none
  - _Requirements:_ AC R1.1, R3.3
  - _Test:_ `uv run pytest cli/tests/test_trust_integration.py -k plugin` (red)

- [x] 3. Make the JSON writer reusable
  - `cli/the_loop/trust.py`: rename `_update_json` → `update_json` (public), update its four
    call sites and the module docstring. No behaviour change.
  - _Depends on:_ none
  - _Requirements:_ NFR (no duplicated atomic writer)
  - _Test:_ `uv run pytest cli/tests/test_trust.py`

- [x] 4. Write the plugin store (green)
  - `cli/the_loop/harness_plugins.py`: `PluginConfig`, `ClaudePluginStore.enable()`,
    the name constants and the `owner/repo` guard, delegating path resolution to
    `ClaudeTrustStore`.
  - _Depends on:_ 1, 3
  - _Requirements:_ AC R1.1, R1.2, R2.1–R2.5
  - _Test:_ task 1 goes green

- [x] 5. Call it from the Claude Code adapter (green)
  - `cli/the_loop/harness/claude_code.py` + `base.py` + `__init__.py`: `plugins` on the
    adapter, the independent third step in `prepare_environment`, `build_adapters(...,
    plugins=…)`. Cursor stays a no-op.
  - _Depends on:_ 4
  - _Requirements:_ AC R1.1, R1.3, R3.5
  - _Test:_ `uv run pytest cli/tests/test_trust.py cli/tests/test_harness_plugins.py`

- [x] 6. Plumb the config through routing
  - `RoutingConfig.harness_plugins` + `from_mapping`; the three `build_adapters` call sites
    (`webhook/dispatcher.py`, `commands/gh_webhook.py`, `commands/poll.py`).
  - _Depends on:_ 5
  - _Requirements:_ AC R3.1, R3.2
  - _Test:_ task 2 goes green

- [x] 7. Schema + operator config
  - `.the-loop/cli-config.schema.json` (`harnessPlugins`), `.the-loop/cli-config.yaml` and
    `skills/the-loop/templates/cli-config.yaml`.
  - _Depends on:_ 6
  - _Requirements:_ AC R3.1, R3.2
  - _Test:_ `uv run python scripts/validate_config.py`

- [x] 8. Event descriptions
  - `cli/the_loop/eventlog.py`: `workspace.trusted` / `workspace.trust_failed` describe
    pre-spawn preparation including plugin enablement.
  - _Depends on:_ 6
  - _Requirements:_ AC R3.3, R3.4
  - _Test:_ `uv run pytest cli/tests/test_eventlog.py`

- [x] 9. Config reference docs
  - `docs/config/cli/routing-options.md`: `harnessPlugins.enabled` and
    `harnessPlugins.marketplaceRepo`, each with Type + Default and the machine-global
    warning.
  - _Depends on:_ 7
  - _Requirements:_ AC R3.1, R3.2
  - _Test:_ `uv run pytest cli/tests/test_docs_parity.py`

- [x] 10. Capability doc + decision record
  - `docs/capabilities/interactive-sessions.md` (behaviour + history row),
    `docs/decisions/decision-054.md` + `docs/decisions/decisions.md`.
  - _Depends on:_ 6
  - _Requirements:_ loop gate (capability fold-in)
  - _Test:_ `uv run pytest cli/tests/test_docs_parity.py`

- [x] 11. Dogfood in this repository
  - `.claude/settings.json`: the two entries from the issue.
  - _Depends on:_ none
  - _Requirements:_ AC R4.1
  - _Test:_ JSON validity check from CI (`uv run python -c "import json; …"`)

- [x] 12. Full check + evidence
  - `make lint typecheck test` (or the equivalent `uv run` commands), execution-log
    evidence, self-review round, reviewer briefing on the PR.
  - _Depends on:_ 1–11
  - _Requirements:_ ready-to-ship gate
  - _Test:_ full suite green
