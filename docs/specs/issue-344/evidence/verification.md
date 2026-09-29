---
type: evidence
phase: verification
workItem: "github:MadaraUchiha-314/the-loop#344"
---

# Verification: programmatic hooks around the lifecycle of a work item's delivery

> The `verification` node's record, against [testing-plan.md](../testing-plan.md)'s
> matrix. Run in this container on the repository checkout (branch
> `claude/github-issue-344-u62t59`, on top of `bbb5714`), with `uv` 0.12.19 installed over
> the image's own 0.8.17 (`pyproject.toml` requires `>=0.12,<0.13`).

## Red first

The six new test files were copied into a worktree of the **base commit** (`bbb5714`) and
run there: every file failed to collect (`No module named 'the_loop.lifecycle'`,
`the_loop.sdk.hooks`, `the_loop.commands.hooks_cmd`) — 6 collection errors, 0 passed.
The first run on the implementation branch, before the wiring was finished, showed 7 red
in `test_lifecycle_declaration.py` (the empty-`tokenEnv` and empty-mapping rules) and one
red in the integration scenarios (the terminal-node expectation), each fixed and re-run.

## Results

| # | Type | Command | Outcome |
|---|------|---------|---------|
| T1 | Unit | `cd cli && uv run python -m pytest -q tests/test_lifecycle_contract.py` | **pass** — 28 (27 passed, 1 skipped when the docs tree is absent): the catalog, the base-class parity, JSON-typed fields, `to_params`/`from_params`, decision-only `apply` with type refusal, `copy_decisions_from`, `handles`, `describe`, the docs heading per point |
| T2 | Unit | `cd cli && uv run python -m pytest -q tests/test_lifecycle_declaration.py` | **pass** — 66 in the file; T2's: every R3 rule (grammar, uniqueness, exactly-one kind, cross-kind keys, `on ⊆ POINTS`, booleans, timeout, headers incl. the `Authorization` refusal, `tokenEnv` grammar, URL scheme and the cleartext-token refusal, an absent block, path resolution against the config file's directory, `~` and absolute paths, `.py` only) |
| T3 | Unit | same file, `-k load` | **pass** — module and path entries, ordering, `handles` narrowing, missing path/module, import and construction failures named, zero/several subclasses, `executor` as class or instance, `with` rules, once-per-process execution, an installed module from `sys.path` |
| T4 | Unit | `cd cli && uv run python -m pytest -q tests/test_lifecycle_runner.py` | **pass** — 22: order and carried decisions, the three return shapes, `hooks.decided` only on change, a raising hook recorded and skipped, wrong-typed and odd answers as failures, `required` at a `proceed` point and at one without, a later hook undoing a refusal, `LocalExecutor`, never raises; the seam: pass-through when nothing is declared, lazy configure, lazy failure → empty runner + one `hooks.load_failed`, strict raise for a daemon, no file → empty runner, `configure_from_config` path resolution, `reset`, the five event types catalogued |
| T5 | Integration | `cd cli && uv run python -m pytest -q tests/test_lifecycle_remote_integration.py` | **pass** — 11 against a live `HookServer` on loopback: the three Gherkin scenarios (answer over JSON-RPC, error as a recorded failure, bearer token only when set — with the server's own 401), unreachable / required-unreachable, a bounded timeout, extra headers, decisions-only from a sneaky server, every JSON-RPC error code, a response that is not its own, `GET /health` |
| T6 | Integration | `cd cli && uv run python -m pytest -q tests/test_lifecycle_hooks_integration.py` | **pass** — 12 over the real dispatcher: a refused start (disarmed, comment, `hooks.refused`, settled), a permitted start seen once, once across a deferred spawn, refused-then-re-armed asks again, a reworded boot prompt, a prevented launch (armed, comment, `spawn_failed will_retry=false`, settled), a silenced announcement and the unchanged default, a closure's `work_item_complete` with `announce=false` and the unchanged default |
| T7 | Integration | same file, `-k "graph or ask"` | **pass** — `phase_changed` at start / edge / terminal claim with `notify=false` silencing exactly one transition, `waiting_for_input(kind=gate)`, the unchanged publishes without hooks, an agent's question reworded before it is posted |
| T8 | Security | the four files above | **pass** — each of the eight abuse cases' named negative test (see [security-review.md](security-review.md)) |
| T9 | Contract / schema | `cd cli && uv run python -m pytest -q tests/test_config_schema_parity.py tests/test_configschema.py tests/test_docs_parity.py tests/test_eventlog.py tests/test_lifecycle_contract.py tests/test_state_portability.py` | **pass** — both schema copies identical, no validator-unknown keyword, the sample configs valid, every `hooks[].*` leaf documented, every emitted `hooks.*` type catalogued, every point has a docs heading, the new `lifecycle` section classified and documented |
| T10 | Unit | `cd cli && uv run python -m pytest -q tests/test_hooks_cmd.py` | **pass** — 8: registered, `list` imports and contacts nothing (a raising module, a refusing URL), JSON, nothing declared, a bad declaration and an unparseable config exit 1, `points` text and JSON, both daemons exit 1 before taking their lock on a bad declaration |
| T11 | Regression | `make test` (as part of `make check`) | **pass** — 4878 passed, 1 skipped in 171 s after the owner's two review rounds (`WorkItem` entity, `input_received`); 4854 at the first run; baseline before the change: 4706 passed, 1 skipped |
| T12 | Manual exploratory | — | **not run** — needs an operator's instance with a TLS-fronted hook server; T5 runs the same client against the same server over loopback |
| T13 | Documentation parity | `make lint` (ruff + markdownlint over every page) | **pass** — 0 errors |
| T14 | Performance | — | **n/a as planned** |
| T15 | UI | — | **n/a as planned** |
| T16 | Migration | — | **n/a as planned** — a new optional top-level key, no version bump |

The full run surfaced one race the wiring had introduced (self-review R1): the lifecycle
mark on the dispatch worker against a control command on the poller thread, both
read-modify-writing one portable record. Fixed with a per-directory lock in
`WorkItemStore.write_section`; the racy test (`test_pre_existing_control_comments_are_applied_in_thread_order`)
then passes 10/10, and `make check` was re-run green.

The rest of `make check`: `uv run ruff check cli hooks` — all checks passed;
`uv run ruff format --check cli hooks` — already formatted; `uv run pyright cli` — 0
errors, 0 warnings; `uv run python scripts/validate_config.py` — every config valid.

## What the run proves, in one line each

- A hook the operator declares is asked at each of the six moments, synchronously, and its
  decisions are what the-loop applies (T6, T7).
- A hook's answer changes decisions and nothing else, locally and over the wire (T1, T5).
- A failing hook is a recorded failure, never a stopped work item — unless the operator
  said `required` at a point that can refuse (T4, T5).
- A declaration that cannot load stops a daemon before it takes its lock, and stops a
  one-shot command from running hooks it did not load (T4, T10).
- An operator who declares nothing sees no change (T11).
