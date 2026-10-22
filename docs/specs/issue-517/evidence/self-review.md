---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#517"
---

# Self-review: hand a conversation to the-loop from any surface, at any stage

> The `self-review` node's proof. The policy (`the-loop critic policy`) is
> `selfReviewCount: 2`, so this stops at two rounds. Both rounds read the whole diff
> against the approved spec and confirmed every suspected defect with a probe before
> fixing it. No finding repeated across rounds: round 2's two fixes correct round 1's own
> fixes, not round 1's findings.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (Claude, `claude-opus-5-5`) | new findings | 7 found. Fixed in `22eab7b2`: (1) empty-author record admitted; (2) the hook's own lock read as tampering on re-run, and re-import overwrote it; (3) symlinked carried file followed; (4) the `is_self` callback trusted a pasted marker; (5) a quoted marker made a record unpostable. Accepted: (6) the spec-artifact sha256 is unchecked, because the per-file hashes protect content; (7) a failed comment listing loses the handoff, which is fail-closed by design | [PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/518#issuecomment-6335199228) |
| 2 | self (Claude, `claude-opus-5-5`) | new findings | 3 found. Fixed in `2b4b8c1d`: (1) the lock was recognised by its `approvedVia` line, which anyone can write; it is now recognised by the recorded sha256 of the bytes the hook wrote; (2) a symlinked `docs/specs` escaped containment, which is now checked against the repository root. Accepted: (3) `handoff note` copies state fields, but records are read only before a walk starts | [PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/518#issuecomment-6335341995) |
