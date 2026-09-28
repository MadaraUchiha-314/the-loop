---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#344"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: programmatic hooks around the lifecycle of a work item's delivery

> Derived from `requirements.md` and `design.md`, before `tasks.md` — each task's
> `_Test:_` names a row below. Authored at `test-planning`, completed at `verification`.
> **Executable content**: credentials by reference only.

## What is testable here, and what is not

Everything the change adds is a dataclass catalog, a parser over a mapping, a loader over
a `tmp_path` module, a chain runner, an HTTP client and server on loopback, six call sites
in code the suite already drives (`FakeTmux` dispatchers, `Runtime` over a `tmp_path` repo,
`ask_session` with a patched `gh`), and a CLI verb. No real GitHub, tmux or harness is
needed; the remote protocol is exercised against the shipped `HookServer` on `127.0.0.1`.

One row cannot run here: a real daemon with a real remote hook server behind TLS (T12)
needs an operator's instance. T5 runs the same client against the same server over
loopback HTTP.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | The contract: six contexts, `to_params` round trip, `apply` copies decisions only and refuses wrong types, `decisions()`, `LifecycleHooks.handles`, `POINTS` ↔ base-class parity, every field JSON-serialisable | `cd cli && uv run python -m pytest tests/test_lifecycle_contract.py` |
| T2 | Unit | yes | The declaration: every R3 rule (grammar, uniqueness, exactly-one kind, kind-specific keys, `on ⊆ POINTS`, URL scheme incl. the cleartext-token refusal, defaults), an absent block, path resolution against the config file's directory | `cd cli && uv run python -m pytest tests/test_lifecycle_declaration.py` |
| T3 | Unit | yes | The loader: `module` and `path` entries, `executor` selection (one subclass, several, none, an instance, `with`), import/construction failures named, the per-process cache | `cd cli && uv run python -m pytest tests/test_lifecycle_declaration.py -k load` |
| T4 | Unit | yes | The runner: order, decisions carried between executors, `None`/context/mapping returns, `hooks.decided`, a raising executor recorded and skipped, `required` at a `proceed` point, never raises; the process-wide seam (lazy configure, failure installs an empty runner + `hooks.load_failed`, `reset`) | `cd cli && uv run python -m pytest tests/test_lifecycle_runner.py` |
| T5 | Integration (scenario) | yes | The remote protocol end to end: `RemoteExecutor` against a live `HookServer` on loopback — pass-through, a decision change, an error member, a raising server method, an unknown method, a non-2xx, a timeout, the bearer header sent and checked, an unset `tokenEnv` sends nothing, `GET /health` | `cd cli && uv run python -m pytest tests/test_lifecycle_remote_integration.py` |
| T6 | Integration (scenario) | yes | The call sites over the real dispatcher (`FakeTmux`): `work_item_start` refused → disarmed, comment, no spawn, settled; fired once per arming across a deferred spawn; `session_spawn` rewrites the boot prompt and can refuse; `session_spawned` `announce: false` silences the announcer; `work_item_complete` fires on closure with `announce` honoured; a PR endpoint refusal falls back to the record's session | `cd cli && uv run python -m pytest tests/test_lifecycle_hooks_integration.py` |
| T7 | Integration (scenario) | yes | The graph runtime and `ask`: `phase_changed` on `start` and on a phase-changing `advance`, `notify: false` silences `publish_lifecycle`; `waiting_for_input(kind=gate)` on a human node; `ask_session` publishes the reworded question and summary | `cd cli && uv run python -m pytest tests/test_lifecycle_hooks_integration.py -k "graph or ask"` |
| T8 | Security / abuse case | yes | The eight abuse cases of `requirements.md`, each a named negative test (design § Security design table) | `cd cli && uv run python -m pytest tests/test_lifecycle_declaration.py tests/test_lifecycle_runner.py tests/test_lifecycle_remote_integration.py tests/test_lifecycle_hooks_integration.py` |
| T9 | Contract / schema | yes | Both copies of `cli-config.schema.json` identical; the documented `hooks` shape validates and an unknown key does not; the sample configs validate; every schema leaf has a docs heading; every emitted `hooks.*` type is in `EVENT_TYPES`; every point has a docs heading | `cd cli && uv run python -m pytest tests/test_config_schema_parity.py tests/test_configschema.py tests/test_docs_parity.py tests/test_eventlog.py tests/test_lifecycle_contract.py -k "schema or parity or documented"` |
| T10 | Unit | yes | `the-loop hooks` / `hooks points`: text and JSON, no import and no request (a module that would raise on import and a URL that would refuse a connection), exit 1 on a bad declaration | `cd cli && uv run python -m pytest tests/test_hooks_cmd.py` |
| T11 | Regression | yes | The whole suite — the dispatcher's spawn/close paths, the graph runtime and `ask` are touched; with no `hooks` declared they must behave as before (R7.2) | `make test` |
| T12 | Manual exploratory | yes | A real daemon with a remote hook server behind TLS: declare `url` + `tokenEnv`, arm a ticket, watch the comment carry the hook's rewording | an operator's instance; not available in this environment |
| T13 | Documentation parity | yes | Capability doc, config reference, command page, SDK page and skill describe the feature; markdown lint green | `make lint` |
| T14 | Performance / load | n/a — one in-process call per executor per point; a remote call is bounded by `timeoutSeconds`, stated in the requirements | | |
| T15 | UI / visual / accessibility | n/a — the-loop has no product UI; the surface is a config key, a CLI verb and an SDK | | |
| T16 | Migration / upgrade | n/a — a new optional top-level key; no version bump, no migration; an older config is unaffected (covered by T11) | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.4, R2.1, R2.2, R2.4 | contexts, decision-only apply, parity |
| T2 | R3.1–R3.4, R4.3, abuse 1, 4, 8 | every parse rule |
| T3 | R3.5, abuse 6 | loading local executors |
| T4 | R2.3, R5.3, R6.1–R6.3, R3.6, abuse 3, 6, 7 | the chain and the seam |
| T5 | R4.2–R4.4, abuse 2, 3, 5 | `Scenario: a remote executor answers a point over JSON-RPC` · `Scenario: a remote error is a recorded failure, not a stop` · `Scenario: the bearer token travels only when its variable is set` |
| T6 | R1.2, R2.6, R2.7, R7.1 | `Scenario: a hook refuses a start and the work item is disarmed with a reason on the ticket` · `Scenario: a hook rewords the prompt a session boots on` · `Scenario: a hook silences the session announcement` · `Scenario: work_item_start fires once across a deferred spawn` · `Scenario: a closure fires work_item_complete` |
| T7 | R1.2, R2.7, R7.1 | `Scenario: a phase change consults the hooks before the channels are told` · `Scenario: an agent's question is reworded before it is posted` |
| T9 | R1.3, R3.1, R5.3 | schema, docs and catalog parity |
| T10 | R5.1, R5.2 | the report imports and contacts nothing |
| T11 | R7.2 | the whole suite |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none; T5 starts `HookServer` on an ephemeral loopback port
  inside the test.
- **Fixtures & data:** hook modules written by the tests under `tmp_path`; `FakeTmux` and
  the stub adapters from `conftest.py`; a patched `gh` for `ask`.
- **Credentials:** none. A test token travels as the value of a variable the test sets in
  its own environment (`monkeypatch.setenv`).
- **Bring-up:** `uv sync` · **Tear-down:** none.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T11, T13 | command, outcome, counts, the red-first run | `verification.md` |
| T8 | the abuse-case table with each test's name | `security-review.md` |
| T13 | the list of pages changed | `documentation.md` |

## Verification activities

- [x] T1–T4, T10 unit tests written red, then green
- [x] T5–T7 integration scenarios written with Gherkin docstrings, red then green
- [x] T8 abuse cases asserted in the suite, not only in prose
- [x] T9 schema, docs, catalog parity green
- [x] T11 full `make test` green
- [x] T13 docs updated; `make lint` green
- [x] Evidence committed

## Verification results

Recorded at the `verification` node in
[evidence/verification.md](evidence/verification.md): T1–T11 and T13 pass (the whole
suite green under `make check`); T14–T16 are `n/a` as planned; T12 did not run for want of
an operator's instance with a TLS-fronted hook server — T5 drives the same client against
the same server over loopback.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.
