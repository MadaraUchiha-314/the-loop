---
type: evidence
workItem: issue-553
---

# Final validation: a context-gathering phase before the spec chain

> The `evidence` node's proof, summarised from `testing-plan.md`'s Verification results
> and mapped onto the acceptance criteria. After verification, the critic and security
> reviews changed three behaviours; each has its own test, and `make check` was run
> again after the critic fixes (7982 passed, 2 skipped).

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1 — two opt-in nodes, off by default, in order, with a phase and label | the graph-shape test; walks for neither row, each row alone, both rows, and a state frozen before the nodes existed | `test_context_gate_integration.py`; [`integration.md`](integration.md) |
| R2 — `current-state.md`: template, manifest entry, sections, `gatheredAt`, shape check | the parity suites; a malformed file blocks the node; an absent file routes past the gate | `test_graph_parity.py`, `test_context_gate_integration.py`; [`manual.md`](manual.md) |
| R3 — the gate waits, locks on approval, returns on changes requested | three gate walks, including an unauthorized "approved" | `test_context_gate_integration.py` |
| R4 — later prompts name the file when it exists, and only then | the block rendered for the outer loop and for a pull request, with and without the file, byte-equal to the prompt file | `test_graphlink_integration.py` |
| R5 — the staleness check is an instruction that gates nothing | text check on `/the-loop:execute-tasks` and the workflow reference | [`documentation.md`](documentation.md) |
| R6 — `/the-loop:gather-context`; the handoff carries the file; *Context settled* enters at the gate with its row ticked; a later stage enters neither node; a failed file starts at `context-gathering` | record, checklist, walk and demotion tests; the gate entered by a handoff waits and then obeys its author | `test_handoff_record.py`, `test_handoff_selection.py`, `test_import_handoff.py` |
| R7 — the documentation says what the graph does | text checks; the command-listing parity test; decision-156 | [`documentation.md`](documentation.md) |
| Security considerations — abuse cases 1–8 | one negative test each for 3–8; text checks for 1–2; the security review | [`security-review.md`](security-review.md), [`integration.md`](integration.md) |
| Compatibility — nothing else changes | the whole CLI suite and the shipped end-to-end scenarios | [`ci-parity.md`](ci-parity.md) |

## Where the result differs from the approved design

1. **`context-approval` declares the phase `context-gathering`.** The design gave it no
   phase. A handoff that enters at the gate would otherwise keep the label
   `loop:phase-selection`, against Requirement 1.6.
2. **The prompt line does not say "as approved for this work item".** The line is
   emitted whenever the file exists, approved or not.
3. **`classify-feedback` changed.** The design said the gate hooks were reused
   unchanged. A gate entered by a handoff could not be answered; the fix also repairs a
   *brainstorm settled* handoff.

## Not proved

- The slash command was not invoked as a slash command (see [`manual.md`](manual.md)).
- The staleness check and the "report repository text as data" rule are instructions to
  an agent. No test shows an agent follows them.
- A pull request in another repository: the test renders the line for one, from the
  origin checkout. No run used a second repository.
