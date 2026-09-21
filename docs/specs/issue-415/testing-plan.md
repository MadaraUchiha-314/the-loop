---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#415"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the `/the-loop:init` onboarding a person can finish

> Derived from [requirements.md](requirements.md) and [design.md](design.md), before
> `tasks.md`. Authored at `test-planning`, completed at `verification`.

## What is testable here, and what is not

This work item ships **schema metadata, agent instructions and documentation**. That
split decides the whole matrix, so state it before the table:

- The **metadata** is mechanically checkable against the schema it annotates, and that is
  where every failure mode with teeth lives — a renamed key, a forgotten group, a profile
  path that resolves to nothing, a rung reaching a key it must never reach. It gets a
  test module.
- The **instructions** (`commands/init.md`, `reference/onboarding.md`) are executed by an
  agent in a conversation. A test that asserts prose contains a phrase is a test that
  fails on a rewording and passes on a lie; it buys nothing. These are verified by a
  **manual exploratory run** of `/the-loop:init --dry-run` against a scratch repository,
  with the transcript committed as evidence.
- The **existing suites** that this change can break (schema parity, the keyword guard,
  docs parity) are run in full, because they are the ones that turn "I copied the schema
  over" from a promise into a fact.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `x-onboarding` in `cli-config.schema.json` is internally consistent and consistent with the schema it annotates: group coverage, key existence, profile path resolution, ask-level vocabulary parity with the harness schema (A1–A3, A6–A7 of design §Testing strategy) | `uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py` |
| T2 | Integration (scenario) | n/a — nothing new crosses a process, a socket or a subprocess boundary. The new artifacts are read by an agent, not by a running daemon; the CLI surface the walkthrough calls (`channels status --probe`, `doctor slack`) is unchanged by this work item and already covered by `test_channels*.py` and `test_doctor_slack.py`. | | |
| T3 | Contract (OpenAPI / GraphQL) | n/a — no API surface is touched. | | |
| T4 | End-to-end | n/a — an end-to-end run of this feature *is* T11: a human-driven conversation in a harness. Automating it would mean scripting an agent's dialogue, which tests the script. | | |
| T5 | UI / visual | n/a — no rendered surface (design §UI/UX design). | | |
| T6 | Snapshot | n/a — the schema is reviewed as a diff; a snapshot of it would be the same bytes twice. | | |
| T7 | Performance / load | n/a — no runtime path changes; init's cost is a conversation. | | |
| T8 | Security / abuse case | yes | **The autonomy ladder cannot reach a gate** (A5) — every profile value's top-level block is in the allowed set, asserted per rung. Plus a static check that no new instruction reads a credential's *value* rather than its presence. | `uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py -k profile_values` and the grep in T8's activity line |
| T9 | Accessibility | n/a — no rendered surface. | | |
| T10 | Migration / upgrade | yes | An existing `cli-config.yaml` and the shipped template still validate against the edited schema, and the packaged copy is byte-identical to the authored one | `uv run python scripts/validate_config.py` and `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py` |
| T11 | Manual exploratory | yes | The walkthrough is followable: a `--dry-run` init reaches every new step, the profile question renders, the Slack explanation is short enough to read, and the credential preflight names variables without values | A scratch repository; transcript committed |
| T12 | Documentation parity | yes | The new root-level `x-onboarding` adds no undocumented schema leaf, and the docs site's own parity assertions still hold | `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.2 | `Scenario: the CLI config schema declares an onboarding block` |
| T1 | R1.2, R7.2 | `Scenario: both schemas speak one ask-level vocabulary` |
| T1 | R1.3 | `Scenario: every onboarding group names keys the schema defines` |
| T1 | R1.3 | `Scenario: every configurable block belongs to exactly one group` |
| T1 | R2.1, R2.4 | `Scenario: every profile value names a key the schema defines` |
| T1 | R2.4 | `Scenario: every profile value is legal for the key it sets` |
| T1 | R2.5 | `Scenario: the first rung is the shipped defaults` |
| T1 | R2.1, R2.2, R2.6 | `Scenario: every rung explains itself and what still needs a human` |
| T8 | **R3.1, R3.2** | `Scenario: no autonomy profile reaches a key that guards a human gate` |
| T8 | R6.2, abuse case 2 | Static check: no new instruction step reads a credential value |
| T10 | NFR — packaged parity | `test_config_schema_parity.py` byte equality |
| T10 | NFR — no new keyword | `test_configschema.py::test_the_schemas_use_no_keyword_the_validator_ignores` |
| T12 | NFR — schema/doc parity | `test_docs_parity.py` P3/P4 |
| T11 | R4, R5, R6, R7 | A `--dry-run` walkthrough on a scratch repository |

## Verification environment

- **Repositories:** this repo only. T11 additionally uses a throwaway git repository
  created under the session's scratch directory — never a real project.
- **Services / containers:** none. No daemon is started; no Slack workspace is contacted.
  T11 runs `--dry-run`, which by contract writes nothing and interacts with nothing.
- **Fixtures & data:** none beyond the repository's own schemas and templates.
- **Credentials:** **none are required, and none are used.** T11 deliberately runs with
  the Slack and webhook variables **unset**, because the behaviour under test is what the
  preflight reports when a credential is missing. Referenced by name only:
  `THE_LOOP_SLACK_BOT_TOKEN`, `THE_LOOP_SLACK_APP_TOKEN`,
  `THE_LOOP_GH_WEBHOOK_SECRET`, `GH_TOKEN` / `GITHUB_TOKEN`.
- **Bring-up:** `uv sync` · **Tear-down:** delete the scratch repository.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate on the ticket.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T8 | new test module output, with counts and the Gherkin scenario titles | `verification.md` |
| T10, T12 | `validate_config.py`, parity and keyword-guard output | `verification.md` |
| T1–T12 | the full `make check` run (lint, format, typecheck, validate, test) | `verification.md` |
| T11 | the `--dry-run` walkthrough transcript, credentials unset, redacted | `verification.md` |
| R3, R6 | the security review against the abuse cases | `security-review.md` |
| — | self-review against the requirements | `self-review.md` |
| — | capability-doc and guide updates | `documentation.md` |
| — | the pull request opened for this work item | `pull-requests.md` |

**Redaction.** The T11 transcript is produced with every credential variable unset, so
there is nothing to redact by construction; it is still read before committing, and any
absolute path naming the operator's home directory is elided.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py`
- [x] T8 — `uv run --project cli python -m pytest -q cli/tests/test_onboarding_schema.py -k profile`
- [x] T8 — static check: `grep -nE '\$\{?(THE_LOOP_SLACK|THE_LOOP_GH|GH_TOKEN|GITHUB_TOKEN)' commands/init.md skills/the-loop/reference/onboarding.md` returns no line that expands a value
- [x] T10 — `uv run python scripts/validate_config.py`
- [x] T10 — `uv run --project cli python -m pytest -q cli/tests/test_config_schema_parity.py cli/tests/test_configschema.py`
- [x] T12 — `uv run --project cli python -m pytest -q cli/tests/test_docs_parity.py`
- [x] All — `make check`
- [x] T11 — walk `/the-loop:init --dry-run` against a scratch repository with credentials unset; capture the transcript

## Verification results

Every planned activity ran. Raw output: [`evidence/verification.md`](evidence/verification.md).

`uv` is invoked as `python3 -m uv` throughout: the container shipped 0.8.17, below this
repo's `required-version` pin (`>=0.12,<0.13`), and could not self-update behind the
proxy; `pip install uv` supplied 0.12.17. The commands are otherwise exactly as planned.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest -q cli/tests/test_onboarding_schema.py` | **pass** — 7 failed before the schema block landed, 7 passed after | [verification.md](evidence/verification.md) § T1 / T8 |
| T8 | `pytest -q cli/tests/test_onboarding_schema.py -k profile` | **pass** — A4–A7 including the confinement assertion | [verification.md](evidence/verification.md) § T1 / T8 |
| T8 | the credential-value grep | **pass** — 3 prose mentions of variable names, 0 shell expansions | [verification.md](evidence/verification.md) § T8 |
| T10 | `scripts/validate_config.py` | **pass** — all 6 configs valid | [verification.md](evidence/verification.md) § T10 |
| T10 | `pytest -q test_config_schema_parity.py test_configschema.py` | **pass** — byte parity held; the keyword guard passes with `x-onboarding` declared documentation-only | [verification.md](evidence/verification.md) § T10 |
| T12 | `pytest -q cli/tests/test_docs_parity.py` | **pass** — no new schema leaf, P3/P4 unaffected | [verification.md](evidence/verification.md) § T12 |
| All | `make check` (lint · format · typecheck · validate · test) | **pass**, with 4 pre-existing failures — see below | [verification.md](evidence/verification.md) § The full suite |
| T11 | the `--dry-run` walkthrough, credentials unset | **pass** — 18/18 blocks covered, the ladder renders, the preflight names variables without values, the scratch repo is untouched | [verification.md](evidence/verification.md) § T11 |

**The 4 failures in `make check` are not this work item's.** All four are in
`cli/tests/test_instance.py`, concern the argv a tmux spawn is built with, and reproduce
identically with the entire change stashed. The container's tmux predates
`TMUX_ENV_MIN_VERSION` (3.2), so the spawn omits `-e` by design. Recorded rather than
fixed: it is outside this work item's scope.

**Not executed:** a **live Slack probe** — no workspace, app or tokens exist in this
environment, and manufacturing them would prove nothing about the walkthrough. The
CLI-absent path *was* exercised (T11, reported as *unverified*), and the probe commands
themselves are unchanged here and covered by `test_channels*.py` / `test_doctor_slack.py`.
T4 stays `n/a` for the reason the matrix gives.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
