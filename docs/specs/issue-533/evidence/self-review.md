---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#533"
---

# Self-review: opt-in session credentials, never on argv

Policy (`the-loop critic policy`): `selfReviewCount: 2`, `criticReviewCount: 1`,
stop on no new findings, escalate on a repeated finding.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | `[claude/opus-5.5]` | new findings | SR1-1 (high): a name in both `sessionPassthrough` and `sessionCredentials` rode `tmux -e` → **fixed** (`047ecc8c`, negative test). SR1-2 (low) repeated warnings → won't-fix (visible misconfiguration feedback, names only). SR1-3 (low) an entry named `PATH` strips it from out-of-scope panes → won't-fix (operator error, obvious symptom) | [PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/535#issuecomment-6935992519) |
| 2 | `[claude/opus-5.5]` | new findings | SR2-1 (medium): a failed write left a partial `0600` file with the value until the sweep; a short write was possible → **fixed** (write loop + unlink on failure, negative test). No other finding | [PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/535#issuecomment-6936009709) |

The operator's cap is two rounds, so the loop ends after round 2 even though round 2 found
something. The critic round that follows reviews the code after this fix.
