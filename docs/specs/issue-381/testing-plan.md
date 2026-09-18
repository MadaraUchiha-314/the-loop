---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#381"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a work item is armed by a set of labels, all of which must be present

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** Nothing here needs credentials or the network:
> `gh` is the `FakeRun` seam every poller test uses, the receiver is the in-process
> server of `test_webhook_routing_integration.py`, and the migration is pure.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `event_carries_labels`: every label required; the added label counts on a `labeled` action; a subset, the wrong added label and an empty list are `False` (R1.2–R1.5, A1–A3) | `cli/tests/test_routing.py` |
| T2 | Unit | yes | `normalize_labels` and `RoutingConfig.from_mapping`: default list, a list read in order without duplicates or empties, a string read as one label (R1.1) | `cli/tests/test_routing.py`, `cli/tests/test_control.py` or the dispatcher unit file that owns `RoutingConfig` |
| T3 | Unit | yes | `Router.route` flags `labeled` only when every label is present (R1.2, R1.3) | `cli/tests/test_routing.py` |
| T4 | Unit | yes | `GhClient` passes one `--label` per label on both listings (R2.1) | `cli/tests/test_poller.py` |
| T5 | Unit | yes | `GitHubPollProvider` drops a listed item missing one label, keeps one carrying all, and `from_source` reads `labels` / falls back to the routing list (R2.1–R2.3) | `cli/tests/test_poller.py` |
| T6 | Unit | yes | the migration both ways: detection by key, refusal naming key/replacement/command, the moves (wrap, empty removed, both-present note), version `0.10.0`, idempotence (R3.1–R3.4, A4) | `cli/tests/test_migrations.py` |
| T7 | Integration (scenario) | yes | receiver: an item carrying every label spawns; one carrying only some does not; adding the last missing label spawns (R1.2–R1.4) | `cli/tests/test_webhook_routing_integration.py` |
| T8 | Integration (scenario) | yes | poller: a listing that returns an item missing one label never tracks or spawns it (R2.1) | `cli/tests/test_poller_integration.py` |
| T9 | Contract / parity | yes | docs ↔ schema parity, packaged schema byte-identical, this repo's configs validate (R4.1) | `cli/tests/test_docs_parity.py`, `cli/tests/test_config_schema_parity.py`, `scripts/validate_config.py` |
| T10 | Regression | yes | every existing routing, poller, control, reactions, tmux, instance, channels and eventlog suite passes with the renamed constructor arguments | `pytest -q cli` |
| T11 | Security / abuse case | yes | A1–A4 as named in `design.md` § Security design | rows T1, T5, T6, T7 |
| T12 | End-to-end / manual | n/a — a real `gh` against a real repository adds nothing the fake seam does not prove, and the provider filters the listing regardless of `gh`'s semantics | | |
| T13 | Performance | n/a — one set comparison per listed item | | |
| T14 | UI / accessibility / snapshot | n/a — no surface | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2–R1.5 | `test_event_carries_labels_requires_every_label`, `test_event_carries_labels_counts_the_label_being_added`, `test_an_empty_label_list_arms_nothing` |
| T3 | R1.2, R1.3 | `test_router_flags_labeled_only_when_every_label_is_present` |
| T4 | R2.1 | `test_gh_listings_pass_one_label_flag_per_label` |
| T5 | R2.1–R2.3 | `test_provider_drops_a_listed_item_missing_one_label`, `test_provider_from_source_reads_labels_and_falls_back_to_routing` |
| T6 | R3 | `test_an_un_migrated_label_key_is_refused`, `test_the_label_keys_become_lists`, `test_the_label_migration_is_idempotent`, `test_the_current_config_version_is_0_10_0` |
| T7 | R1.2–R1.4 | `Scenario: an item carrying only some of the labels is not armed`; `Scenario: adding the last missing label spawns a session` |
| T8 | R2.1 | `Scenario: the poller drops a listed item missing one label` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none.
- **Fixtures & data:** the existing `FakeRun` / `FakeTmux` / in-process receiver fixtures.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T8 | red→green tail and the green run | `final-validation.md` |
| T9, T10 | the gate commands and their tail | `final-validation.md` |
| T11 | abuse-case table | `security-review.md` |

## Verification activities

- [x] T1–T3 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py`
- [x] T4, T5 — `uv run --project cli python -m pytest -q cli/tests/test_poller.py -k label`
- [x] T6 — `uv run --project cli python -m pytest -q cli/tests/test_migrations.py`
- [x] T7 — `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py -k label`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_poller_integration.py -k label`
- [x] T9 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py cli/tests/test_config_schema_parity.py && uv run python scripts/validate_config.py`
- [x] T10 — `make check`

## Verification results

See `evidence/final-validation.md` for the verbatim output.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1–T3 | `pytest cli/tests/test_routing.py` | pass | `evidence/final-validation.md` |
| T4, T5 | `pytest cli/tests/test_poller.py -k label` | pass | `evidence/final-validation.md` |
| T6 | `pytest cli/tests/test_migrations.py` | pass | `evidence/final-validation.md` |
| T7 | `pytest cli/tests/test_webhook_routing_integration.py -k label` | pass | `evidence/final-validation.md` |
| T8 | `pytest cli/tests/test_poller_integration.py -k label` | pass | `evidence/final-validation.md` |
| T9 | parity suites + `scripts/validate_config.py` | pass | `evidence/final-validation.md` |
| T10 | `make check` | pass | `evidence/final-validation.md` |

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed.
