---
type: testing-plan
phase: test-planning
workItem: issue-220
status: draft                # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: the-loop's JSON schemas ship with the plugin, not with your repo

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at the `test-planning` node and **completed at the `verification` node**.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials of any kind are involved in this work item.

## What can be tested, and what honestly cannot

Half of this work item is **instructions an agent follows** — `commands/init.md` and
`commands/upgrade-the-loop.md` are markdown, executed by a model, not by a runner. No test
in this repository can assert that `/the-loop:init` did not copy a file, because nothing
here runs `/the-loop:init`. Saying so plainly is the point of this section: R1, R3 and R5
are verified by **review against their acceptance criteria**, recorded as evidence, and
the rows below mark that explicitly instead of borrowing credibility from the tests that
do run.

What *is* mechanically testable is the part that decides what the agent does: the manifest
declarations it reads, and the files it writes. Those carry T1 and T2.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `harness_config.scaffold()` keeps the `$schema` modeline on line 1 when it prepends its adoption header (R4.2 on the issue-193 path); the packaged default and the shipped template stay byte-identical | `uv run pytest cli/tests/test_harness_config.py` |
| T2 | Integration (repository parity) | yes | the manifest declares `schemasDir`, it resolves and holds the three schemas, `meta` names no schema, all three are `deprecated`, and every scaffolded config's first line is a modeline naming a schema that exists (R2, R3.1, R4.1) | `uv run pytest cli/tests/test_manifest_schemas.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — no API surface changes; the control-plane contract under `docs/api-specs/` is untouched | | |
| T4 | End-to-end | n/a — the e2e suite (`cli/tests/test_pdlc_e2e/`, issue-217) drives the *process graph*; `/init` and `/upgrade` are not graph nodes and have no runtime to drive | | |
| T5 | UI / visual | n/a — no user-facing surface (design.md §UI/UX) | | |
| T6 | Snapshot | n/a — no rendered output; the one byte-for-byte comparison this work item cares about (template ↔ packaged default) is an existing assertion in T1 | | |
| T7 | Performance / load | n/a — removing files from a scaffold has no performance dimension | | |
| T8 | Security / abuse case | yes | the four abuse cases in `design.md` §Security design: deletion is name-driven and closed, a drifted copy is reported not deleted, the loop needs no network, a tampered modeline reaches nothing | review against `requirements.md` §Security considerations + T2's assertion that the three deprecated paths are exact literals |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes, **by review** | an existing project's copies are shed by `/upgrade` and its config migrations still work with no project-local schema: `upgrade-the-loop.md` steps 3 and 4 read against R3.1–R3.5 | review + `uv run python scripts/validate_config.py` (this repository is the migration's own target: it carries all three configs) |
| T11 | Manual exploratory | yes | read `commands/init.md` end to end as the agent would, confirming no step still writes a schema and every schema reference names `${CLAUDE_PLUGIN_ROOT}` (R1, R2.4) | `grep` + read-through, recorded in evidence |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R4.2, R4.3 | `Scenario: adoption keeps the schema modeline on the first line` |
| T1 | NFR3 | existing: the packaged default is the shipped template (byte parity) |
| T2 | R2.1, R2.2 | `Scenario: the manifest's schemasDir resolves to the shipped schemas` |
| T2 | R2.3 | `Scenario: the manifest claims no schema as a project file` |
| T2 | R3.1 | `Scenario: every retired schema copy is listed as deprecated` |
| T2 | R4.1, R4.2, R2.4 | `Scenario: every scaffolded config points at a schema that exists` |
| T8 | abuse 1–4 | negative reading: the deprecated list is three exact literals; no code path reads the modeline |
| T10 | R3.1–R3.5 | review of `upgrade-the-loop.md` §3–4 against the criteria; this repo's own configs re-validated |
| T11 | R1.1–R1.4, R2.4, R5.1 | read-through of `init.md`, the guide, and the config reference |

## Verification environment

- **Repositories:** this repository only. No consuming repository is checked out: the
  criteria that would need one (R1.1's "init creates no schema") are the ones this plan
  marks as review-verified rather than executed.
- **Services / containers:** none.
- **Fixtures & data:** none beyond `tmp_path` in the unit test.
- **Credentials:** none. This work item touches no secret, token or environment variable.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2 | test output (counts, duration), plus the full-suite run proving no regression | `verification.md` |
| T8, T10, T11 | the review record: each criterion, where it is met in the diff, and the quality-gate output (`lint`, `markdownlint`, `pyright`, `validate_config.py`) | `verification.md` |

Nothing captured here can contain a secret: the commands run a test suite and linters over
a public repository. Standard redaction still applies to any path that would reveal a
local home directory.

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_harness_config.py`
- [x] T2 — `uv run pytest cli/tests/test_manifest_schemas.py`
- [x] T8 — review against `requirements.md` §Security considerations (four abuse cases)
- [x] T10 — review of `commands/upgrade-the-loop.md` §3–4 + `uv run python scripts/validate_config.py`
- [x] T11 — read-through of `commands/init.md` and the user-facing docs
- [x] Regression — `make check` (full suite, lint, format, types, markdown, config validation)

## Verification results

Executed in full on 2026-08-14. Every activity ran; nothing was replanned or escalated.
Full output in [`evidence/verification.md`](evidence/verification.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run pytest cli/tests/test_harness_config.py` | 38 passed in 0.52s, including the new modeline case (red→green captured) | [T1](evidence/verification.md#t1--unit-adoption-keeps-the-modeline-first-and-the-default-stays-the-template) |
| T2 | `uv run pytest cli/tests/test_manifest_schemas.py` | 7 passed in 0.10s; all 7 red against the unchanged repository | [T2](evidence/verification.md#t2--repository-parity-the-manifest-the-schemas-and-the-modelines-agree) |
| T8 | review of the four abuse cases against the shipped mechanisms | all four met; the one new authority (`/upgrade` deleting three named files) is bounded by a closed list, an escape check and a fail-closed rule | [T8](evidence/verification.md#t8--security--abuse-cases) |
| T10 | review of `upgrade-the-loop.md` §3–4 + `uv run python scripts/validate_config.py` | R3.1–R3.5 met; this repo's 7 config files still VALID | [T10](evidence/verification.md#t10--migration--upgrade) |
| T11 | read-through of `init.md` + the `grep` sweep for project-relative schema paths | no step writes a schema; every surviving reference is a plugin-root path, this repo's own file, or a `deprecated` entry | [T11](evidence/verification.md#t11--read-through-of-the-command-and-the-user-facing-docs) |
| Regression | `make check` | lint, markdownlint (623 files), format, pyright, config validation all clean; 1895 passed + 1 skipped (+8) | [Regression](evidence/verification.md#regression--the-whole-gate) |

## Review comments

None yet.
