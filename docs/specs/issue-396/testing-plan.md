---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#396"
status: in-review            # draft | in-review | approved — tier 3: locked with design.md at the PR
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: `graph status` reads the state file the runtime wrote

> Derived from [`bugfix.md`](bugfix.md) and [`design.md`](design.md). Planned at
> `test-planning`, results recorded at `verification` (below).

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `work_item_id` translates a ref (plain and host-qualified) to `issue-<n>`, passes a bare id and a non-GitHub ref through; `check` on a ref reads the same directory as on the id; the report carries `statePath`/`stateFound`; the issue-238 no-path answer is unchanged | `cd cli && uv run pytest tests/test_core_graphs.py` |
| T2 | Integration (scenario, Gherkin-docstringed) | yes | the CLI, in-process, over a real checkout with a real `work-item-state.json` and a real registry record: a ref from a foreign directory reports the runtime's node and names the checkout and the file; a bare id from a foreign directory prints the not-found path with its hint; `--repo` wins over the registry; from inside the checkout the registry is not consulted (R1.1–R1.3, R2.1, R2.4) | `cd cli && uv run pytest tests/test_graph_status_resolution.py` |
| T3 | Contract (OpenAPI) | yes | the authored contract still matches the served schema (the description changed, the surface did not) | `cd cli && uv run pytest tests/test_api_contract_parity.py` |
| T4 | End-to-end (live) | no — the daemon-run reproduction is the next live Slack run's; the state file and registry record are written here as the daemon writes them | | |
| T5 | UI / visual | n/a | | |
| T6 | Snapshot | n/a — the rendered lines are asserted directly (T2) | | |
| T7 | Security / abuse case | yes | a crafted "ref" that is not parsable is passed through untranslated (no new path shape); a registry `cwd` that is not a directory is ignored; the position-unknown answer still names no path | with T1 and T2 |
| T8 | Accessibility | n/a | | |
| T9 | Migration / upgrade | n/a — no key, state or schema change; `--repo` unset means what `.` meant | | |
| T10 | Manual exploratory | no — deferred to the next live run (B7's own steps) | | |
| T11 | Regression (full suite) | yes | every graph, check, API and MCP suite stays green | `cd cli && uv run pytest -q` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4 | `work_item_id`: `github:octo/repo#161` → `issue-161`; `github:ghe.corp.example/octo/repo#7` → `issue-7`; `issue-5` → `issue-5`; `jira:PROJ#5`-shaped → unchanged; `check(repo, "github:…#161")` equals `check(repo, "issue-161")` on this repository |
| T1 | R2.2 | `check` on this repository's `issue-161` carries `statePath` ending in `docs/specs/issue-161/work-item-state.json` and `stateFound` matching the file; the pinned key set gains exactly these two; the non-resolving answer keeps its six keys and names no path |
| T2 | R1.2, R2.1 | `Scenario: graph status with a ref from the daemon's config directory` — a checkout under `tmp_path` with `work-item-state.json` at `brainstorming`, a CLI config with `routing.registryDir`, a registry record whose `cwd` is the checkout; from another directory the command prints `at brainstorming`, `repo: <checkout> (from the session registry)`, `state: <checkout>/docs/specs/issue-1/work-item-state.json` |
| T2 | R2.1 | `Scenario: graph status with a bare id from a foreign directory` — `state: … (not found; … does not exist — run from the work item's checkout, or pass --repo)` and the start node |
| T2 | R1.3 | `Scenario: --repo is given` — the registry is not consulted (its record points elsewhere; the given repo wins) |
| T2 | R1.3 | `Scenario: run from inside the checkout` — no `repo:` line; the state line names the file |
| T2 | R2.1, R2.3 | `Scenario: check with a ref` — the same resolution and `state:` line; `check --format json` carries the fields; `check --all` prints no `state:` line |
| T2 | R1.4 | `Scenario: a mutating verb keeps the working directory` — `graph complete <ref>` from a foreign directory addresses `./docs/specs/issue-1`, not the registry's checkout |
| T7 | security | a registry record whose `cwd` was cleaned up falls through to the working directory |

## Verification environment

- **Repositories:** this repo only.
- **Services / containers:** none; `THE_LOOP_SERVICE_LOCAL=1` keeps the CLI in-process.
- **Fixtures & data:** a checkout, a `cli-config.yaml` and a registry record written per
  test under `tmp_path`.
- **Credentials:** none.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record under Verification results, leave the rows unticked.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T7 | test names and run output, red → green noted | `automated-tests.md` |
| T11 | full-suite, lint, format, typecheck output | `automated-tests.md` |

## Verification activities

- [x] T1 + T7 — `cd cli && uv run pytest -q tests/test_core_graphs.py`
- [x] T2 + T7 — `cd cli && uv run pytest -q tests/test_graph_status_resolution.py`
- [x] T3 — `cd cli && uv run pytest -q tests/test_api_contract_parity.py`
- [x] T11 — `cd cli && uv run pytest -q` · `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli`

## Verification results

Recorded in [`evidence/automated-tests.md`](evidence/automated-tests.md).

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T7 | `cd cli && uv run python -m pytest -q tests/test_core_graphs.py` | pass — 20 passed (10 red before the fix) | `evidence/automated-tests.md` |
| T2 + T7 | `cd cli && uv run python -m pytest -q tests/test_graph_status_resolution.py` | pass — 8 passed (all red before the fix) | `evidence/automated-tests.md` |
| T3 | `cd cli && uv run python -m pytest -q tests/test_api_contract_parity.py` | pass — 2 passed | `evidence/automated-tests.md` |
| T11 | `cd cli && uv run python -m pytest -q` · `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli` | pass — 4308 passed, 1 skipped; ruff and pyright clean | `evidence/automated-tests.md` |

## Review comments

*None yet.*
