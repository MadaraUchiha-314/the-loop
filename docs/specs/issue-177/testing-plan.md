---
type: testing-plan
phase: test-planning
workItem: issue-177
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: proving a skip is declared, bounded, and never forged

> Phase 3 of 4. Derived from the locked [`requirements.md`](requirements.md) and
> [`design.md`](design.md). Ticket:
> [issue #177](https://github.com/MadaraUchiha-314/the-loop/issues/177).
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials are involved: every test runs against temp directories and a
> fake integration; nothing touches the network.

## Test matrix

| # | Type | In scope? | What it proves |
|---|------|-----------|----------------|
| M1 | Unit — graph compile | yes | R1.1–R1.4: `skippable` parsed and shown; `required`+`skippable` refused; skippable node without a `skipped` edge refused; bad `skipSets` member refused; `expand_skip_tokens` accepts ids and set names, rejects the rest |
| M2 | Unit — shipped graphs | yes | R1.5, R1.6, R4.1: exactly the six outer-loop nodes are skippable; `spec-chain` names exactly them; the floor nodes carry no marker; `pdlc-pr-loop` declares no skippable node |
| M3 | Unit — runtime routing | yes | R3.1, R3.5: pointer routes through declared-skipped nodes on `skipped` edges, runs none of their hooks (no phase label, no log entry), lands on the first non-skipped node and runs its entry |
| M4 | Unit — reporting | yes | R3.2, R3.3: `status()` (both modes) reports `skip` + provenance for declared skips; a forged declaration on `security-review` is inert and surfaced |
| M5 | Unit — artifact-gate tolerance | yes | R3.4: `implementation` with `tasks-breakdown` skipped and no `tasks.md` passes its artifact gate as a skip; a *present* `tasks.md` is still gated |
| M6 | Integration — the selection gate | yes | R2.1–R2.9: the checklist is posted once and names the executing loop's phases; the gate waits without an authorized `the-loop execute`; an unauthorized reply is ignored; unticked skippable phases become provenance-carrying skips and the loop proceeds; a protected phase is refused and named; `execute` with no list runs everything; an outage leaves the gate waiting |
| M7 | Unit — CLI verb semantics | yes | R2.10–R2.12: `declare_skips` requires a reason, refuses entered/past and non-skippable tokens, records provenance, posts one marked audit comment (fake integration) |
| M8 | Contract — API surface | yes | R2.10, R4.2: `POST /graph/skip` routes to core; the OpenAPI document declares it; MCP exposes no skip tool |
| M9 | Regression — full suite, lint, types | yes | nothing else moved: `pytest`, `ruff`, `ruff format --check`, `pyright`, `markdownlint`, `validate_config.py` |
| M10 | UI/visual, accessibility | n/a | no user-facing surface — CLI text and YAML only |
| M11 | Performance | n/a | one comment fetch per gate evaluation (already best-effort) and set lookups over ≤ 20 nodes; nothing hot |
| M12 | Migration | n/a | `skips` is an additive state key; existing `graph-state.json` files load unchanged (M4 exercises absent-key loads implicitly) |
| M13 | E2E against live GitHub | n/a | the integration seam is faked at the `add-comment`/`list-comments` operations the live transports already implement; live-credential runs stay out of CI by design |

## Verification environment

This repository's own checkout, nothing else: `uv` for the environment, `pytest` from
`cli/`, the linters from the repo root — the same commands CI runs
(`uv run --directory cli pytest -q`, `uvx ruff check`, `uv run --directory cli pyright`,
`markdownlint`). No second repo, no service, no secrets; integrations are faked in-process.

## Evidence plan

Committed under [`evidence/`](evidence/):

- `tests.md` — the new tests' red run (against the pre-change runtime, proving they test
  something) and the final green run with the full-suite counts.
- `walkthrough.md` — the motivating scenario end-to-end in a temp repo: a doc-fix work
  item entering the graph, the-loop's checklist, an authorized reply unticking the spec
  chain plus `the-loop execute`, `the-loop check` showing the provenance-carrying skips,
  and the tamper case refused.
- `lint-and-types.md` — ruff, pyright, markdownlint, config validation output.

## Activities checklist

- [x] M1–M8 written test-first and failing against the pre-change code where the
      behaviour is new (record the red in `evidence/tests.md`)
- [x] M1–M8 green
- [x] M9 full regression suite + lint + types green
- [x] Evidence committed and redacted (no tokens, no hostnames beyond github.com)

## Verification results

> Executed at the `verification` node on 2026-08-08. Per-activity record below;
> raw output in [`evidence/`](evidence/).

| Activity | Command | Outcome | Evidence |
|---|---|---|---|
| M1–M7 red→green | `uv run --directory cli pytest -q tests/test_graph_skips.py` | pass — 33 tests. Reds recorded: collection-level `ImportError` before the runtime existed; the shipped-vocabulary tests red before the YAML carried it; four selection tests red against the first (label) implementation | [`evidence/tests.md`](evidence/tests.md) |
| M2 shipped-graph audit | same file, `-k shipped` (3 tests) | pass — exactly six skippable outer-loop nodes; `spec-chain` names exactly them; the floor unmarked; the PR loop declares none | [`evidence/tests.md`](evidence/tests.md) |
| M6 the selection gate | same file, the `phase-selection` block (9 tests) | pass — posts once; waits without an authorized `the-loop execute`; ignores an unauthorized reply; records provenance and proceeds; refuses a protected phase; `execute` with no list runs everything; an outage leaves it waiting | [`evidence/tests.md`](evidence/tests.md) |
| M7/M8 operator + contract surface | `uv run --directory cli pytest -q tests/test_core_graphs.py tests/test_api_contract_parity.py` | pass — core `skip()` declares/rejects against the shipped vocabulary and requires a reason; the served schema matches the authored contract including `POST /graph/skip` | [`evidence/tests.md`](evidence/tests.md) |
| M9 full suite | `uv run --directory cli pytest -q` | pass — 1458 passed, 1 skipped (baseline 1423/1; the +35 are this item's tests) | [`evidence/tests.md`](evidence/tests.md) |
| M9 lint/types/config | `uvx ruff check cli` · `uvx ruff format --check cli` · `uv run --directory cli pyright` · `npx markdownlint-cli2` over the changed docs · `uv run python scripts/validate_config.py` | pass — all clean | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |
| Walkthrough (the ticket's scenario) | scripted temp-repo run against the shipped graph: entry → checklist → authorized reply → `check --recompute` → tamper | pass — the gate held until `the-loop execute`; the reply's unticked phases became provenance-carrying skips; the pointer landed on `test-planning`, which still blocks for its missing plan; a forged skip on `security-review` was inert and surfaced | [`evidence/walkthrough.md`](evidence/walkthrough.md) |
