---
type: execution-log
workItem: issue-142
phase: needs-review
status: in-progress
---

# Execution Log: `routing` is a top-level concern, not a property of the webhook receiver

> Append-only log of progress. The-loop keeps the work item's `loop:<phase>` label in sync
> with the `phase` front-matter above.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 | — | Issue #142 specifies the target shape and acceptance criteria; the one open judgement call (a config declaring **both** blocks) resolved in R3.4. |
| design | 2026-08-04 | — | Four decisions: no compatibility read (D1), the shared accessor's home (D2), the hot-reloader's widened read (D3), both-blocks precedence (D4). |
| tasks-breakdown | 2026-08-04 | — | 8 tasks, two independent roots (migration, schema). |
| implementation | 2026-08-04 | — | All 8 complete; full suite green. |
| needs-review | 2026-08-04 | *pending* | Tier 4 (`autonomy.sensitivePaths` matches the CLI schema) → `human-approves-pr` **plus** a named human security sign-off. |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#143](https://github.com/MadaraUchiha-314/the-loop/pull/143) | Tasks 1–8 (whole work item) | open |

## Progress entries

### 2026-08-04 — spec locked (requirements → design → tasks)

- **Phase:** tasks-breakdown
- **Did:** Wrote the three artifacts. Classified every `webhooks.ghWebhook` key by which
  ingress it governs (requirements § Analysis) and confirmed the split is clean: only the
  HTTP listener, the pidfile and the event filter are receiver-specific. Read the prior art
  the issue points at (`migrations.py`'s four properties, issue-109 and issue-128) and
  matched its shape rather than inventing a second convention.
- **Checkpoint/tests:** none yet (no code).
- **Next:** task 1 — the migration, test-first.

### 2026-08-04 — tasks 1–2: the migration and the shared accessor

- **Phase:** implementation
- **Did:** Wrote the failing tests first (11 red), then `CURRENT_CONFIG_VERSION = 0.4.0`,
  the `assert_current` refusal, `_promote_routing` (per-key precedence, empty-container
  removal) and `cli_config.load_routing_config`. `apply_integrations` now fans the gh
  binary out to the promoted block.
- **Checkpoint/tests:** `pytest cli/tests/test_migrations.py` → **red → green** (23
  passed).
- **Next:** task 3, the schema.

### 2026-08-04 — tasks 3–5: schema, receiver, poller and sessions

- **Phase:** implementation
- **Did:** Moved the schema definition verbatim (asserted: with the block popped from
  both revisions, the documents are byte-equal, so nothing inside it drifted). Split
  `_build_routing` into its two blocks, widened the hot-reloader to the whole document
  (design D3), and replaced the `from .gh_webhook import _load_config_defaults` import in
  `poll.py` and `sessions_cmd.py` with the shared accessor.
- **Checkpoint/tests:** full suite → 65 failures, all of them fixtures still writing the
  old shape *plus* this repository's own `cli-config.yaml` being correctly refused. That
  refusal is the mechanism working: the dogfooded config had to migrate like everyone
  else's.
- **Next:** task 6 — the config files and the docs.

### 2026-08-04 — tasks 6–7: config, docs, capabilities, decision

- **Phase:** implementation
- **Did:** Promoted the block in both `cli-config.yaml` files (this repo's and the shipped
  template), bumped both to `0.4.0`, and replaced the per-option *"NOT webhook-only"* note
  with the block's own scope header — the nesting says it now. Renamed the path across 18
  live docs and docstrings, left `docs/decisions/` and merged specs as written (R5.4,
  design D6). Added decision-053 and history rows on both capability docs.
- **Checkpoint/tests:** `pytest cli/tests/` → **1078 passed, 2 skipped**, including
  `test_docs_parity` P3/P4, which is what mechanically proves the schema and the docs
  moved together.
- **Next:** task 8 — full validation.

### 2026-08-04 — task 8: validation and evidence

- **Phase:** needs-review
- **Did:** Ran the configured tooling and proved the migration end-to-end on a hand-written
  pre-issue-142 config (evidence below).
- **Checkpoint/tests:** `ruff check` clean · `ruff format` applied, then clean ·
  `pyright cli` → 0 errors · `markdownlint` → 0 errors across 346 files ·
  `scripts/validate_config.py` → both `cli-config.yaml` files VALID against the promoted
  schema · `pytest cli/tests/` → 1078 passed, 2 skipped.
- **Next:** post the reviewer briefing on the PR; request the tier-4 human approval and the
  named security sign-off.

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| 1 | self | the-loop | New findings: `apply_integrations` still dug the old subtree (silently returning the unfanned binary rather than failing); the hot-reloader read only the receiver block, so a `routing` edit would have stopped hot-reloading; `--route`'s default still came from `defaults.get("routing")`. All three fixed before the suite was re-run. | this log |
| 2 | self | the-loop | New findings: the `ghBinary` sites were declared only under the old path, so a hand-written config that had already promoted `routing` could smuggle a removed key past the gate. `_GH_BINARY_SITES` now lists both spellings. | this log |
| 3 | self | the-loop | Zero new findings (converged): full suite, lint, typecheck, markdownlint and schema validation all green; every acceptance criterion traced to a test or to the evidence below. | this log |
| 4 | critic | — | **unavailable** — `reviews.critics: []` in this repository's harness config, so no critic harness is configured to run. Does **not** count toward `reviews.criticReviewCount`; the PR review is the gate that replaces it. | `.the-loop/harness-config.yaml` |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no built-in
  security-review skill invoked for a relocation with no new code path).
- **Outcome:** **pass.** No trust boundary is added, removed or moved *in behaviour* — the
  block that declares them changes address only. Both fail-closed layers verified:
  (1) a config carrying the old key does not load at all, proven by the refusal below;
  (2) an absent `routing` block still resolves `authorizedUsers` to empty, so both
  ingresses act on no human-authored event, and both warnings now name the key that
  actually exists. The one migration behaviour that *could* have changed authorization —
  merging two `authorizedUsers` lists — is explicitly refused: the top-level block wins
  whole, per key, and every dropped value is reported
  (`test_a_half_migrated_config_prefers_the_new_block_and_reports_what_it_dropped`).
- **Human sign-off:** **required and pending.** Risk tier 4 (the change touches
  `.the-loop/cli-config.schema.json`, matching `autonomy.sensitivePaths`), and
  `security.review.humanSignOffMinTier` is 4 — requested on the PR.

## Final validation evidence

**R1 — `routing` is top-level.** The schema move is verbatim, asserted rather than
eyeballed: popping the block from both revisions leaves byte-equal documents.
`webhooks.ghWebhook` now declares exactly `host`, `port`, `path`, `secretEnv`, `pidfile`,
`events`. Both `cli-config.yaml` files validate against it.

**R2 — an un-migrated config is refused, loudly.**

```text
$ the-loop --config ./mig/cli-config.yaml events list
ConfigTooOld: this CLI config still declares `webhooks.ghWebhook.routing`. That block
governs BOTH ingresses — the poller reads it verbatim for dispatch — so it moved to a
top-level `routing` (issue-142). It is NOT being ignored: `routing.authorizedUsers`
decides which GitHub logins may drive your daemon, and quietly falling back to none is
not a decision this config gets to make for you. Run `/the-loop:upgrade-the-loop` to
migrate.
```

**R3 — the migration performs the move, and is idempotent.**

```text
$ the-loop migrate-config --path ./mig/cli-config.yaml --dry-run
migrated the CLI config:
  · webhooks.ghWebhook.routing → routing (top level; it governs the poller too)
  · version '0.3.0' → '0.4.0'

--- ./mig/cli-config.yaml (preview, not written) ---
version: 0.4.0
state: {root: .the-loop}
webhooks:
  ghWebhook: {host: 127.0.0.1, port: 8787, events: [issues, issue_comment]}
polling: {intervalSeconds: 60}
routing:
  enabled: true
  authorizedUsers: [operator]
  spawnOnUnmatched: labeled
  interaction: {mode: work-item}

$ the-loop migrate-config --path ./mig/cli-config.yaml     # written, .bak kept
$ the-loop migrate-config --path ./mig/cli-config.yaml     # second run
config is already current; nothing to migrate
byte-identical: True
```

**R4 — both ingresses behave identically.** 1078 tests pass, including the routing,
poller, control, reactions, announce, interaction and session suites, whose fixtures were
moved to the new key without weakening any assertion. The migrated config above loads and
resolves through the one shared accessor:
`load_routing_config(...)` → `authorizedUsers: ['operator'] | interaction: {'mode':
'work-item'} | enabled: True`. `poll` and `sessions_cmd` no longer expose
`_load_config_defaults` at all, pinned by a test.

**R5 — nothing live still names the old path.** `test_docs_parity` P3/P4 green (every
documented option in the schema, every schema leaf documented) with
`configBase: routing`. The remaining occurrences of `webhooks.ghWebhook.routing` in the
tree are deliberate: the migration's own narrative (its refusal message, the upgrade
command's instructions, the `migrate-config` page) and the historical record
(`docs/decisions/`, merged `docs/specs/`), per R5.4.
