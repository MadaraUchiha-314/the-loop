---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#260"
status: in-review             # draft | in-review | approved
approvedBy: []
collaborators: [engineer]
checkmarks: complete          # pending | complete
overrides: {}
---

# Testing plan: the checklist asks, the config answers when nobody did

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning` and completed at `verification` — one file, written once as a
> plan and once as a record.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the gate: the checklist renders three rows with the deployment's default pre-ticked; one ticked row freezes that mode; none/several fall back; a mode row is never read as a phase | `make test` (`cli/tests/test_graph_skips.py`) |
| T2 | Unit | yes | the resolver moved to `the_loop.prsessions` still answers decision-092 D2/D3 for every input, from its new home | `make test` (`cli/tests/test_routing.py`) |
| T3 | Unit | yes | routing: a frozen mode overrides the operator's default in `_endpoint_for`; an absent one falls back; an invalid one falls back; one work item's mode does not move another's | `make test` (`cli/tests/test_routing.py`) |
| T4 | Integration (scenario) | yes | the whole chain in one pass: an authorized `the-loop execute` ticking `pr-sessions-never` on a deployment configured `cross-repository`, then a cross-repository pull-request event routing into the **work item's** session | `make test` (`cli/tests/test_webhook_routing_integration.py`) |
| T5 | Contract (OpenAPI / GraphQL SDL) | n/a — no schema leaf is added, removed or retyped. `routing.tmux.sessionPerPr` keeps its type, enum and default; only its *description* and the docs page say it is now a default | | |
| T6 | End-to-end | n/a — a real `claude` process against real GitHub webhooks is not reproducible in this suite; T4 covers the same path with the harness adapter and tmux faked, which is how every routing behaviour in the-loop is proved | | |
| T7 | UI / visual | n/a — no user interface. The rendered checklist is markdown and is asserted as text in T1 | | |
| T8 | Snapshot | n/a — no rendered artifact is produced or compared | | |
| T9 | Performance / load | n/a — the added work is one small JSON read per routed pull-request event, on a path that already reads the session registry from disk. It changes no concurrency bound | | |
| T10 | Security / abuse case | yes | one negative test per boundary in `design.md` §Security design: an unauthorized ticker cannot freeze a mode; a token outside the vocabulary is ignored rather than obeyed or refused; a hand-edited portable record cannot introduce a fourth mode | `make test` (`cli/tests/test_graph_skips.py`, `cli/tests/test_routing.py`) |
| T11 | Accessibility | n/a — no user interface | | |
| T12 | Migration / upgrade | yes | a work item whose portable record predates this change (no `sessionPerPr` key) routes by `routing.tmux.sessionPerPr`, unchanged | `make test` (`cli/tests/test_routing.py`) |
| T13 | Manual exploratory | n/a — every claim in the requirements is mechanically checkable, and this repository's own daemon config is unchanged by this work item | | |
| T14 | Lint / typecheck / docs parity | yes | `ruff`, `ruff format --check`, `pyright`, `markdownlint`, and the docs↔schema parity gate that fails if the documented option drifts from the schema | `make lint`, `make format-check`, `make typecheck`, `make test` (`cli/tests/test_docs_parity.py`) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | the posted checklist carries all three `pr-sessions-*` rows, and the row matching the configured default is the ticked one |
| T1 | R1.1, R3.2 | a deployment configured `always` pre-ticks `pr-sessions-always`; a deployment configured with the legacy `false` pre-ticks `pr-sessions-never` |
| T1 | R1.2, R1.3, R1.4 | ticking `pr-sessions-always` freezes `always` into the decision, into the frozen graph, into the published record, and names it in the confirmation |
| T1 | R3.1 | no row ticked → the default; two rows ticked → the default |
| T1 | R3.3 | an unticked `pr-sessions-never` row is neither a declared skip nor a refusal |
| T1 | R1.5 | the contribution loop's checklist carries the rows (it reaches the gate); it still carries no surface row |
| T2 | R3.2 | `session_per_pr_mode` over the full input table: three names, both booleans, absent, and four unrecognised values |
| T3 | R2.1 | a portable record frozen to `always` routes a same-repository pull request to its own endpoint on a daemon configured `cross-repository` |
| T3 | R2.1 | a portable record frozen to `never` routes a cross-repository pull request to the work item's session on a daemon configured `cross-repository` |
| T3 | R2.2, T12 | a record with no frozen mode routes by the daemon's configured mode |
| T3 | R2.3 | a record frozen to `"sometimes"` routes by the daemon's configured mode |
| T3 | R2.4 | two work items, two frozen modes, one daemon — each routes by its own |
| T3 | R2.5 | `delivery_status` resolves through the frozen mode: a delivery recorded on the work item's session under `never` reports `done`, not `unhandled` |
| T4 | R1.2, R2.1 | `Scenario: a work item that chose one conversation keeps its pull request's events in it` |
| T10 | R1.2 (abuse case 1) | an unauthorized author's execute comment does not freeze a mode |
| T10 | R3.3 (abuse case 2) | `pr-sessions-sometimes` in a reply is ignored: default frozen, and the token appears in no refusal |
| T10 | R2.3 (abuse case 3) | a hand-edited `sessionPerPr` in the portable record cannot reach `TmuxConfig` |
| T14 | R4.3 | no new event name or `reason` value is introduced (asserted by the unchanged event tests continuing to pass) |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No network, no GitHub, no `gh`, no `git` beyond what the
  existing fixtures already create.
- **Fixtures & data:** the existing `selecting` / `repo` / `fake_github` fixtures in
  `cli/tests/test_graph_skips.py` for the gate; `make_dispatcher` / `FakeTmux` /
  `make_session` in `cli/tests/test_routing.py` for routing; the webhook integration
  fixtures for T4. The portable record is written through `ControlStore` in the tests, never
  by hand-crafted JSON, so the test exercises the same writer the daemon uses.
- **Credentials:** none — this work item reads no credential. Nothing to reference.
- **Bring-up:** `uv sync` · **Tear-down:** none (`tmp_path` is torn down by pytest).
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate — do not pass the gate on an environment that never came
  up.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T4, T10, T12 | the red run (before the implementation) — the new tests failing | `red.md` |
| T1–T4, T10, T12 | the green run: full suite summary plus the targeted node ids | `unit-and-integration.md` |
| T14 | `ruff`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config` output | `lint-and-typecheck.md` |
| T10 | the security review of this change | `security-review.md` |

No capture in this work item contains a token, a cookie, personal data or an internal
hostname: the runs are pytest and linter output over paths inside the repository and
`tmp_path`. Nothing is redacted because nothing needed redacting — stated rather than
implied.

## Verification activities

- [x] T1 — `uv run --project cli python -m pytest -q cli/tests/test_graph_skips.py`
- [x] T2, T3, T12 — `uv run --project cli python -m pytest -q cli/tests/test_routing.py`
- [x] T4 — `uv run --project cli python -m pytest -q cli/tests/test_webhook_routing_integration.py`
- [x] T10 — the abuse-case assertions above, plus a security review of the diff
- [x] T14 — `make lint`, `make format-check`, `make typecheck`, and `pytest cli/tests/test_docs_parity.py`
- [x] Whole suite — `make test`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| Red run | the four affected files, with `cli/the_loop/` stashed | 17 failed, 274 passed — the three fallback cases pass red by design | [`evidence/red.md`](evidence/red.md) |
| T1 | `pytest -q cli/tests/test_graph_skips.py cli/tests/test_graph_contribution.py` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2, T3, T12 | `pytest -q cli/tests/test_routing.py` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T4 | `pytest -q cli/tests/test_webhook_routing_integration.py` | pass | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T10 | abuse-case tests + security review of the diff | pass — no new attack surface | [`evidence/security-review.md`](evidence/security-review.md) |
| T14 | `make lint`, `make format-check`, `make typecheck`, `make validate`, the parity tests | pass (three lint findings fixed in the run, listed in the evidence) | [`evidence/lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| Whole suite | `make test` | 2333 passed, 1 skipped | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |

**Not executed:** none. Every row marked `yes` ran; every row marked `n/a` carries its
reason in the matrix above.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with comments.
