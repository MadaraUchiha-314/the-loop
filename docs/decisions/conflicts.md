# Conflict & assumption log

Append-only log of ambiguities and conflicts hit **mid-flight** during a run (distinct
from the deliberate decisions in `decisions.md`). Rule (see
`skills/the-loop/reference/collaboration.md`): resolvable with a reasonable default →
**assume and continue**; genuinely blocked → **log, escalate once, move on**. One line per
entry so an unattended run stays moving and the human gets a reviewable trail.

| Timestamp | Phase | Conflict / assumption | Status |
|-----------|-------|-----------------------|--------|
| 2026-07-01 | tasks-breakdown | Recorded 8 review-driven feature proposals as issues #3–#10 and implemented them in PR #2 per the author's explicit choice (implement all now) | resolved |
| 2026-09-19 | requirements-definition | issue-389: the owner said "go ahead with requirements" on PR #390 with four brainstorm questions unanswered. Assumed: a thread snapshot is copied verbatim (Q4); shortcuts and the modal ride in this work item (Q6); an unlisted room member's mention is dropped in silence, as a stranger's is (Q7); the mention rule reaches typed gate answers and kickoffs, button presses unchanged (Q8). Each is stated in requirements.md for the requirements-approval gate | assumed |
| 2026-09-19 | requirements-definition | issue-389: Slack does not deliver `app_mention` in a direct message with the app. Assumed: the DM with the bot is addressed by construction and keeps `message.im` as its input; the mention rule governs channels (public, private, group DM) | assumed |

_Status: `assumed` (default taken, continuing) · `escalated` (raised once, moved on) ·
`resolved` (later settled)._
