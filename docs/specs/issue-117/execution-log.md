---
type: execution-log
workItem: issue-117
phase: tasks-breakdown
status: in-progress
---

# Execution Log: the CLI documented as a product, and the docs restructured around it

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-07-30 | | Gap measured from the tree, not assumed — see the first progress entry |
| design | 2026-07-30 | | |
| tasks-breakdown | 2026-07-30 | | |
| implementation | | | |
| needs-review | | | |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| _pending_ | spec + T1–T12 | — |

## Progress entries

### 2026-07-30 — spec written (requirements → design → tasks)

- **Phase:** not-started → requirements-definition → design → tasks-breakdown
- **Did:** Measured the gap before specifying it, rather than restating the ticket:

  | Claim | How it was established |
  |---|---|
  | 679-line single page | `wc -l cli/README.md`; `docs/scripts/sync-content.mts` copies it verbatim to `docs/cli.md`; `config.mts` exposes it as one nav entry `{ text: "CLI", link: "/cli" }` |
  | 3 of 9 commands undocumented | `grep 'name = ' cli/the_loop/commands/*.py` → 9 registered (`gh-webhook`, `sessions`, `poll`, `events`, `scenarios`, `critic`, `check`, `graph`, `migrate-config`); `cli/README.md` has `###` sections for 6 |
  | 4 config blocks undocumented | Walked `.the-loop/cli-config.schema.json` → 80 leaves; `integrations.*`, `routing.workspace.*`, `routing.graph.*`, `polling.maxRetries` appear in none of the README's tables |
  | `ghBinary` documented but removed | 5 occurrences in `cli/README.md`, `grep -c ghBinary .the-loop/cli-config.schema.json` → **0**. `cli_config.apply_integrations()` fans `integrations.github.cli.binary` out to `control`/`reactions`/`announce` under a private key; `migrations.py` makes the old key a hard refusal (`ConfigTooOld`) |

  The finding that shaped the design: **the flat shape is why the content is wrong.** A
  single file has nowhere to put a new command, so issue-109's three commands got no
  entry while a key it deleted stayed documented. A structure with a slot per command and
  a slot per option turns that from "someone forgot" into a failing test — hence R4.5 and
  the parity test at T1.

  Wrote `requirements.md` (6 requirements, 26 EARS criteria + threat-model-lite),
  `design.md` (23 new pages, the `configBase` per-option contract, the four parity
  assertions, the exhaustive `cli/README.md` → new-home mapping), `tasks.md` (12-task DAG,
  red-first).
- **Checkpoint/tests:** none yet — no code or pages written.
- **Next:** T1 — `cli/tests/test_docs_parity.py`, red first.
- **Blockers:** none. Two open questions recorded on the ticket with assumptions taken
  (retiring `/reference/configuration`; treating `ghBinary` as doc drift rather than a
  lost migration path). Neither blocks implementation.

## Risk tier

**3** — documentation, navigation and one build-script line; no runtime behaviour change,
no schema change, no touched `sensitivePaths`. `autonomy.tiers."3": human-approves-pr`.
Below `security.review.humanSignOffMinTier` (4), so no named human security sign-off is
required; the security-review gate itself still runs at T11.

## Reviews

| Round | Kind | Reviewer | Findings | Where |
|-------|------|----------|----------|-------|
| | | | | |

## Requirement → evidence

| Requirement | Evidence |
|-------------|----------|
| | _filled at T12_ |
