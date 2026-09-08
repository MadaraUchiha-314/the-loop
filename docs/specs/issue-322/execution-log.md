---
type: execution-log
workItem: "github:MadaraUchiha-314/the-loop#322"
phase: needs-review
status: in-progress
---

# Execution Log: instances scoped to their own work items

> Append-only log of progress for the user's visibility.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| phase-selection | 2026-09-08 | — | Tier 4 (`human-approves-pr`, and a named human security sign-off at `humanSignOffMinTier: 4`): a seam on the dispatch path — the one place an event becomes a session — plus an additive block in `cli-config.schema.json` (an `autonomy.sensitivePaths` entry). Brainstorming skipped: the ticket's bullets are the requirements and its three questions are answered in `requirements.md` § Open questions. No authorized `the-loop execute` reaches this cloud session, so the selection is recorded here and every phase is walked |
| requirements-definition | 2026-09-08 | | [`requirements.md`](requirements.md) — five requirements, six abuse cases |
| design | 2026-09-08 | | [`design.md`](design.md) — one block, one seam, one token, one route; [`decision-110`](../../decisions/decision-110.md) |
| test-planning | 2026-09-08 | | [`testing-plan.md`](testing-plan.md) — thirteen rows, seven applicable |
| tasks-breakdown | 2026-09-08 | | [`tasks.md`](tasks.md) — seven tasks |
| implementation | 2026-09-08 | | On `claude/github-issue-322-2yely4` |
| verification | 2026-09-08 | | [`evidence/verification.md`](evidence/verification.md) — rows T1, T2, T3, T8, T10, T12; [`evidence/security-review.md`](evidence/security-review.md) — six abuse cases, six closed |
| needs-review | 2026-09-08 | | PR raised; awaiting the owner (tier 4: `human-approves-pr` + the named security sign-off) |
| complete | | | |

## Pull requests

| PR | Scope / tasks | Status |
|----|---------------|--------|
| __PR__ | tasks 1–7: the whole work item | open |

## Progress entries

### 2026-09-08 — implemented, verified, ready for review

- **Phase:** implementation → verification → needs-review
- **Did:** tasks 1–7, red first each. `the_loop.instance` (`InstanceConfig`,
  `parse_address`, `decide`, the outcome constants); `cli_config.apply_instance` (the
  `_ghBinary`-style fan-out, applied only when a block is declared) and
  `RoutingConfig.instance`; the seam in `Dispatcher.handle` with `_manages` and
  `_refuse_scope`, the four outcomes added to `SETTLED_OUTCOMES` and to the
  `poll.comment_settled` catalogue entry; `ControlRecord.instance` on every record the
  dispatcher and `core.sessions` write; `command_comment(address=)` on the CLI's posted
  keyword, `announcement_body(instance=)`, `TmuxRunner.instance` with the one-time
  `tmux -V` probe and the `-e THE_LOOP_INSTANCE=<name>` argv; `core.sessions` refusing a
  `start` on a `locked` instance before anything is recorded or posted;
  `core/instance.py::describe_instance` behind `GET /api/v1/instance`, the `get_instance`
  MCP tool, `loop.instance()` and the `status` line; the schema block (authored + packaged,
  byte-identical, purely additive), the template and this repository's config; the docs.
- **Checkpoint/tests:** `make check` — see `evidence/verification.md`. New tests: 60 unit
  (`test_instance.py`), 14 two-dispatcher scenarios (`test_instance_integration.py`), 1
  status-line test. Existing assertions changed: one — the settled-vocabulary test in
  `test_routing.py`, which by its own docstring is where a new settlement is added.
- **Self-review:** three passes over the diff. Pass one found the fan-out stamping
  `_instance` onto every routing dict, which broke three equality tests on configs with no
  block — made conditional. Pass two verified three design claims against the code: only
  comment and review bodies reach `parse_address` (`event_body` returns `None` for an
  issue's own body, so an issue body cannot address); the receiver's and the poller's
  reload paths build from `load_cli_config`, so the block is hot-reloaded; the dashboard's
  config writer reads raw YAML, so the private key never reaches the file. Pass three
  found nothing new.
- **Next:** the owner's review and the tier-4 security sign-off.
- **Blockers:** none.

### 2026-09-08 — spec chain drafted

- **Phase:** requirements-definition → tasks-breakdown
- **Did:** read `webhook/dispatcher.py` (`handle`, `_on_unmatched`, `_apply_control`,
  `_spawn_for`, `reload`), `control.py`, `cli_config.py`, `state.py`, `runner.py`,
  `announce.py`, `core/sessions.py`, `core/lifecycle.py`, `api/routes.py` and the
  two daemons at `10a55b3`; found that every instance judges every labelled event
  identically and that the one seam where an event becomes a session is `handle`; found
  the `_ghBinary` fan-out precedent for a top-level block reaching `RoutingConfig`; found
  the standing-session name grammar and the collaborator `@login` argument as the
  precedents for a validated token. Wrote the four artifacts and the decision.
- **Checkpoint/tests:** baseline — `test_control.py` green (57 passed).
- **Next:** task 1 (the block), red first.
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
| 1 | self | the-loop (this session) | new findings — the unconditional `_instance` fan-out broke three equality tests on block-less configs: made conditional; the settled vocabulary needed the four outcomes in its test and catalogue entry: added | this log |
| 2 | self | the-loop (this session) | zero new findings — three design claims verified against the code (issue bodies never parsed; both reload paths carry the block; the config writer never sees the private key) | this log |
| 3 | self | the-loop (this session) | zero (converged) | this log |
| — | critic | — | unavailable — `reviews.critics` is empty in this repository's config; does not count toward `criticReviewCount` | — |
| 4 | security | the-loop checklist | pass on the autonomous review; human sign-off pending (tier 4) | [`evidence/security-review.md`](evidence/security-review.md) |

## Security review (gate)

- **Mechanism:** the-loop checklist (`security.review.mechanism: auto`; no security-review
  skill is invocable from this session's plugin set)
- **Outcome:** pass — [`evidence/security-review.md`](evidence/security-review.md), six abuse cases closed
- **Human sign-off:** **required and pending** (tier 4 ≥ `humanSignOffMinTier: 4`) — the
  owner's approval of the PR is the named sign-off; requested in the PR briefing

## Final validation evidence

| Requirement | Proof |
|-------------|-------|
| R1.1 the block's shape | `test_the_block_reads_name_mode_and_declared_refs`; `make validate` against the authored schema |
| R1.2 unset = 13.3.1, additive | `test_the_block_unset_is_an_unnamed_open_instance`, `test_a_bare_routing_mapping_is_an_unnamed_open_instance`, `Scenario: An open, unnamed instance is 13.3.1`; `test_control_integration.py` + `test_graphlink_integration.py` unchanged and green; `CURRENT_CONFIG_VERSION` unchanged |
| R1.3 in `cli-config.yaml`, hot-reloaded | `test_the_block_reaches_routing_config_through_the_loaded_config`; both daemons' reload paths build from `load_cli_config` (verified in self-review pass two) |
| R1.4, R1.5 narrowing | `test_the_block_refuses_a_name_outside_the_grammar`, `test_an_unknown_mode_resolves_to_locked`, `test_the_block_addressed_without_a_name_is_locked`, `test_the_block_skips_a_bad_declaration_by_index_and_keeps_the_rest` |
| R2.1 managed = as before, every mode | `Scenario: A managed work item is in scope whatever the mode` (×3), `Scenario: A stopped work item is still this instance's`; `decide` rows 3 |
| R2.2 open = 13.3.1 | `decide` row 4; the open-unnamed scenario |
| R2.3 addressed | `Scenario: An addressed start reaches only the instance it names`, `Scenario: An unaddressed start on two addressed instances reaches neither` |
| R2.4 locked | `Scenario: A locked instance takes only what its config declares`; `test_an_address_does_not_unlock_a_locked_instance` |
| R2.5 command → `control.rejected` | the addressed and unaddressed scenarios assert `control.rejected` with the reason and `delivery_outcome == control-rejected` |
| R2.6 no mark | `Scenario: A non-owner leaves nothing behind` (no `portable/`, no session, no spawn, no delivery, one `dispatch.dropped`) |
| R2.7 `sessions start` | `Scenario: sessions start on a locked instance`, `Scenario: sessions start on an addressed instance` |
| R3.1, R3.4 the token | `test_the_token_is_read_as_a_whole_word_with_a_case_insensitive_prefix` (six bodies), `test_a_malformed_token_is_not_an_address_and_reaches_no_record` (eleven) |
| R3.2 address is authoritative | `Scenario: An explicit address wins over the managed set`; `decide` row 2 |
| R3.3 ambiguity | `test_two_different_addresses_are_ambiguous`, `Scenario: A comment naming two instances is ambiguous` |
| R3.5 both ingresses | the seam reads `event_body`, the one body accessor both ingresses feed (`parse_control_command` reads the same); the poller's `RoutedEvent` shape is what the scenarios use (`labeled=False`) |
| R4.1 `control.instance` | `test_the_control_record_carries_the_instance_and_reads_old_records_as_unnamed`; every scenario that spawns asserts the record names the instance |
| R4.2 the posted keyword | `test_the_posted_keyword_carries_the_address`; the addressed `sessions start` scenario |
| R4.3 the announcement | `test_the_announcement_names_the_instance` |
| R4.4 the route | `test_describe_instance_merges_declared_session_and_control_sources`, `test_describe_instance_for_an_unset_block_is_unnamed_open_and_empty`; `test_api_contract_parity.py`; `test_mcp_integration.py`; `test_sdk_docs_parity.py` |
| R4.5 `status` | `test_status_prints_the_instance_line` |
| R4.6 `THE_LOOP_INSTANCE` | `test_a_named_instance_spawns_with_the_environment_variable`, `test_an_unnamed_instance_spawns_with_the_argv_it_used_before`, `test_an_old_tmux_gets_no_environment_flag_and_one_warning` |
| R5.1–R5.3 docs | `test_docs_parity.py` (P3, P4, P5 over `instance-options.md`); `make validate` (template + this repo's config); markdownlint over 977 files |
| A1–A6 | `evidence/security-review.md` |

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`instances.md`](../../capabilities/instances.md) | **minted** — the block, the managed set, the modes, the address token, the refusal, the record, the surface, what it does not do, and the seams left for the manager and the ticket-managed instance | issue-322 row |
| [`capabilities.md`](../../capabilities/capabilities.md) | the index row for `instances` | — |
| [`webhook-triggers.md`](../../capabilities/webhook-triggers.md) | a current-behaviour bullet: the scope decision runs before anything else acts on an event, and can only refuse | issue-322 row |
| [`cli.md`](../../capabilities/cli.md) | a current-behaviour bullet: the `status` line, the locked refusal of `sessions start`, the address on posted keywords | issue-322 row |
| [`control-plane.md`](../../capabilities/control-plane.md) | a current-behaviour bullet: `GET /api/v1/instance`, `get_instance`, `loop.instance()` — the manager seam | issue-322 row |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/instance-options.md` | **new** — `name`, `scope.mode`, `scope.workItems` with type, default, grammar and the three rules (parity-tested) |
| `docs/config/cli/index.md` | the options-by-area row |
| `docs/cli/instances.md` | **new** guide — the shape, the three modes, addressing, pinning and locking, what the record says, what the design does not do |
| `docs/cli/index.md` | a "you want to…" row pointing at the guide |
| `docs/cli/state.md` | `control.instance` in the field table and the example record |
| `docs/cli/commands/status.md` | the instance line, first in the example, and its JSON form |
| `docs/.vitepress/config.mts` | sidebar entries for the guide and the options page |
| `docs/api-specs/openapi/the-loop.v1.yaml` | `GET /api/v1/instance` (`getInstance`) |
| `docs/sdk/reference.md` | the `instance()` row |
| `skills/the-loop/reference/automation.md` | a bullet beside the control keywords: the block, the modes, the address token |
| `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml` | the `instance` block at its defaults, commented |
| `.the-loop/cli-config.schema.json`, `cli/the_loop/schemas/cli-config.schema.json` | the `instance` block (byte-identical copies; purely additive) |
| `docs/decisions/decision-110.md`, `decisions.md` | the decision and its index row |
| `README.md`, `skills/the-loop/SKILL.md` | unchanged — neither enumerates the daemon's configuration blocks; the operating model itself did not change (an instance is still armed by a label and started by an authorized keyword) |
