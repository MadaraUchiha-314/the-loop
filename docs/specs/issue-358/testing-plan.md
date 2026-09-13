---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#358"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: per-work-item model and effort choice, and spawning after the gate

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md), before
> [`tasks.md`](tasks.md). Authored at `test-planning`, completed at `verification`.
>
> **This file is executable content** — it names commands an agent will run. No credential
> appears in it, by value or by reference: this work item reads and writes none.

## What has to be proved

Three things carry the risk, and the matrix is shaped around them:

1. **No comment text reaches an argv.** Everything a reply can do is pick a key into the
   operator's declared list, and the argv is built from config or the adapter. This is the
   work item's one new trust boundary (T8).
2. **Nothing runs on a model the harness refuses.** The probe measures, the checklist
   withholds, resolution falls back, and the re-probe bounds the loop (T1, T2).
3. **R8 cannot strand a work item.** Deferral applies only at a human-gate start node;
   every other path spawns and respawns exactly as it does today (T2, T10).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `modelchoice` resolution and merge order; `modelprobe` verdicts, digest invalidation and the withhold-not-introduce rule; adapter `effort_args`/`with_args`; `selection.py` rendering and per-section parsing; registry round-trip | `make test` (`uv run --project cli python -m pytest -q cli`) |
| T2 | Integration (scenario) | yes | the four end-to-end behaviours below, Gherkin-documented, against a fake registry and a stub tmux | `uv run --project cli python -m pytest -q cli/tests/test_*_integration.py` |
| T3 | Contract (OpenAPI) | yes | the session schema gains `model`, `effort`, `harnessArgs`; the spec parses and matches what the API returns | `make validate` + the API route tests |
| T4 | End-to-end | n/a — an end-to-end run needs a real harness, a real tmux server and a real GitHub repository. The verification environment section says why that is out of scope here and what stands in for it (T2 with stubs at the same seams). | | |
| T5 | UI / visual | n/a — no product UI. The three human surfaces are text (checklist body, `sessions list` table, `models check` matrix) and are asserted as strings in T1/T2. | | |
| T6 | Snapshot | n/a — the one rendered artifact that would justify a snapshot is the checklist body, and T1 asserts its rows individually, which fails more usefully than a whole-body diff. | | |
| T7 | Performance / load | n/a — the feature adds no work to the delivery path: resolution reads a record the dispatcher already reads, and probing is off-path. T1 asserts the no-new-I/O property directly (no probe is invoked during a delivery). | | |
| T8 | Security / abuse case | yes | one negative test per abuse case A1–A7 of `requirements.md` § Security considerations | `uv run --project cli python -m pytest -q cli -k abuse` |
| T9 | Accessibility | n/a — no UI surface. | | |
| T10 | Migration / upgrade | yes | a config with no new sections behaves exactly as today; a session record written before this change still parses; `routing.harnessArgs` still works behind the deprecation shim | `make test` |
| T11 | Manual exploratory | n/a — every surface is deterministic and asserted; there is no interactive flow a human would find something in that T1/T2 would not. | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R2.5–R2.9, R3.1–R3.2 | model name → `[model_flag, name]`; effort level → `adapter.effort_args`; merge order is base → model → effort; a harness with no `model_flag` offers no model section |
| T1 | R2.2–R2.4 | a bare name is a candidate everywhere; `harnesses:` narrows; an undeclared harness in `harnesses:` contributes nothing |
| T1 | R7.2, R7.6 | verdict caching, `args_digest` invalidation, `unknown` stays offerable |
| T1 | R1.4–R1.5 | per-section parse: one tick, no tick, two ticks, unknown token, ambiguous model beside a valid effort |
| T1 | R5.1–R5.4 | the three session fields round-trip; a record without them parses and renders `-` |
| T2 | R1.3, R4.1–R4.2 | `Scenario: a work item that chose a model and an effort is respawned on both` |
| T2 | R7.3–R7.4 | `Scenario: a model the harness refuses is never spawned` |
| T2 | R8.1–R8.2 | `Scenario: an armed work item gets no session until its gate is answered` |
| T2 | R8.3 | `Scenario: a mid-graph work item still respawns` |
| T8 | A1 | an unauthorized reply freezes nothing |
| T8 | A2 | a reply naming a flag, a path or a metacharacter resolves to no choice |
| T8 | A3 | the argv contains only what the config and the adapter produced |
| T8 | A4 | a hand-edited frozen record naming an undeclared choice is ignored |
| T8 | A5 | a label named after a model selects nothing |
| T8 | A6 | an unreadable checklist keeps the operator's arguments |
| T8 | A7 | a forged availability verdict can withhold a choice but never introduce one |
| T10 | R6.1–R6.3, R2.12 | an untouched config is byte-identical in behaviour; the `routing.harnessArgs` shim warns and works |

## Verification environment

- **Repositories:** this one only.
- **Services / containers:** none. Every external seam is stubbed — the harness binary
  (`modelprobe` takes an adapter, so the probe is a fake in tests), tmux (the existing
  runner stub), and the GitHub integration (the existing `resolve("github", …)` seam the
  selection-hook tests already patch).
- **Fixtures & data:** temporary directories for the registry, the portable state and the
  verdict cache; the shipped process graphs, unmodified.
- **Credentials:** none. This work item reads and writes no secret, token or environment
  variable, and the probe inherits the daemon's environment exactly as a critic run does.
- **Bring-up:** `uv sync` · **Tear-down:** none (pytest temporary directories).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

**Why there is no T4.** An end-to-end run would need a real harness CLI with real model
access, a real tmux server and a real repository — none of which this repository's CI has,
and a probe against a live vendor would make the suite depend on an account. T2 stands in
for it at the same seams, which is where the logic being proved actually lives.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1 | pytest summary (counts, duration) | `unit.md` |
| T2 | scenario table (`the-loop scenarios --format markdown`) + run output | `integration.md` |
| T3 | `make validate` output and the changed contract excerpt | `contract.md` |
| T8 | the seven negative tests and their assertions | `security-review.md` |
| T10 | the before/after `sessions list` table and the shim's warning | `migration.md` |

Nothing captured here can contain a secret — no credential is read, and the only rendered
output is a checklist body, a verdict matrix and a session table over fixture data. The
redaction rule still applies to anything unexpected in captured output.

## Verification activities

- [ ] T1 — `make test`
- [ ] T2 — `uv run --project cli python -m pytest -q cli/tests/test_*_integration.py`
- [ ] T3 — `make validate`
- [ ] T8 — `uv run --project cli python -m pytest -q cli -k abuse`
- [ ] T10 — `make test` (the migration cases)
- [ ] lint/format/typecheck parity — `make check`

## Verification results

_Not yet executed._

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
