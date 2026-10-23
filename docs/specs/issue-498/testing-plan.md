---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#498"
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a control keyword must open the comment; an ambiguous body is conversation

Everything is proved in this repository with the existing pytest suite: the parser is pure
and the dispatcher is exercised in-process by the routing tests. No service, credential or
network is involved.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | `parse_command` placements (R1.1–R1.4) | `uv run pytest cli/tests/test_control.py` |
| T2 | Integration (scenario) | yes | dispatcher routes an ambiguous comment to the session; the #496 comment reaches the session (R2) | `uv run pytest cli/tests/test_routing.py cli/tests/test_reactions.py cli/tests/test_reactions_integration.py` |
| T3 | Contract | n/a — no API shape changes; the schema edit is a description string only | | |
| T4 | End-to-end | n/a — no live GitHub needed: the dispatcher path is the same code the poller and webhook call, covered by T2 | | |
| T5 | UI / visual | n/a — no UI | | |
| T6 | Snapshot | n/a — no snapshot surfaces | | |
| T7 | Performance | n/a — one anchored regex per keyword, cheaper than today's unanchored search | | |
| T8 | Security / abuse case | yes | two different leading commands execute nothing; a mid-prose keyword executes nothing; a forwarded ambiguous body still meets the paused suppression | T1 + T2 commands |
| T9 | Accessibility | n/a — no UI | | |
| T10 | Migration / upgrade | n/a — no stored state or config shape changes | | |
| T11 | Manual exploratory | n/a — the repro is fully covered by T2 | | |
| T12 | Full suite + lint/type | yes | nothing else relied on mid-body keywords | `make check` |

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | leading keyword (with leading whitespace/newlines) → command |
| T1 | R1.2, R1.6 | the #496 body; keyword mid-line; in backticks at start; in a fenced block; in a `>` quote; on a later line of a body that opens with prose → no command |
| T1 | R1.3 | two `add-collaborator` lines → both subjects |
| T1 | R1.4 | `the-loop pause` then a line `the-loop resume` → ambiguous |
| T1 | R1.5 | Slack: mention-stripped text still parses (existing `test_channels*` suites, in T12) |
| T2 | R2.1–R2.3 | `Scenario: an ambiguous comment reaches the live session and executes nothing` |
| T2 | R1.2 | `Scenario: a comment discussing two commands in prose reaches the session` |
| T8 | Security | `Scenario: an ambiguous comment on a paused session is suppressed, not delivered` |
| T12 | R3 | docs/schema text reviewed in the diff; suite green |

## Verification environment

The repository checkout with `make install-dev` done. Commands: `uv run pytest …` as above,
`make check`. No credentials.

## Evidence plan

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1 | test summary | `unit.md` |
| T2, T8 | scenario table + run output | `integration.md` |
| T12 | `make check` summary | `lint-and-typecheck.md` |

## Verification activities

- [x] T1 unit tests pass (and the new ones failed before the fix)
- [x] T2/T8 dispatcher scenarios pass
- [x] T12 `make check` passes

## Verification results

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| T1 | `uv run pytest cli/tests/test_control.py` | 86 passed; the 13 new placement cases fail on the pre-fix parser | [unit.md](evidence/unit.md) |
| T2 / T8 | `uv run pytest cli/tests/test_routing.py cli/tests/test_reactions.py cli/tests/test_reactions_integration.py cli/tests/test_control_integration.py` | 291 passed, including the 3 new scenarios | [integration.md](evidence/integration.md) |
| T12 | `uv run pytest cli/tests`; `make lint format-check typecheck validate` | 6784 passed; all checks clean | [lint-and-typecheck.md](evidence/lint-and-typecheck.md) |
