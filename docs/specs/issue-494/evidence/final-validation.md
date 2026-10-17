---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#494"
---

# Final validation: gate the brainstorm on its author's approval

## Final validation evidence

Summarised from [`verification.md`](verification.md) and the review records, at head
`cce3f96` and the record commits after it.

| Acceptance criterion | Met by | Proof |
|----------------------|--------|-------|
| R1.1 a written brainstorm enters `brainstorm-approval` | `brainstorming --pass--> brainstorm-approval` | `test_a_written_brainstorm_waits_at_its_gate_across_comments` |
| R1.2 indecisive comments keep it waiting, label stays `loop:brainstorming` | `classify-feedback` returns `wait`; the node declares no phase | same test (a question, a remark) |
| R1.3 approval records feedback, locks, moves to requirements | `record-feedback`, `lock-artifacts` | `test_an_approval_locks_the_brainstorm_and_moves_to_requirements` |
| R1.4 changes-requested returns to brainstorming | the `changes-requested` edge | `test_changes_requested_returns_to_brainstorming` |
| R1.5 same authorization as `requirements-approval` | the reused hooks; an unauthorized "approved" waits; deleting the file blocks | the same test, plus the two `test_deleting_the_brainstorm_*` tests |
| R1.6 regression tests red before, green after | 9 new tests fail with `origin/main`'s graph and hooks | `verification.md` |
| R2.1 no brainstorm → straight to requirements | `absentOutcome: not-entered` | `test_no_brainstorm_goes_straight_to_requirements` |
| R2.2 declared-skipped brainstorming never enters the gate | the `skipped` edge, plus `whenPresent` over `skipped_artifacts` | `test_a_skipped_brainstorm_never_reaches_its_gate`, `test_a_skipped_brainstorm_left_on_disk_is_not_reported_at_its_gate` |
| R2.3 selectable, in `spec-chain`, skipped alone keeps the old route | the checklist row, the skip set, its `skipped` edge | `test_declaring_the_gate_away_restores_the_old_route`, the `test_graph_skips.py` pins, the Jira fixtures |
| R2.4 custom graphs unchanged | both parameters are opt-in | `test_absent_outcome_is_opt_in_and_says_nothing_once_the_artifact_exists` |
| R3.1, R3.2 docs describe the gate | the skill, workflow, commands, template, capabilities, README | `documentation.md` |

**Checks.** Lint, format, pyright and `validate` are clean. Full suite: 6128 passed and 21
failed, the same 21 as on the base commit `584958c` (they read this host's live poller).
Reviews: two self-review rounds (S1–S4, all fixed or documented), one critic round (C1,
fixed), and the security review (pass, tier 3).

**CI `gate`.** It stays red until `human-approval`, because it names the next review
node that has not run yet. That was escalated on the PR; no code change was made for it.
