# Reviewing reference — the self/critic review loop

`reviews.selfReviewCount` / `reviews.criticReviewCount` say *how many* rounds and
`reviews.critics[]` *which* critic; this file defines the **procedure** those counts
drive, so review depth is reproducible and the loop converges. Tool-agnostic: "review
comments" and "threads" map to GitHub reviews or Jira comments equally.

## Rounds and attribution

- A **round** is one reviewer's full pass that posts its findings as review comments.
- Each finding carries a short **attribution prefix** so mixed-harness findings are
  distinguishable: `[<harness>/<model>]` (e.g. `[claude/opus-4.8]`, `[cursor/gpt-5.5]`).
  Self-review uses the running harness/model; critic rounds use the configured
  `reviews.critics[]` entry (`harness`/`model`/optional `command`).
- Run `selfReviewCount` self rounds, then `criticReviewCount` critic rounds — these are
  **caps**, not quotas.

## Reply-first-then-fix protocol

For every finding, in order:

1. **Reply first.** Before changing any code, reply to the finding with one of:
   **will-fix**, **won't-fix-because …**, or **needs-clarification**. This records the
   decision (paper trail) and prevents silent churn.
2. **Fix one finding per commit.** Make the change for a will-fix finding as its own
   commit referencing the thread, then **resolve that thread**. One finding ↔ one commit
   ↔ one resolved thread keeps history reviewable.
3. **Won't-fix / needs-clarification** findings are left unresolved with the reason
   recorded; needs-clarification escalates to the human via the paper trail.

## Convergence — stop and escalate signals

- **Stop early on zero new findings.** If a round surfaces **no new actionable finding**,
  the loop is converged — stop even if the count cap is not reached
  (`reviews.stopOnNoNewFindings`, default true).
- **Hard cap.** Never exceed `selfReviewCount` / `criticReviewCount` rounds.
- **Diminishing-returns guard.** If two consecutive rounds surface the **same** finding
  (it recurs rather than getting resolved), stop looping and **escalate to the human**
  (`reviews.escalateOnRepeatFinding`, default true) — the loop is stuck, not improving.

## The security review round (`security.review`)

After the self/critic rounds converge, one more recorded round runs with a **security
lens** — a distinct, required gate item, not an extra critic pass (`security.md` has
the full procedure and checklist):

- Mechanism per `security.review.mechanism`: the harness's built-in security-review
  skill when available (`auto`/`skill`), else the-loop's checklist (`checklist`).
- Findings follow the **same protocol above** (reply-first, one finding per commit),
  with one tightening: a security finding is never silently dismissed — won't-fix
  requires a recorded justification, and an unresolved security finding blocks
  completion regardless of risk tier.
- An effective risk tier ≥ `security.review.humanSignOffMinTier` needs a named human
  sign-off on this round (paper trail); lower tiers run it autonomously.

## Record every round

Append each round to the execution log's **review table**: round #, type
(self/critic/**security**), reviewer (`<harness>/<model>` or the mechanism), outcome
(new findings / zero / escalated), and a link. This is the evidence that the
configured review counts — and the security gate — were actually run.
