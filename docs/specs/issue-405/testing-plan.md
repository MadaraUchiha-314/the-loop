---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#405"
status: in-review            # draft | in-review | approved — tier 3: locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: the clause reader stops at the phases; the close path waits for the endgame

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `strip_signature` (same line, own line, mention form, plain, absent); `without_clause` with a same-line signature, markup-wrapped names and numbers, a zero-width space, the second-line signature (unchanged); `apply_without`'s 3-tuple, reasons and the position-naming refusal; the hostile-name rule still holds | `cd cli && uv run pytest tests/test_channels_verbs.py tests/test_selection_control.py` |
| T2 | Integration (scenario, Gherkin-docstringed) | yes | the typed reply through `process_reply`: a signed `execute without capability-docs` freezes the selection; a refused reply drops as `unknown-phase` with `read` on the record and the mirrored refusal; a protected phase stays `unskippable-phase` | `cd cli && uv run pytest tests/test_selection_control.py` |
| T3 | Integration (scenario, Gherkin-docstringed) | yes | the real `Dispatcher` over `FakeTmux` and a stub graph link: a closure at the terminal node is deferred (record live, harness not ended, `session.closing`); the completion claim ends the grace early (`finished: true`); the deadline ends it (`finished: false`, `waited_seconds`); a pointer off the terminal node, a dead pane, an unreadable graph or `finishGraceSeconds: 0` close at once; a reopen cancels; a duplicate close is a no-op; `merged: true` on an issue closure whose PR merged; the sweeper thread finishes a pending closure on its own | `cd cli && uv run pytest tests/test_finish_grace.py` |
| T4 | Contract (schema parity) | yes | the authored and packaged `cli-config.schema.json` copies agree on `finishGraceSeconds`; `TmuxConfig.from_mapping` reads it | `cd cli && uv run pytest tests/test_schema_parity.py tests/test_routing.py -k "tmux or schema"` |
| T5 | Unit | yes | `GraphContext.terminal` / `delivered_by_merge` from a real runtime state (`test_graph_drive.py`) | `cd cli && uv run pytest tests/test_graph_drive.py` |
| T6 | End-to-end (live) | no — the live Slack run is the operator's next run (run 4); this PR's `read` field and `info` log are what that run reads if P1 recurs | | |
| T7 | UI / visual | n/a | | |
| T8 | Snapshot | n/a — refusal text asserted directly (T1/T2) | | |
| T9 | Security / abuse case | yes | a `<!channel>`, `@here`, 60-char or `design;rm -rf /` item is still refused without echo; `read` never carries a non-token item's text; a state file that cannot be read closes at once | with T1, T2, T3 |
| T10 | Accessibility | n/a | | |
| T11 | Migration / upgrade | n/a — one additive key with a default; no state change | | |
| T12 | Manual exploratory | no — deferred to run 4 | | |
| T13 | Regression (full suite) | yes | every suite stays green; ruff, ruff format, pyright, markdownlint, `validate_config` | `cd cli && uv run pytest -q` · `make lint format-check typecheck validate` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | `execute without capability-docs *Sent using* @Claude` → `["capability-docs"]`; `… <@UCLAUDE>` and `… Sent using Claude` alike; `…\n*Sent using* @Claude` unchanged |
| T1 | R1.2 | `without *5*, _design_` plus a backticked `2` → `["5", "design", "2"]`; a `capability-docs` carrying U+200B → `capability-docs` |
| T1 | R1.3, R1.4 | `apply_without(rows, ["design", "*Sent"])` → composed `""`, a refusal opening *that name (word 2 after without)*, reason `unknown-phase`; `["security-review"]` → `unskippable-phase`; `[]` → `empty-clause`; `["9"]`, `["desgin"]` → `unknown-phase` |
| T2 | R1.1, R1.4, R1.5 | `Scenario: a signed execute-without freezes the selection` — the record is the checklist with the phase unticked; `Scenario: a non-token word refuses with its position and the drop names what was read` — outcome `unknown-phase`, `read == ["design", "<non-token: 5 chars>"]`, one mirrored comment |
| T3 | R2.1 | `Scenario: the issue closes while the session is at its terminal node` — `session.closing` emitted, registry record still live, `tmux.terminated == []`, no stamp |
| T3 | R2.2 | `Scenario: the session claims graph complete during the grace` — the next sweep closes: record closed, harness terminated, stamp present, `session.autoclosed finished=true` |
| T3 | R2.2 | `Scenario: the grace expires` — `sweep_closing(now=deadline+1)` closes with `finished=false`, `waited_seconds ≥ grace` |
| T3 | R2.3 | `Scenario: the pointer is on implementation` / `the pane is dead` / `the graph is unreadable` / `finishGraceSeconds: 0` — closed at once, no `session.closing` |
| T3 | R2.4 | `Scenario: reopened during the grace` — pending entry gone, `session.closing_cancelled`, record live; `Scenario: a second close arrives` — one pending entry, one `session.closing` |
| T3 | R2.5 | `Scenario: an issue closes after its PR merged` — `session.autoclosed merged=true` |
| T3 | R2.1, R2.2 | `Scenario: the sweeper thread finishes a pending closure` — `close_sweep_interval_seconds` lowered; the record closes without the test calling `sweep_closing` |
| T4 | R2.2 | both schema copies carry `finishGraceSeconds` with default `300`; `TmuxConfig.from_mapping({"finishGraceSeconds": 12})` reads `12.0` |
| T5 | R2.1, R2.5 | a runtime at its terminal node reports `terminal=True`; after `complete` it reports `status == "complete"`; a state with a merged PR reports `delivered_by_merge=True` |
| T9 | security | the hostile-name test unchanged; `read` for `<!channel>` is `<non-token: 10 chars>` |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none; no tmux (the `FakeTmux` double), no network.
- **Fixtures & data:** the existing `CHECKLIST` fixture, `make_dispatcher` /
  `FakeTmux`, a stub graph link returning a `GraphContext` per scenario.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record under Verification results, leave the rows unticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T4, T5, T9 | test names and run output, red → green noted | `automated-tests.md` |
| T13 | full-suite, lint, format, typecheck, markdownlint, validate output | `automated-tests.md` |

## Verification activities

- [x] T1 + T9 — `cd cli && uv run pytest -q tests/test_channels_verbs.py tests/test_selection_control.py`
- [x] T2 — `cd cli && uv run pytest -q tests/test_selection_control.py`
- [x] T3 + T9 — `cd cli && uv run pytest -q tests/test_finish_grace.py`
- [x] T4 — `cd cli && uv run pytest -q tests/test_config_schema_parity.py tests/test_finish_grace.py -k "schema or grace_seconds"`
- [x] T5 — `cd cli && uv run pytest -q tests/test_graph_drive.py`
- [x] T13 — `uv run --project cli python -m pytest -q cli` · `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli` · markdownlint on the touched files · `uv run python scripts/validate_config.py`

## Verification results

Recorded in [`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T2 + T9 | `cd cli && uv run python -m pytest -q tests/test_channels_verbs.py tests/test_selection_control.py` | pass — 52 passed (the suite failed at collection before the fix; the pre-fix reader shown red on the four P1 cases) | `evidence/automated-tests.md` |
| T3 + T9 + T4 | `cd cli && uv run python -m pytest -q tests/test_finish_grace.py` | pass — 12 passed (all red before the fix: `GraphContext` had no `terminal`) | `evidence/automated-tests.md` |
| T4 | `tests/test_config_schema_parity.py` (in the full run) | pass — both schema copies carry `finishGraceSeconds` | `evidence/automated-tests.md` |
| T5 | `cd cli && uv run python -m pytest -q tests/test_graph_drive.py` | pass — 25 passed | `evidence/automated-tests.md` |
| T13 | full suite · ruff · ruff format · pyright · markdownlint · validate | pass — 4335 passed, 1 skipped; **4 pre-existing failures in `tests/test_instance.py`** that fail identically on the base commit in this environment (the checkout's own `.the-loop/cli-config.yaml` is exported into the spawn env); ruff, format, pyright, markdownlint and validate clean | `evidence/automated-tests.md` |
