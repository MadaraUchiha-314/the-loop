---
type: testing-plan
phase: test-planning
workItem: "github:MadaraUchiha-314/the-loop#370"
status: in-review            # draft | in-review | approved
approvedBy: []
overrides: {}
---

<!-- Authored per the the-loop:writing skill. -->

# Testing plan: a pull request is tracked because the-loop recorded it

> Derived from `requirements.md` and `design.md`, **before** `tasks.md` — each task's
> `_Test:_` names a row of the matrix below. Authored at `test-planning`, completed at
> `verification`. See `reference/testing.md`.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. Nothing here needs credentials or the network: every row is a filesystem
> read through the stores, the poller with a fake provider, or the hook driven over its
> stdin/stdout contract with a fake `the-loop` on `PATH`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | a labelled PR linked to an issue only by `closingIssuesReferences` / branch / keyword keeps a portable record of **its own**; the issue's record gains no `pullRequests` entry (R1.1, R1.2, AC1) | `cli/tests/test_poller.py` |
| T2 | Unit | yes | the same PR **with** a registry binding is ledgered under the work item, and an already-ledgered PR keeps its owner (R1.1, AC2) | `cli/tests/test_poller.py` |
| T3 | Integration | yes | a comment on that PR is still delivered to the work item's session — delivery routing is untouched (R1.3, AC3) | `cli/tests/test_poller_integration.py` |
| T4 | Unit | yes | `_record_pr_binding` writes the registry endpoint and **no** `work-item-state.json` row; `on_pr_linked` records `linkedBy: "session"` (R2.1, AC4) | `cli/tests/test_graph_contribution.py` |
| T5 | Unit | yes | a v1 file carrying `linkedBy: "event"` loads and round-trips with that value intact (R2.2) | `cli/tests/test_graph_state.py` |
| T6 | Unit | yes | `set_pr_state` still records `merged`/`closed` on an existing row and creates none (R2.3) | `cli/tests/test_graph_state.py` |
| T7 | Unit | yes | `OPERATIONS` has no `linked-pulls`, and both transports refuse it as unsupported (R3.1, AC5) | `cli/tests/test_graph_integrations.py` |
| T8 | Unit | yes | the work-item brief request pre-fills `Pull requests:` from `work-item-state.json`'s `pullRequests[]`, then `pr-loops/`, deduplicated; the integration is never called; nothing recorded falls back to the ask-the-reviewer wording (R3.2, R3.3, AC5) | `cli/tests/test_graph_review.py` |
| T9 | Unit | yes | the hook links a PR from a `gh pr create` `PostToolUse` payload — `THE_LOOP_WORK_ITEM`, then registry-by-session-id, then registry-by-cwd — with the right argv (R4.1, R4.3, AC6) | `cli/tests/test_harness_link_pr.py` |
| T10 | Unit | yes | every degraded input is a silent exit 0 running nothing: no work item, no CLI on `PATH`, a non-matching tool, a failed/interrupted command, a response with no PR URL, malformed stdin (R4.2, R4.4, AC6) | `cli/tests/test_harness_link_pr.py` |
| T11 | Unit | yes | a cross-repository PR in the MCP response is linked by its **full ref**, not by number (R4.1) | `cli/tests/test_harness_link_pr.py` |
| T12 | Unit | yes | a tmux spawn for a work item carries `-e THE_LOOP_WORK_ITEM=<ref>`; a standing session carries none; an old tmux omits both env flags without failing (R5.1, R5.2, AC7) | `cli/tests/test_tmux_runner.py` |
| T13 | Parity | yes | `hooks/hooks.json` declares the `PostToolUse` entry pointing at the shipped file, and the file exists and is executable | `cli/tests/test_harness_link_pr.py` |
| T14 | Docs parity | yes | the capability docs and `reference/automation.md` no longer describe the removed inference (reviewed at `documentation`, recorded in `evidence/documentation.md`) | review |
| T15 | Security | yes | the hook never interpolates payload text into a shell, validates the extracted number and repository before they reach an argv, and bounds the subprocess with a timeout | `cli/tests/test_harness_link_pr.py` + `evidence/security-review.md` |
| T18 | Unit | yes | a PR armed as its own work item records itself with `self: true` and no `stateDir`; it round-trips; the self ref is refused without the marker; a delivering row keeps its inner loop and carries no marker key; a hand-written `stateDir` on a marked row is dropped (R7.1–R7.3, R7.5, AC8) | `cli/tests/test_graph_state.py` |
| T19 | Unit | yes | "is this work item a pull request?" is read from the arming event — true for a PR event about itself, false for an issue, false for an event about a *different* PR, false with no event; `on_arm` records the row for the first case only, and the write is idempotent (R7.1, R7.4, AC8) | `cli/tests/test_graphlink.py` |
| T16 | Performance | no | no hot path changes; the poller does strictly less work per item | — |
| T17 | Accessibility | no | no UI surface | — |

## Commands

```bash
make lint format-check typecheck
uv run --project cli python -m pytest -q cli
```

## Gherkin docstrings

`cli/tests/test_poller_integration.py` is a configured integration glob
(`.the-loop/harness-config.yaml` → `testing.integrationTestGlobs`), so T3's test carries a
Gherkin docstring naming the requirement it links.

## What is deliberately not tested

- GitHub's own linkage semantics. The removal means the-loop no longer reads them for
  tracking; the router's delivery use is unchanged and already covered by
  `cli/tests/test_routing.py`, which this work item does not touch.
- A live `gh pr create`. T9–T11 drive the hook over its documented stdin contract with a
  stub on `PATH`: the contract is the unit under test, and a network call would prove
  nothing the stub does not.
