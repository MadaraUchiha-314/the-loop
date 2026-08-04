---
type: execution-log
workItem: "issue-143"
phase: needs-review
status: in-progress
---

# Execution Log: the CLI installs the-loop's own plugin before a spawned session starts

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-143/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 |  | Issue #143 states the target settings shape; requirements add the guarantees that shape implies (never overwrite, validate, opt out). |
| design | 2026-08-04 |  | One seam: a third, independent step in `ClaudeCodeAdapter.prepare_environment`. The single judgement call — which settings file — is decision-054. |
| tasks-breakdown | 2026-08-04 |  | 12-task DAG |
| implementation | 2026-08-04 |  | Implemented on `claude/github-issue-143-3gdbp8` |
| needs-review | 2026-08-04 |  | PR opened; awaiting human review + named security sign-off (risk tier 4, `human-approves-pr`, `security.review.humanSignOffMinTier: 4`) |
| complete |  |  |  |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#145](https://github.com/MadaraUchiha-314/the-loop/pull/145) | all tasks 1–12 | open |

## Progress entries

### 2026-08-04 — spec chain

- **Phase:** requirements-definition → design → tasks-breakdown
- **Did:** Traced what actually reaches a spawned session today. `Dispatcher._prepare_environment`
  → `ClaudeCodeAdapter.prepare_environment` writes workspace trust (issue-90/136) and the
  bypass disclaimer, and nothing else; the spawn prompt then asks the session to run the
  loop, whose skill/commands/SessionStart hook live entirely in the **plugin**. On a machine
  where the operator never ran `/plugin marketplace add`, that prompt lands in a session with
  no loop — silently, since a missing plugin is not an error.
  The design's one real decision is *which* settings file. The two project-scoped options
  both put a daemon-authored file inside a working tree the agent is about to open a PR from
  (`.claude/settings.json` is tracked; `.claude/settings.local.json` is untracked only by
  convention), so the user settings file — where `/plugin install` writes, and where
  the-loop already writes `skipDangerousModePermissionPrompt` — wins, with its user-global
  scope stated out loud. Recorded as decision-054.
- **Checkpoint/tests:** n/a (documents)
- **Next:** implement the 12-task DAG.

### 2026-08-04 — implementation

- **Phase:** implementation
- **Did:** Test-first per task (`tdd.mode: standard`).
  - `cli/the_loop/harness_plugins.py` (new): `PluginConfig` + `ClaudePluginStore.enable()`,
    writing `extraKnownMarketplaces["the-loop"]` and `enabledPlugins["the-loop@the-loop"]`
    into the harness's user settings file, adding **only absent** keys, validating
    `marketplaceRepo` as `owner/repo`, and reporting a non-object container without touching
    the file.
  - `cli/the_loop/trust.py`: `_update_json` → public `update_json` so there is exactly one
    atomic, non-destructive writer for a harness's own config (no behaviour change).
  - `cli/the_loop/harness/{base,claude_code,__init__}.py`: `plugins` on the adapter, the
    independent third step in `prepare_environment`, `build_adapters(..., plugins=…)`.
  - `webhook/dispatcher.py` + `commands/{gh_webhook,poll}.py`: `routing.harnessPlugins`
    parsed into `RoutingConfig` and passed to all three adapter-building call sites.
  - Schema, both `cli-config.yaml` mirrors, `docs/config/cli/routing-options.md`,
    `docs/capabilities/interactive-sessions.md`, decision-054 + index, and this repository's
    own `.claude/settings.json` (the literal diff from the issue).
- **Checkpoint/tests:**
  - `uv run --project cli python -m pytest -q cli` → **1093 passed, 2 skipped**
  - `uv run ruff check cli hooks` / `ruff format --check` → clean
  - `uv run pyright cli` → **0 errors, 0 warnings**
  - `uv run python scripts/validate_config.py` → all VALID
  - `npx markdownlint-cli2 "docs/**/*.md"` → 0 errors
- **Notes:** three existing tests in `test_trust.py` and one in `test_trust_integration.py`
  used "the settings file does not exist" as a proxy for "the bypass disclaimer was not
  accepted" / "nothing was written". That proxy is no longer valid now that a second step
  writes to the same file, so each was tightened onto the key it actually cares about — and
  the integration one now doubles as the independence check (trust off, plugin still
  enabled).
- **Next:** self-review round, security review, reviewer briefing on the PR.

### 2026-08-04 — reviews

- **Phase:** needs-review
- **Did:** Self-review round 1 over the whole diff (see the table below), then the built-in
  security review (`security.review.mechanism: auto`).
- **Checkpoint/tests:** full suite re-run green after the review fixes.
- **Blockers:** human approval on the PR + a named security sign-off (risk tier 4).

### 2026-08-04 — rebased onto main (issue-142 landed)

- **Phase:** needs-review
- **Did:** Owner asked for a rebase on PR #145. `main` had moved by two commits, one of them
  breaking: [#144](https://github.com/MadaraUchiha-314/the-loop/pull/144) (issue-142)
  promoted `routing` out from under `webhooks.ghWebhook` to the top level, and took decision
  number **053**. Resolved by taking main's version of every conflicted file and re-applying
  this work item's additions on the new layout:
  - `harnessPlugins` re-inserted into the relocated top-level `routing` block in the schema
    and both `cli-config.yaml` mirrors (re-indented for the shallower nesting);
  - this work item's decision record renumbered `053 → 054` — every reference updated
    (`harness_plugins.py`, the spec chain, the capability doc, the config reference, the
    schema description, the decisions index);
  - `webhooks.ghWebhook.routing` → `routing` throughout this work item's prose and the
    `PluginConfig` docstring.
- **Checkpoint/tests:** full suite re-run on the rebased branch — **1104 passed, 2 skipped**
  (11 more than before: main's own new tests); ruff clean, pyright 0 errors, config VALID,
  markdownlint 0 errors.
- **Notes:** issue-142 also shipped a config migration for the `routing` move; the new
  `harnessPlugins` key sits inside `routing`, so it travels with the block and needs no
  migration of its own.
- **Next:** human approval + named security sign-off.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop (this session) | findings fixed — see the implementation entry's *Notes* (stale existence-proxy assertions) and the fail-closed guard on `marketplaceRepo` | PR #145 |
| 2 | security | built-in security-review | see the Security review section | PR #145 |

> `reviews.critics[]` is empty in this repository's `harness-config.yaml`, so no critic
> round could run; a round that cannot run is recorded rather than counted
> (`reference/reviewing.md`).

## Security review (gate)

- **Mechanism:** security-review skill (`security.review.mechanism: auto`)
- **Outcome:** pass — the write takes no untrusted input (marketplace/plugin names are
  source constants; the repository comes from the operator's own config file, never from an
  event payload or a cloned repo), `marketplaceRepo` is validated as `owner/repo` and fails
  closed, existing values are never overwritten, no subprocess or network call is added, and
  every failure degrades to today's behaviour rather than to a wider write.
- **Residual risk (deliberate, documented):** `enabledPlugins` in the user settings file is
  user-global, so the plugin — including its SessionStart hook — loads in the operator's own
  interactive sessions too; and pointing `marketplaceRepo` at a fork means running that
  fork's code. Both are stated in the schema, the config reference, the capability doc and
  decision-054. `harnessPlugins.enabled: false` is the opt-out.
- **Human sign-off:** pending — risk tier 4 (`.the-loop/cli-config.schema.json` is an
  `autonomy.sensitivePaths` match) ≥ `security.review.humanSignOffMinTier: 4`.

## Final validation evidence

| Acceptance criterion | Evidence |
|---|---|
| R1.1 plugin enabled before the harness starts | `test_the_plugin_is_enabled_before_the_harness_starts` — the snapshot is taken *inside* the faked spawn, so it proves ordering, not just the end state |
| R1.2 idempotent | `test_enable_is_idempotent` (byte-identical file on the second call) |
| R1.3 cursor no-op | `test_cursor_has_no_plugin_surface_and_stays_a_no_op` |
| R2.1 / R2.2 existing values kept | `test_an_existing_marketplace_entry_is_left_alone`, `test_a_deliberately_disabled_plugin_stays_disabled` |
| R2.3 odd-shaped file | `test_a_non_object_container_is_reported_and_left_untouched`, `test_an_unparseable_settings_file_is_never_overwritten` |
| R2.4 malformed repo | `test_a_malformed_marketplace_repo_writes_nothing` (5 hostile values) |
| R2.5 empty repo | `test_an_empty_marketplace_repo_enables_without_registering` |
| R3.1 opt-out | `test_plugins_disabled_writes_nothing`, `test_disabled_plugins_leave_the_settings_file_alone` |
| R3.2 fork repo | `test_a_custom_marketplace_repo_reaches_the_settings_file` |
| R3.3 audit trail | `test_the_plugin_is_enabled_before_the_harness_starts` asserts the `workspace.trusted` `applied` note |
| R3.4 best-effort | existing `test_an_exploding_adapter_hook_does_not_wedge_the_work_item` covers the path unchanged |
| R3.5 independent switches | `test_the_two_pre_spawn_steps_are_independently_switchable`, `test_disabled_trust_leaves_the_harness_config_alone` |
| R4.1 this repo dogfoods it | `.claude/settings.json` diff |
| Gates | 1104 passed / 2 skipped · ruff clean · pyright 0 errors · config VALID · markdownlint 0 errors |
