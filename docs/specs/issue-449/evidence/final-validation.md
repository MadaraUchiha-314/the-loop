---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#449"
---

# Final validation: Codex hosting and critic support

## Final validation evidence

| Acceptance criteria | Verification | Evidence |
| --- | --- | --- |
| R1: declared Codex hosting and critic support | Installed Codex completed test issue #3 and merged PR #4; adapter, output and usage regressions pass | [Completion verification](completion-verification.md), [earlier verification](codex-verification.md) |
| R2: exact conversation identity | A real newer unrelated chat did not alter the original native conversation match; invalid metadata and unsafe paths are rejected | [Completion verification](completion-verification.md) |
| R3: instructions, hooks and trust | Tracked project bytes preserved, native global/project guidance loaded, gate reviewed and trusted through native UI; negative and idempotence tests pass | [Completion verification](completion-verification.md), [security review](security-review.md) |
| R4: migration and delegation | Requested adapter and one-shot arguments used; unknown harness blocks; migrations preserve explicit choices | [Earlier verification](codex-verification.md), [testing plan](../testing-plan.md) |
| R5: diagnostics and durable starts | Routing/control/Codex coverage reports 672 passed, including preserved human-gate starts and disarmed genuine failures | [Completion verification](completion-verification.md) |

Local full-suite platform failures and unexercised native interruption/Stop
continuation cases are explicitly retained in the linked evidence. Main PR #450
remains open pending current-head CI and the selected human approval/security
sign-off. This record does not grant an approval.
