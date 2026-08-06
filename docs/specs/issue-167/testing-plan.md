---
type: testing-plan
phase: test-planning
workItem: issue-167
status: approved              # draft | in-review | approved
approvedBy: []
overrides: {}
---

# Testing plan: six inert gates, and the assertion that will keep them honest

> Phase 3 of 4. Derived from the locked [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before `tasks.md`. Ticket:
> [issue #167](https://github.com/MadaraUchiha-314/the-loop/issues/167).
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credentials are involved — this work item touches no network and no
> secret store.

## Test matrix

**The proof this work item needs is a negative one:** the six gates must stop skipping,
and must not be able to start skipping again. Three rows carry that; the rest are `n/a`
for a pure library-and-YAML change with no runtime surface.

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `validate-artifacts` with `validates:`: an absent target blocks, a satisfied one passes, alternation and ambiguity behave as they do for `produces`, and every pre-existing branch (missing-artifact message, `optional:` skip, no-checks skip) is unchanged | `uv run --directory cli pytest tests/test_graph_hooks.py` |
| T2 | Integration (scenario) | yes | the real `security-review` node, driven through `run_chain` against a temp spec directory: blocks without its execution-log section, passes with it. Gherkin-documented | `uv run --directory cli pytest tests/test_graph_verification_integration.py` |
| T3 | Contract (OpenAPI / GraphQL SDL) | n/a — the change adds no API surface; `docs/api-specs/openapi` is untouched | | |
| T4 | End-to-end | n/a — the CLI end-to-end path is `the-loop graph`, covered by T2's chain-level drive; no shell-level behaviour changes | | |
| T5 | UI / visual | n/a — the-loop has no product UI (`design.uiArtifacts.format: html`, unused here) | | |
| T6 | Snapshot | n/a — no rendered output; the one message string that must stay stable is pinned by an equality assertion in T1 instead | | |
| T7 | Performance / load | n/a — two extra `Path.is_file()` calls per node boundary | | |
| T8 | Security / abuse case | yes | the fail-closed branch: a section gate that resolves no target **blocks** and is **not retriable**; and the parity assertion (P5) that fails when a node gates sections with nothing to read them from | `uv run --directory cli pytest tests/test_graph_hooks.py tests/test_graph_parity.py` |
| T9 | Accessibility | n/a — no user-facing surface | | |
| T10 | Migration / upgrade | n/a — no persisted state changes. `validates` is a hook parameter inside the shipped graph, so no run state, manifest entry or project file is migrated | | |
| T11 | Manual exploratory | yes | the ticket's own reproduction script prints nothing after the change — the defect's own definition, re-run | `uv run --directory cli python - <<'PY' …` (§ Verification results) |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.3, R1.4, R1.5 | a validated target that is absent blocks; present and satisfied passes; `produces` + `validates` findings arrive in one result; `a.md\|b.md` alternation; no checks and no target still skips |
| T1 | R2.3, R2.4 | `optional:` still skips; the missing-artifact message is byte-identical |
| T2 | R3.1, R3.2 | `Scenario: the security-review gate blocks a work item whose execution log has no security section` |
| T2 | R3.1, R3.2 | `Scenario: the security-review gate passes once the section is written` |
| T8 | R2.1, R2.2 | a section gate with no resolvable target blocks, not retriable |
| T8 | R4.1, R4.2, R4.3 | P5 over the **shipped** graph: every section gate resolves a target; every validated name is manifest-tracked; every demanded section exists in the bundled template |
| T11 | R3.3, R5.1–R5.3 | the reproduction script is silent; the template offers `## Capability docs`; the capability doc and decision record are present |

## Verification environment

Nothing beyond this repository and its own toolchain — the whole change is a Python
package plus checked-in markdown and YAML.

- **Repositories:** this repo only.
- **Services / containers:** none.
- **Fixtures & data:** none. The unit tests build spec directories under pytest's
  `tmp_path`; the parity test reads the **shipped** `pdlc.yaml`, `.the-loop/manifest.yaml`
  and `skills/the-loop/templates/` from the checkout.
- **Credentials:** none. This work item reads and writes no secret, and makes no network
  call.
- **Bring-up:** `uv sync --directory cli` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1, T2, T8 | full `pytest` run — counts, duration, the new tests named | `tests.md` |
| T8 | `ruff` + `pyright` output over the changed files | `lint-and-types.md` |
| T11 | the ticket's reproduction script, before and after — the before output is the defect, the after output is its absence | `reproduction.md` |

No capture in this work item can contain a token, a cookie, personal data or an internal
hostname: the outputs are pytest summaries, linter findings and a list of node ids. They
are committed as markdown, as the rule requires.

## Verification activities

- [x] T1 — `uv run --directory cli pytest tests/test_graph_hooks.py -q`
- [x] T2 — `uv run --directory cli pytest tests/test_graph_review_chain_integration.py -q`
- [x] T8 — `uv run --directory cli pytest tests/test_graph_parity.py -q`
- [x] T8 — P5 fails against the **unfixed** graph and the **unfixed** template (the check
      that the checks check something)
- [x] T11 — the behavioural reproduction: every review node blocks where it used to skip
- [x] Full suite — `uv run --directory cli pytest -q`
- [x] Lint + types — `ruff check`, `ruff format --check`, `pyright`, `markdownlint`

## Verification results

Every activity ran; nothing was left unexecuted. One activity's *shape* changed during
execution and is recorded as it happened rather than as it was planned — see T11.

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `pytest tests/test_graph_hooks.py -q` | pass — 42 tests, 12 of them new | [`evidence/tests.md`](evidence/tests.md) |
| T2 | `pytest tests/test_graph_review_chain_integration.py -q` | pass — 24: four Gherkin scenarios × all six review nodes | [`evidence/tests.md`](evidence/tests.md) |
| T8 | `pytest tests/test_graph_parity.py -q` | pass — 8, including P5a/P5b/P5c | [`evidence/tests.md`](evidence/tests.md) |
| T8 | P5a against the pre-fix graph (the six `validates:` lines removed) | **fails**, naming all six nodes | [`evidence/tests.md`](evidence/tests.md) |
| T8 | P5c against the pre-fix template (`## Capability docs` removed) | **fails**, naming the section and the node | [`evidence/tests.md`](evidence/tests.md) |
| T11 | every review node's exit chain driven over the shipped graph against an empty spec folder | all six `block` (`required artifact is missing … execution-log.md`); all six were `skip` before | [`evidence/reproduction.md`](evidence/reproduction.md) |
| Full suite | `pytest -q` | pass — 1380 passed, 1 skipped (pre-existing, unrelated) | [`evidence/tests.md`](evidence/tests.md) |
| Lint + types | `ruff check .`, `ruff format --check .`, `pyright`, `markdownlint-cli2` | clean | [`evidence/lint-and-types.md`](evidence/lint-and-types.md) |

**Planned differently from how it ran:** T11 was planned as "the ticket's reproduction
script prints nothing". It does **not** — that script tests for `sections:` without
`produces:`, a question that predates the `validates:` vocabulary, so it still prints six
lines after the fix. Rather than quietly swapping the activity, the evidence file records
the script's stale output, the corrected structural check (which is what P5a asserts in
CI), and the behavioural check that is the real proof: what each node's chain actually
returns. The integration file `test_graph_verification_integration.py` named in the plan
was likewise the wrong home — the scenarios landed in a new
`test_graph_review_chain_integration.py`, since they are the review chain's, not
issue-163's.

**Not executed:** none.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments. Append-only and attributed.
