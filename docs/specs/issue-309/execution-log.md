---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#309"
phase: needs-review
status: in-progress
---

# Execution Log: one event bus, many channels, one ledger

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-02 | — | Tier 4 (`human-approves-pr` **plus** a named human security sign-off): a chat message may now advance a gate and create a work item, and the CLI config schema is touched. Brainstorming skipped — the ticket and the owner's comment state the model |
| requirements-definition | 2026-09-02 | | [`requirements.md`](requirements.md) — eight requirements, ten abuse cases. The owner's comment on the ticket is the architecture; the five gaps are consequences of it |
| design | 2026-09-02 | | [`design.md`](design.md) — one catalog, one bus, one ledger with four record shapes, identity in one place, a classify-then-grant pipeline, a renderer; eight decisions in [`decision-103`](../../decisions/decision-103.md) |
| test-planning | 2026-09-02 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, six applicable |
| tasks-breakdown | 2026-09-02 | | [`tasks.md`](tasks.md) — thirteen tasks |
| implementation | 2026-09-02 | | On `claude/the-loop-architecture-h5cfh9` |
| verification | 2026-09-02 | | [`evidence/verification.md`](evidence/verification.md) — the full suite, ruff, pyright, markdownlint and the config validator clean; [`evidence/security-review.md`](evidence/security-review.md) — ten abuse cases, ten closed |
| needs-review | 2026-09-02 | | PR raised; awaiting the owner **and** the named human security sign-off tier 4 requires |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| [#310](https://github.com/MadaraUchiha-314/the-loop/pull/310) | tasks 1–13: the whole work item | open |

## Progress entries

### 2026-09-02 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read the ticket, the owner's architecture comment and the channels, config,
  graph-hook and ingress code at `bf8ab84`; wrote the four artifacts.
- **Checkpoint/tests:** none yet.
- **Next:** task 1 (identity), then the config migration.
- **Blockers:** none.

### 2026-09-02 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–13. `identity.py` and the 0.7.0 migration first (red: the
  schema-parity and migration tests; green after the schema, template and repo config
  moved); then the catalog, the envelope, the bus and the GitHub ledger; the ask, the
  `notify` hook and both ingresses moved onto the bus; the Slack channel rewritten
  around grants, Block Kit and the kickoff read; the docs and the capability doc.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 8
  (identity), 37 (bus/ledger/renderer/grants), 8 scenarios (bus integration), 5
  (router publisher), 2 (graphlink attribution), 1 (poller publisher), 7 (migration);
  the existing channel tests updated to the new config shape and record shapes.
- **Self-review:** three passes over the diff. Findings fixed in place: the ingress
  publishers must skip enveloped records themselves (not only the helper, because a
  daemon may inject a raw publisher); the pipeline's log field for the classified type
  must not be called `event_type` (it collides with the event-log fake's positional
  name); the `routing` block must be type-guarded before the Slack config reads it.
- **Next:** the owner's review and the tier-4 security sign-off.
- **Blockers:** none.

## Verification results

> Only when this work item declared `test-planning` away. It did not: results live in
> [`testing-plan.md`](testing-plan.md).

| What was verified | Command | Outcome | Evidence |
|-------------------|---------|---------|----------|
| — | — | — | see `testing-plan.md` |

## Design critic review

> Not selected for this work item.

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| | | | | |

## Review cycles

| Cycle | Type (self/critic/security) | Reviewer | Outcome | Link |
|-------|-----------------------------|----------|---------|------|
| | | | | |

## Security review (gate)

- **Mechanism:** the-loop checklist against the abuse cases (`security.review.mechanism: auto`)
- **Outcome:** pass — ten abuse cases, ten closed by a mechanism in the diff and a
  negative test ([`evidence/security-review.md`](evidence/security-review.md))
- **Human sign-off:** required (tier 4 ≥ `humanSignOffMinTier`) — requested in the PR

## Final validation evidence

| Requirement | Proved by |
|-------------|-----------|
| R1 one catalog, one bus | `test_bus.py` (catalog views, publish ordering, source skip, best-effort); the docs↔catalog pin in `test_channels.py` |
| R2 subscribe / publish grants | `test_publish_grants_default_to_reply_and_ignore_what_the_catalog_forbids`, `test_a_control_keyword_without_the_grant_is_dropped_not_delivered`, `Scenario: Without a grant a reply is session input and nothing more` |
| R3 the ledger and its record shapes | the four record-shape tests in `test_bus.py`; `Scenario: An asked question is one ledger comment and one Slack post` |
| R4 rendering | `test_render_blocks_*`, `test_approve_buttons_only_when_interactive`; the button scenario |
| R5 identity in one place | `test_identity.py`; `test_slack_member_ids_come_from_routing_authorized_users`; `test_identity_is_declared_once_and_read_per_channel` |
| R6 the five gaps | the comment-mirror, gate-grant, control-grant, kickoff and complete-node scenarios in `test_bus_integration.py`; `test_the_router_publishes_*`, `test_the_poller_publishes_*` |
| R7 config and migration | `test_migrations.py` (0.7.0 section), `test_configschema.py`, `test_config_schema_parity.py`, `make validate` |
| R8 observability | `test_a_failing_ledger_or_channel_is_a_result_never_an_exception` (ids only), the event-type catalog pins in `test_eventlog.py` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`channels.md`](../../capabilities/channels.md) | Rewritten around the bus, the ledger, identity, grants, rendering and the kickoff; the index row reworded | issue-309 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/channels-options.md` | Rewritten: `ledger`, `subscribe` (with the full catalog table), `publish` (the grant table), `maxChars`, `kickoff.*`, who may speak |
| `docs/config/cli/routing-options.md` | `authorizedUsers` as person entries, with `[].github`, `[].slack`, `[].name` |
| `docs/config/cli/index.md` | current config version; the channels row |
| `docs/cli/commands/channels.md` | status output, the kickoff read, button presses, the classify-then-grant pipeline |
| `docs/cli/commands/migrate-config.md` | the 0.7.0 migration |
| `docs/cli/state.md` | the `channel:<id>` cursor and the created-issue bindings |
| `skills/the-loop/reference/collaboration.md` | the channels paragraph, rewritten for the bus |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml`, `.the-loop/harness-config.yaml` | the new keys, commented; the `work-item-complete` note |
| `README.md` | one line: the channel is a peer on the bus |
| `docs/decisions/decision-103.md` (+ index) | the eight decisions |
