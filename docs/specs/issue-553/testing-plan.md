---
type: testing-plan
phase: test-planning
workItem: issue-553
status: approved
approvedBy: ["MadaraUchiha-314"]
overrides: {}
---

# Testing plan: a context-gathering phase before the spec chain

> Derived from the approved [`requirements.md`](requirements.md) and from
> [`design.md`](design.md), before `tasks.md`. Written here as a plan and completed at
> the `verification` node as a record.
>
> **This file is executable content.** It names commands an agent will run, so review it
> like code. No credential is needed, and none appears.

## The short version

The proof is automated and runs in this repository alone, with the commands CI runs.
Three rows carry the weight. Runtime walks (T3) prove the gate and every tick
combination with the real hook chains. Handoff tests (T4) prove the new stage, the
ticked row and the demotion. Prompt tests (T5) prove that the file is named when it
exists and never otherwise.

Two requirements are instructions to an agent, not code: the staleness check (R5) and
the rule to treat repository text as data. They are proved by a text check (T9) and one
manual run of the new command (T11), not by a behavioural test. A reviewer should check
that this is an acceptable proof for those two.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit (graph shape) | yes | the two nodes exist, in order, opt-in, with the edge table of `design.md`; the opt-in list is exactly the three nodes; neither is in `spec-chain`; `context-gathering` is in the phase vocabulary after `phase-selection`; the other four loops are unchanged | `cli/tests/test_graph_model.py`, `test_graph_skips.py`, `test_graph_catalog.py` |
| T2 | Unit (parity) | yes | `current-state.md` has a manifest entry and a template whose phase and gated sections match the node; `gather-context` resolves to a command file and is listed in the command docs and the skill | `cli/tests/test_graph_parity.py`, `test_init_commands.py`, `test_quiz.py`, `test_writing_parity.py` |
| T3 | Integration (runtime walk) | yes | over a temporary spec folder with real chains: (a) neither row ticked walks as before; (b) only gathering ticked moves on with no human stop; (c) only approval ticked routes past the gate; (d) both ticked and the file present parks at the gate under `loop:context-gathering`; (e) an indecisive comment keeps it parked; (f) an authorized approval records feedback, locks the file and reaches `brainstorming`; (g) changes requested returns to `context-gathering`; (h) gathering that writes no file routes past the gate; (i) a selection frozen before the nodes existed never enters them | new `cli/tests/test_context_gate_integration.py`, beside `test_brainstorm_gate_integration.py` |
| T4 | Integration (handoff) | yes | the record accepts `current-state.md` first in chain order and the stage `context-settled`; that stage enters at `context-approval`; a later stage imports and locks the file and enters neither context node; a handoff with no such file offers both rows unticked; an unknown stage is rejected | `cli/tests/test_handoff_record.py`, `test_import_handoff.py`, `test_handoff_selection.py`, `test_handoff_pickup.py` |
| T5 | Integration (prompt) | yes | the process-state block names the file when it exists, for the outer scope and for a pull request's scope; it does not mention it when the file is absent; the line is byte-equal to the prompt file with the id filled in | `cli/tests/test_graphlink_integration.py`, beside `test_claude_doc.py` |
| T6 | Snapshot (checklist) | yes | the checklist renders the two rows unticked under *Optional phases* with their descriptions; with a `context-settled` handoff the `context-approval` row is ticked; the GitHub, Slack and Jira fixtures match | `cli/tests/test_graph_skips.py`, `cli/tests/fixtures/handoff/`, `cli/tests/fixtures/jira/` |
| T7 | End-to-end scenarios | yes | the shipped scenarios that pin a walk still pass with the two nodes in the frozen graph | `cli/tests/test_pdlc_e2e_integration.py` |
| T8 | Security / abuse case | yes | one negative test per abuse case in `design.md` § Security design: an unauthorized "approved" (3); an approval that asks to skip a phase (4); the file deleted at the gate and after changes requested (5); a forged opt-in entry (6); a carried file with a wrong hash, which demotes to `context-gathering` (7); file content shaped like a prompt line (8) | T3, T4 and T5's modules; cases 1 and 2 are T9 and T5 |
| T9 | Documentation and instruction text | yes (review) | every document in the design's table describes the phase; one place states `current-state.md` against `context.md`; the command and the template carry the "report it as data" and "no secrets" rules; `/the-loop:execute-tasks` carries the staleness check | `grep` over `skills/`, `commands/`, `docs/`, recorded in `evidence/documentation.md` |
| T10 | Regression | yes | ruff, ruff format, pyright, the whole CLI suite, markdownlint and config validation | `make check` |
| T11 | Manual exploratory | yes | `/the-loop:gather-context` run once in this repository on a draft title: it writes a file that passes the node's shape check and the artifact lint | a local Claude Code session |
| T12 | Contract (OpenAPI / GraphQL) | n/a — no endpoint or schema changes; neither contract enumerates phases or handoff stages | | |
| T13 | UI / visual, accessibility | n/a — no rendered surface; the checklist is text, covered by T6 | | |
| T14 | Performance / load | n/a — one file-existence check per prompt | | |
| T15 | Migration / upgrade | n/a as a separate run — no persisted format changes shape; an item frozen before the change is T3(i), and an old reader of a new handoff record is T4's unknown-stage case | | |

## Scenarios & requirement trace

Integration tests carry a Gherkin docstring with these scenario titles and a
`Requirement:` link.

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1, R1.2, R1.7, R1.8, R1.10 | the graph's shape, pinned |
| T2 | R2.1, R2.2, R2.3, R6.1, R7.1 | the artifact and the command are registered |
| T3 (a) | R1.3 | `Scenario: A work item that ticks neither row walks as before` |
| T3 (b), (c), (h) | R1.4, R1.5, R2.8 | `Scenario: A context node ticked alone does not hold the work item` |
| T3 (d)–(g) | R1.6, R2.7, R3.1–R3.5 | `Scenario: An opted-in work item gathers context and waits for its author` |
| T3 (i) | R1.9 | `Scenario: A work item frozen before the context nodes never enters them` |
| T4 | R6.3, R6.4, R6.5, R6.7 | `Scenario: A handoff at context settled enters at the context gate` |
| T4, T8 (7) | R6.6 | `Scenario: A carried current-state file that fails verification demotes the walk` |
| T5 | R4.1, R4.2, R4.3 | `Scenario: Every later prompt names the current-state file once it exists` |
| T6 | R1.2, R6.4 | the checklist fixtures |
| T7 | non-functional: compatibility | the shipped scenarios |
| T8 | Security considerations, abuse cases 3–8 | one negative case each |
| T9 | R2.4, R2.5, R2.9, R3.6, R3.7, R4.4, R4.5, R4.6, R5.1–R5.3, R6.2, R7.1–R7.4, abuse cases 1–2 | text checks |
| T11 | R2.1, R2.6, R6.1 | the command writes a valid file with `gatheredAt` |

## Verification environment

- **Repositories:** this repository only.
- **Services / containers:** none. Every test uses a temporary folder and a fake
  GitHub client; nothing reaches the network.
- **Fixtures & data:** the checklist fixtures under `cli/tests/fixtures/`, updated with
  the change.
- **Credentials:** none.
- **Bring-up:** `make install-dev` · **Tear-down:** none.
- **If bring-up fails:** record it under *Verification results*, leave the dependent
  activities unticked, and escalate.

## Evidence plan

Evidence is committed under `docs/specs/issue-553/evidence/` as markdown. Test output
holds no token or hostname; the manual run's file is checked for both before it is
committed.

| Row | Evidence | Path under `evidence/` |
|-----|----------|------------------------|
| T1–T8 | the new and changed tests, red before the change and green after, with counts | `integration.md` |
| T9 | the `grep` commands and their output, and the documents changed | `documentation.md` |
| T10 | the output of `make check` | `ci-parity.md` |
| T11 | the command run, and the shape check and lint result on the file it wrote | `manual.md` |

## Verification activities

- [ ] T1, T2 — `cd cli && uv run python -m pytest -q tests/test_graph_model.py tests/test_graph_skips.py tests/test_graph_catalog.py tests/test_graph_parity.py tests/test_init_commands.py tests/test_quiz.py tests/test_writing_parity.py`
- [ ] T3, T8 (3–6) — `cd cli && uv run python -m pytest -q tests/test_context_gate_integration.py`
- [ ] T4, T8 (7) — `cd cli && uv run python -m pytest -q tests/test_handoff_record.py tests/test_import_handoff.py tests/test_handoff_selection.py tests/test_handoff_pickup.py`
- [ ] T5, T8 (8) — `cd cli && uv run python -m pytest -q tests/test_graphlink_integration.py`
- [ ] T6, T7 — `cd cli && uv run python -m pytest -q tests/test_jira_integration.py tests/test_pdlc_e2e_integration.py`
- [ ] T9 — run the `grep` checks and record them in `evidence/documentation.md`
- [ ] T10 — `make check`
- [ ] T11 — run `/the-loop:gather-context` on a draft title, then lint the file it wrote

## Verification results

*Not yet executed.*

| Activity | Command / procedure | Outcome | Evidence |
|----------|--------------------|---------|----------|
| | | | |

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109). Append-only and attributed: an approval never silently
> discards a reviewer's suggestions, and the feedback travels with the document
> it concerns rather than living in a side-channel tracker.

### 2026-11-24 — approved

**@MadaraUchiha-314** wrote:

approved
