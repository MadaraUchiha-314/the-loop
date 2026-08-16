---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#243"
status: approved             # draft | in-review | approved
approvedBy: ["@MadaraUchiha-314"]
overrides: {}
---

# Testing plan: a forwarded event carries the instruction, not GitHub's metadata

> Derived from the approved [`requirements.md`](requirements.md) and
> [`design.md`](design.md), before `tasks.md`. Authored at `test-planning`, completed at
> `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit — comment surfaces | yes | R1: `issue_comment`, `pull_request_review_comment`, `pull_request_review` carry body + address + author and nothing else; anchor before body | `uv run pytest cli/tests/test_excerpt.py` |
| T2 | Unit — every other event | yes | R2: lifecycle, label, CI and `status` events keep what makes them actionable; an unknown event distils rather than falling back to raw | `uv run pytest cli/tests/test_excerpt.py` |
| T3 | Unit — caps and JSON validity | yes | R3: a 10 KB body truncates the field only; the excerpt parses; URL and anchor survive | `uv run pytest cli/tests/test_excerpt.py` |
| T4 | Integration (scenario) — ingress parity | yes | R4.1: the poller's synthesised event and the equivalent webhook event render the same fields, through one function | `uv run pytest cli/tests/test_excerpt_integration.py` |
| T5 | Integration (scenario) — the gates are untouched | yes | R5.1: authorization, self-comment detection, control parsing and reaction targeting still decide correctly on an event whose excerpt omits their inputs | `uv run pytest cli/tests/test_excerpt_integration.py` |
| T6 | Security / abuse case | yes | Abuse cases 1–4 of `requirements.md`: forged JSON in a body stays inside the string; a crowding body is bounded with its URL intact; an unlisted hostile field never reaches the prompt; a malformed container yields `{}` rather than raising | `uv run pytest cli/tests/test_excerpt.py -k abuse` |
| T7 | Regression — existing dispatcher/interaction suites | yes | R5.2: the `$payload_excerpt` placeholder contract, its position above/below the directive, and every existing delivery test still hold | `uv run pytest` |
| T8 | Measurement — before/after cost | yes | The non-functional numbers claimed in `requirements.md` § Introduction and `design.md` are measured, not asserted | `uv run python docs/specs/issue-243/evidence/measure_prompt.py` |
| T9 | Contract (OpenAPI / GraphQL SDL) | n/a — the change touches no API surface. `docs/api-specs/openapi` describes the control plane; the excerpt is prompt text inside the dispatcher | | |
| T10 | End-to-end | n/a — an end-to-end run needs a real `gh`, real credentials and a live tmux harness; none exist in this environment. T4/T5 cover the seam between ingress and prompt, which is what changed | | |
| T11 | UI / visual | n/a — the-loop has no product UI (`design.uiArtifacts.format: html`, unused here) | | |
| T12 | Snapshot | n/a — the excerpt's exact bytes are asserted field-by-field in T1–T3, which is a stricter and more readable check than a golden file | | |
| T13 | Performance / load | n/a — the function is a dict walk over ≤ 8 fields; the change strictly *reduces* work and output size | | |
| T14 | Accessibility | n/a — no human-facing UI | | |
| T15 | Migration / upgrade | n/a — no state, no config key, no on-disk format changes. An operator's custom template keeps working unchanged (R5.2), which T7 pins | | |
| T16 | Manual exploratory | n/a — no interactive surface changed; the reviewer reads the measured before/after in T8 instead | | |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2 | A conversation comment renders body, URL and author, and no `issue`, `sender` or API URL |
| T1 | R1.3 | An inline review comment renders `path` and `line` **before** `body` |
| T1 | R1.4, R1.5 | A review renders `state`, `body`, `html_url`, `author` — the author as a login string |
| T2 | R2.1, R2.2 | A `labeled` issue event renders the entity's four fields plus the label's name |
| T2 | R2.3, R2.4 | A failed `check_run` renders name/status/conclusion/URL and its `output` summary |
| T2 | R2.5 | A `status` event renders its root-level fields |
| T2 | R2.6, R2.7 | An event with no rule distils the containers it has; a payload with none renders `{}` |
| T3 | R3.1, R3.2, R3.3 | `Scenario: a comment carrying a 10 KB log is truncated to its body alone` |
| T4 | R4.1, R4.2 | `Scenario: the poller and the webhook render the same comment identically` |
| T5 | R5.1 | `Scenario: the gates read the payload, not the excerpt` |
| T6 | Abuse cases 1–4 | Forged JSON inside a body; crowding body with surviving URL; unlisted hostile field absent; malformed container tolerated |
| T7 | R5.2 | The existing `test_interaction.py` / `test_routing.py` assertions on the placeholder and delivered prompts |
| T8 | Non-functional cost | Measured baseline and post-change prompt sizes for the same event |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. No `gh`, no tmux, no network: the tests exercise pure
  functions and the dispatcher's fake-tmux seam the existing suite already uses.
- **Fixtures & data:** one realistic GitHub `issue_comment` payload (hand-built in the
  test module and in `evidence/measure_prompt.py`, shaped after GitHub's documented
  webhook payload — two `user` objects, `reactions`, `labels`, the full `issue`).
- **Credentials:** none. No test reads an environment variable or a secret.
- **Bring-up:** `uv sync` · **Tear-down:** none.
- **If bring-up fails:** record it under Verification results, leave the dependent
  activities unticked, and escalate.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T3, T6 | red run (tests failing against the undistilled tree) | `red.md` |
| T1–T7 | unit + integration run output, counts, duration | `unit-and-integration.md` |
| T7 | full-suite run, plus `ruff`, `ruff format --check`, `pyright`, `markdownlint` | `lint-and-typecheck.md` |
| T8 | the measurement script and its before/after output | `measure_prompt.py`, `baseline.md`, `after.md` |

## Verification activities

- [x] T1 — `uv run pytest cli/tests/test_excerpt.py`
- [x] T2 — `uv run pytest cli/tests/test_excerpt.py`
- [x] T3 — `uv run pytest cli/tests/test_excerpt.py`
- [x] T4 — `uv run pytest cli/tests/test_excerpt_integration.py`
- [x] T5 — `uv run pytest cli/tests/test_excerpt_integration.py`
- [x] T6 — `uv run pytest cli/tests/test_excerpt.py -k abuse`
- [x] T7 — `uv run pytest`
- [x] T8 — `uv run python docs/specs/issue-243/evidence/measure_prompt.py`

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1–T3, T6 (red) | `uv run pytest cli/tests/test_excerpt.py -q`, against the pre-change distiller | fail — 21 failed, 6 passed (the six pass in both trees; the file says which and why) | [`red.md`](evidence/red.md) |
| T4, T5 (red) | `uv run pytest cli/tests/test_excerpt_integration.py -q`, with `08b7bd6:excerpt.py` restored under the wired dispatcher | fail — 4 failed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T1, T2, T3, T6 | `uv run pytest cli/tests/test_excerpt.py -q` | pass — 27 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T6 | `uv run pytest cli/tests/test_excerpt.py -k abuse -q` | pass — 8 passed, 19 deselected | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T4, T5 | `uv run pytest cli/tests/test_excerpt_integration.py -q` | pass — 4 passed | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T7 | `uv run pytest cli -q` | pass — 2155 passed, 1 skipped | [`unit-and-integration.md`](evidence/unit-and-integration.md) |
| T7 | `ruff check`, `ruff format --check`, `pyright cli`, `markdownlint-cli2 "**/*.md"`, `validate_config.py` | pass — clean | [`lint-and-typecheck.md`](evidence/lint-and-typecheck.md) |
| T8 | `uv run python docs/specs/issue-243/evidence/measure_prompt.py` | measured — excerpt 4,014 → 203 chars (−94.9%), prompt 6,676 → 2,865 (−57.1%), and the excerpt parses | [`baseline.md`](evidence/baseline.md), [`after.md`](evidence/after.md) |

**Not executed:** none. Every activity in the checklist ran.

**Corrected after execution:** two numbers the specs carried before the code existed. The
distilled excerpt is **203** characters, not the ~238 `design.md` estimated (the estimate
counted a field the design later dropped — see below), and the integration suite is **4**
tests, not the 5 the plan sketched: ingress parity for a conversation comment and for the
review surfaces fit one test each rather than three.

**Changed during implementation:** the `issue` and `pull_request` containers do **not**
carry an `author`. The design said every container would; the first run of
`test_a_labeled_issue_carries_the_entity_and_the_label_that_is_the_event` showed what that
means in practice — GitHub's `issue.user` is whoever *opened* the item, not who acted, so
carrying it as `author` invites a session to reply to the wrong person. Those events carry
a top-level `actor` (from `router.event_actor`) and nothing else; `design.md` records the
rule.

## Residual risk

One assumption is not testable here: that the fields the allow-list keeps are the ones a
session actually needs. It is bounded rather than eliminated — the excerpt is *context*,
not an input to any decision (R5.1), and every carried object keeps its `html_url`, so a
session that needs a field the excerpt no longer shows can fetch the object. The failure
mode is a session asking one extra question, never a wrong action; the loud alternative
(the previous behaviour) was a truncated, unparseable excerpt.

## Review comments

*None yet.*
