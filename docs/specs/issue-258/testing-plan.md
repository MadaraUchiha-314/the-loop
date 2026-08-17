---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#258"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
checkmarks: complete          # pending | complete
overrides: {}
---

# Testing plan: three named choices, and a tree the endpoint can actually work in

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning` and completed at `verification` — one file, written once as a
> plan and once as a record.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `TmuxConfig` mode parsing (every input in the design's table), `_endpoint_for` under all three modes, `Workspace.prepare(require_branch=…)` both ways | `make test` (`cli/tests/test_routing.py`, `cli/tests/test_workspace.py`) |
| T2 | Integration (scenario) | yes | end-to-end through the dispatcher against real `git`: `always` spawns a second tmux session for a **same-repository** pull request when it gets a clone of its own; the same config **declines** to one session under `strategy: worktree` | `make test` (`cli/tests/test_workspace.py` — the dispatcher+real-git integration tests live beside the workspace they drive) |
| T3 | Contract (OpenAPI / GraphQL SDL) | yes | `cli-config.schema.json` accepts the two booleans and the three names and rejects anything else; the packaged copy is byte-identical to the authored one | `make test` (`cli/tests/test_configschema.py`, `cli/tests/test_config_schema_parity.py`), `make validate` |
| T4 | End-to-end | n/a — a real `claude` process against real GitHub webhooks is not reproducible in this repository's suite; T2 covers the same path with the harness adapter and tmux faked, which is how every routing behaviour in the-loop is proved | | |
| T5 | UI / visual | n/a — no user interface; the surface is a config key and a tmux session name | | |
| T6 | Snapshot | n/a — no rendered artifact is produced or compared | | |
| T7 | Performance / load | n/a — the change is one string comparison on a path that already does a repository comparison; it adds no I/O. `always` raises *concurrency*, which is bounded by the existing `maxConcurrentDispatches` and is the operator's choice, not a regression to measure | | |
| T8 | Security / abuse case | yes | one negative test per boundary in `design.md` §Security design: an unrecognised mode fails closed to `cross-repository`; a hostile head ref declines the session rather than spawning onto the wrong tree | `make test` (`cli/tests/test_routing.py`, `cli/tests/test_workspace.py`) |
| T9 | Accessibility | n/a — no user interface | | |
| T10 | Migration / upgrade | yes | an existing config carrying `sessionPerPr: true` / `false` — and one carrying neither — keeps its exact current behaviour (R3); no session-record migration exists to test, by design | `make test` (`cli/tests/test_routing.py`) |
| T11 | Manual exploratory | n/a — every claim in the requirements is mechanically checkable, and this repository's own daemon config is not switched to `always` by this work item | | |
| T12 | Lint / typecheck / docs parity | yes | `ruff`, `ruff format --check`, `pyright`, `markdownlint`, and the docs↔schema parity gate (P3/P4/P5) that fails if the new key's values are undocumented | `make lint`, `make format-check`, `make typecheck`, `make test` (`cli/tests/test_docs_parity.py`) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.5, R3.1–R3.2 | every row of the design's C1 parse table, one assertion each |
| T1 | R1.1 | `never`: a cross-repository pull request routes to the work item's session |
| T1 | R1.2 | `cross-repository`: a same-repository pull request routes to the work item's session; a cross-repository one to its endpoint |
| T1 | R1.3 | `always`: a same-repository pull request routes to **its own** endpoint |
| T1 | R2.2 | `Workspace.prepare(require_branch=True)` raises when the branch cannot be checked out; `require_branch=False` still degrades to the detached default branch |
| T2 | R1.3, R2.1 | `Scenario: an operator who chose always gets a session per pull request in their own repository` |
| T2 | R2.2, R2.3 | `Scenario: always declines to one session when the pull request cannot have its own branch` |
| T3 | R3.3 | the schema accepts `true`, `false`, `never`, `cross-repository`, `always`; rejects `"sometimes"` and `3` |
| T8 | R1.5 | an unrecognised mode resolves to `cross-repository`, never to `always` |
| T8 | R2.2 (abuse case 1) | a head ref shaped like a git option is passed as an argument, fails the checkout, and declines the session |
| T10 | R3.1, R3.2 | a boolean config and an absent key are parsed to the modes they mean today |

## Verification environment

- **Repositories:** this repository only. The integration rows drive the dispatcher
  in-process with a faked harness adapter and a faked tmux — the observable seam every
  routing behaviour in the-loop is proved through — over **real** `git` clones and worktrees
  created in a `tmp_path`. They sit in `test_workspace.py` beside the existing
  `test_a_cross_repo_pr_endpoint_spawns_in_its_own_checkout`, which is the same shape, rather
  than in `test_webhook_routing_integration.py`, whose fixtures carry no git origin.
- **Services / containers:** none. No network, no GitHub, no `gh`.
- **Fixtures & data:** the existing `make_origin` / `_dispatcher` / `FakeTmux` helpers in
  `cli/tests/`; a local `git clone --bare` origin per test, with a pushed feature branch
  standing in for a pull request head.
- **Credentials:** none — this work item reads no credential. Nothing to reference.
- **Bring-up:** `uv sync` · **Tear-down:** none (`tmp_path` is torn down by pytest).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that never
  came up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T3, T8, T10 | the red run (before the fix) — the tests that must fail, failing | `red.md` |
| T1, T2, T3, T8, T10 | the green run: full suite summary plus the targeted node ids | `unit-and-integration.md` |
| T12 | `ruff`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config` output | `lint-and-typecheck.md` |
| T8 | the security review of this change | `security-review.md` |

No capture in this work item contains a token, a cookie, personal data or an internal
hostname: the runs are pytest and linter output over paths inside the repository and
`tmp_path`. Nothing is redacted because nothing needed redacting — stated rather than
implied.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py cli/tests/test_workspace.py`
- [x] T2 — `uv run --project cli python -m pytest -q cli/tests/test_workspace.py -k "always"`
- [x] T3 — `uv run --project cli python -m pytest -q cli/tests/test_configschema.py cli/tests/test_config_schema_parity.py` and `make validate`
- [x] T8 — the abuse-case assertions above, plus a security review of the diff
- [x] T10 — the back-compatibility assertions above
- [x] T12 — `make lint`, `make format-check`, `make typecheck`, and `pytest cli/tests/test_docs_parity.py`
- [x] Whole suite — `make test`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| Red run | `pytest -q` on the new tests, before the implementation | 28 failed across three files, as designed — the two red roots plus their dependants and the schema corpus | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_routing.py cli/tests/test_workspace.py` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `pytest -q cli/tests/test_workspace.py -k always` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T3 | `pytest -q cli/tests/test_configschema.py cli/tests/test_config_schema_parity.py`; `make validate` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md), [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| T8 | abuse-case tests + security review of the diff | pass — no new attack surface | [`evidence/security-review.md`](evidence/security-review.md) |
| T10 | back-compat assertions (`true`/`false`/absent) | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T12 | `make lint`, `make format-check`, `make typecheck`, `make validate`, docs-parity test | pass | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Whole suite | `make test` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |

**Not executed:** none. Every row marked `yes` ran; every row marked `n/a` carries its
reason in the matrix above.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
