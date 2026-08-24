---
type: testing-plan
phase: test-planning
workItem: "issue-279"
status: approved
approvedBy: []
overrides: {}
---

# Testing plan: a first-class PR review workflow

> Derived from the approved `requirements.md` and `design.md`, **before** `tasks.md`.
> Authored at `test-planning` and completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | the graph compiles with the specified shape and gates nothing; `parse_brief`'s accepted and refused shapes; `post-review-brief`'s idempotence and fast path; `classify-review-brief`'s waiting / briefed / short-circuit; the `review` keyword's parsing, arming and spawn-arming; `resolve_outer_loop` and `LOOP_FOR_CONTROL_COMMAND` extended fail-closed | `uv run --project cli pytest cli/tests/test_graph_review.py` |
| T2 | Integration (scenario) | yes | the whole walk against the stub GitHub integration — `review-brief → (briefed) → review → follow-up → (more-work) → review → follow-up → (done) → complete` — with Gherkin docstrings; PR-first targeting through the dispatcher (`the-loop review` on a PR with a linked issue binds to the PR) | `uv run --project cli pytest cli/tests/test_graph_review.py -k "Walk or target"` |
| T3 | Contract (OpenAPI / GraphQL SDL) | yes | the control-plane contract is unchanged by this work item — no route, request or response shape is added; `test_api_contract_parity` proves it | `uv run --project cli pytest cli/tests/test_api_contract_parity.py` |
| T4 | End-to-end | n/a — the e2e harness (`cli/tests/test_pdlc_e2e/`) drives the **outer** loop's phase chain against a mocked agent; the review loop has no phase chain, and T2 already exercises every node and edge it has | | |
| T5 | UI / visual | yes | the Sessions screen renders a `pdlc-review-loop` item treeless, like the other guest/ad-hoc loops | `cd ui && bun run test` |
| T6 | Snapshot | n/a — no snapshot-tested output in this change | | |
| T7 | Performance / load | n/a — one more YAML compiled at load, one more tuple membership test per resolution; no hot path | | |
| T8 | Security / abuse case | yes | one negative test per abuse case in `requirements.md` §Security considerations: unauthorized arming, two-command refusal, unauthorized brief, self-authored brief/"done", invented loop name, unauthorized reply at the follow-up gate | `uv run --project cli pytest cli/tests/test_graph_review.py -k "unauthorized or refused or invented or self_authored or cannot or empty_allowlist or prose"` |
| T9 | Accessibility | n/a — no new UI surface beyond one existing list rendering path | | |
| T10 | Migration / upgrade | yes | a pre-issue-279 `graph-state.json` still resolves exactly as before; the two generalized adoption call sites (`GUEST_LOOPS`) are behaviour-preserving for the existing loops; the full suite proves nothing else moved | `uv run --project cli pytest cli/tests/test_graph_contribution.py cli/tests/test_graph_adhoc.py cli/tests/test_graphlink.py cli/tests/test_core_graphs.py`, then `uv run --project cli pytest -q cli` |
| T11 | Manual exploratory | n/a — every surface is a library call or a config leaf, and the parity tests cover the docs/schema pairing mechanically | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1–R1.6 | the shipped graph compiles; four walkable nodes plus two terminals; no `produces`; no `validate-artifacts`; no `skipSets`; no `skippable`; existing phase vocabulary only; a repo-supplied override is warned about |
| T1 | R2.1, R2.3 | `review` is in `COMMANDS`, `SPAWN_COMMANDS` and the arming set; `DEFAULT_KEYWORDS[review] == "the-loop review"`; the keyword is configurable and disablable |
| T1 | R2.4 | `resolve_outer_loop` accepts `pdlc-review-loop` and still returns `""` for an invented name, for `pdlc-pr-loop`, and for the default |
| T1 | R4.2–R4.6 | `parse_brief` accepts one/two/three filled sections and refuses an empty form; `post-review-brief` skips when a brief or its marker already exists; `classify-review-brief` waits on silence, freezes the newest brief with provenance, and short-circuits once decided |
| T2 | R4.1, R5.1–R5.3, R6.1 | `Scenario: a review walks brief → review → follow-up rounds → complete on the reviewer's replies` |
| T2 | R3.1–R3.2 | `Scenario: the-loop review on a pull request binds the review to the pull request itself` (linked issue present) and the plain-issue fallback |
| T2 | R2.5 | `Scenario: the core verbs address a review item through its recorded loop` |
| T3 | R1.1 | the control-plane API contract is unchanged |
| T5 | design §10 | a review item renders treeless on the Sessions screen |
| T8 | abuse 1 | `Scenario: an unauthorized "the-loop review" arms nothing` |
| T8 | abuse 2 | `Scenario: a comment carrying two control keywords is refused` |
| T8 | abuse 3 | `Scenario: an unauthorized brief leaves the brief gate waiting` |
| T8 | abuse 4 | `Scenario: the harness can neither brief nor end its own review` |
| T8 | abuse 5 | `Scenario: an invented loop name in agent-writable state selects no graph` |
| T8 | abuse 6 | `Scenario: an unauthorized reply leaves the follow-up gate open` |
| T10 | R7.1, R7.3 | the contribution, ad-hoc and outer loops behave identically after the `GUEST_LOOPS` generalization |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test is an in-process filesystem test against
  `tmp_path`; the GitHub integration is the suite's existing stub.
- **Fixtures & data:** `cli/tests/conftest.py` and the fakes in `test_graph_review.py`
  (mirrored from `test_graph_adhoc.py`).
- **Credentials:** none — no test touches the network.
- **Bring-up:** `uv sync` (and `cd ui && bun install` for T5) · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | the new suite's run output (counts, duration, scenario names) | `unit-and-integration.md` |
| T3, T10 | the full suite's run output, proving nothing else moved | `full-suite.md` |
| T5 | the UI suite's run output | `ui-suite.md` |
| — | `ruff`, `pyright`, `markdownlint` and `validate_config` output | `lint-and-types.md` |

## Verification activities

> Run from `cli/`, so `pytest`'s configured `testpaths` apply.

- [x] T1 — `uv run pytest tests/test_graph_review.py`
- [x] T2 — `uv run pytest tests/test_graph_review.py -k "Walk or target"`
- [x] T3 — `uv run pytest tests/test_api_contract_parity.py`
- [x] T5 — `cd ui && bun run test`
- [x] T8 — `uv run pytest tests/test_graph_review.py -k "unauthorized or refused or
  invented or self_authored or cannot or empty_allowlist or prose"`
- [x] T10 — `uv run pytest tests/test_graph_contribution.py tests/test_graph_adhoc.py
  tests/test_graphlink.py tests/test_core_graphs.py`, plus `uv run pytest` for the whole
  suite and its parity tests
- [x] lint / types — `uv run ruff check cli hooks`, `uv run ruff format --check cli
  hooks`, `uv run pyright cli`, `markdownlint-cli2`, `scripts/validate_config.py`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 + T2 + T8 | `uv run pytest tests/test_graph_review.py` (from `cli/`) | pass — 55 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T2 | `uv run pytest tests/test_graph_review.py -k "Walk or target"` | pass — 5 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T3 | `uv run pytest tests/test_api_contract_parity.py` | pass — 2 passed | [`evidence/full-suite.md`](evidence/full-suite.md) |
| T5 | `cd ui && bun run lint && bun run test && bun run build` | pass — 157 passed (12 files), lint and build clean | [`evidence/ui-suite.md`](evidence/ui-suite.md) |
| T8 | `uv run pytest tests/test_graph_review.py -k "unauthorized or refused or invented or self_authored or cannot or empty_allowlist or prose"` | pass — 9 passed | [`evidence/unit-and-integration.md`](evidence/unit-and-integration.md) |
| T10 | `uv run pytest tests/test_graph_contribution.py tests/test_graph_adhoc.py tests/test_graphlink.py tests/test_core_graphs.py` | pass — 162 passed | [`evidence/full-suite.md`](evidence/full-suite.md) |
| whole suite | `uv run pytest` (from `cli/`) | pass — 2660 passed, 1 skipped (+60 over the 2600 issue-277 recorded on `main` at `b6bfda1`) | [`evidence/full-suite.md`](evidence/full-suite.md) |
| lint / types | `uv run ruff check cli hooks` · `uv run ruff format --check cli hooks` · `uv run pyright cli` · `markdownlint-cli2` (870 files, 0 errors) · `scripts/validate_config.py` (7 VALID) | pass | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Not executed:** none.

## Review comments
