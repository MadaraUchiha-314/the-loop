---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#517"
---

# Final validation: hand a conversation to the-loop from any surface, at any stage

> The `evidence` node's proof, summarised from `testing-plan.md`'s Verification results and
> mapped onto the acceptance criteria. Raw output sits beside this file.

## Final validation evidence

| Acceptance criterion | How it was proved | Where |
|----------------------|-------------------|-------|
| R1: hand off from anywhere | The skill and `/the-loop:handoff` ship in the wheel and sdist, and the skill refuses to run in a daemon session (R2.10). Running the skill outside Claude Code is the owner's check at `human-approval`, per their call on T11 | [`skills/handoff-to-the-loop/SKILL.md`](../../../../skills/handoff-to-the-loop/SKILL.md); [testing-plan.md](../testing-plan.md#verification-results) |
| R2: the interview | Specified in the skill. **Not run live:** there is no `AskUserQuestion` in a daemon session. Deferred to the owner's check at `human-approval` ([B](https://github.com/MadaraUchiha-314/the-loop/issues/517#issuecomment-6334963165)) | [manual-handoff.md](manual-handoff.md) |
| R3: ticket creation, including a Jira copy with issue type, parent and mirror label (R3.4, R3.5) | Unit tests for `create_issue` (issue type and parent), the route and the MCP tool; a scenario test for the Jira copy; a Jira item with the mirror label is refused at arming (`arm.refused reason=mirror`) | [tests.md](tests.md); [scenarios.md](scenarios.md) |
| R4: commit at handoff | Specified in the skill's posting order (spec branch and draft PR before the record); arming checks out the record's branch (scenario, R6.2) | [scenarios.md](scenarios.md) |
| R5: the handoff record (format, parts under 65,536 characters, `note`) | Parse and render round trips, parts rejoined byte-equal, snapshots for each carrier, the `note` scenario; a real GitHub round trip on scratch issue #520 with a record and one part, byte-equal and hashes verified | [tests.md](tests.md); [manual-handoff.md](manual-handoff.md) |
| R6: the poller starts at the right step | A walk scenario for each row of the R6 table, start to the first approval gate; a checklist snapshot for a requirements-settled handoff; the no-handoff checklist is byte-identical | [scenarios.md](scenarios.md); [tests.md](tests.md) |
| R7: the `import-handoff` step (no-handoff skip, demotion, artifact URL) | The no-handoff walk is unchanged (`via: no-handoff`); a missing Security considerations section demotes to `requirements-definition`; no verified file means un-skipping from `brainstorming`; the claude.ai artifact URL is adopted at start (critic round 1) | [scenarios.md](scenarios.md); [critic-review.md](critic-review.md) |
| R8: approvals | An artifact approved in chat is locked with `approvedVia: handoff <url>`, except the furthest one; the lock is recognised by its recorded sha256 (self-review round 2); the skips are signed by whoever replied `the-loop execute` | [self-review.md](self-review.md); [scenarios.md](scenarios.md) |
| Security considerations (abuse cases 1–7) | Negative tests: an unauthorized or empty author, a pasted marker, a forged lock line, a symlinked file or spec folder, a bad branch name, a mirror copy. The security review found no high- or medium-confidence findings | [security-review.md](security-review.md); [tests.md](tests.md) |
| Whole suite | `make check`: lint, markdownlint, format, pyright and validate pass; 321 issue-517 tests pass; the 22 failures are environment-only and also fail on `main` locally; CI on PR #518 is green | [tests.md](tests.md) |
