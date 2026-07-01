# Decision 013: Trigger mandatory user-education via a required PR-briefing gate

- **Status:** accepted
- **Date:** 2026-07-01
- **Deciders:** @MadaraUchiha-314 (PR #2 retro)
- **Work item:** issue-1

## Context

R10 makes educating the reviewer **mandatory** — every PR must carry a condensed,
prioritized, mermaid-illustrated briefing that says where to focus and explains the
low-level decisions. But on PR #2 the education step **never fired**: the-loop's own PR
was reviewed off a stream of per-change replies, with no PR-level briefing and no updated
PR description. The rule existed; nothing **triggered** it. This was the open
"how to enforce mandatory user-education" question (formerly R10.4), and dogfooding caught
it live.

## Decision

Make the reviewer briefing a **required item of the ready-to-ship gate**, so "request
human review" cannot happen without education having fired:

- Add `.the-loop/templates/pr-briefing.md` — the structure the briefing is produced from
  (TL;DR, where-to-focus, mermaid map, key decisions & why, evidence, open questions).
- Add `userInteraction.prSummary.required` (default true) and `templatePath`.
- The ready-to-ship gate (`reference/workflow.md`) now requires: green checks + all
  threads resolved + evidence recorded + **the briefing posted/updated in the PR**.
  `execute-tasks`, `work-on` and `collaboration.md` all state the briefing is produced
  from the template and posted **before** requesting review.

## Consequences

- Mandatory education is now **triggered by construction**, not left to the agent's
  discretion — the failure mode that happened on PR #2 cannot silently recur.
- Resolves the formerly-deferred R10.4 enforcement question.
- The gate is checkable: the briefing either exists in the PR or it does not.

## Alternatives considered

- **A Claude hook** — rejected: a hook cannot force a PR comment/description, and the
  behavior is harness-agnostic; a gate item in the workflow is the tool-neutral mechanism.
- **Leave it as a rule** — rejected: PR #2 is the proof that a rule without a trigger gets
  skipped (see `learning-007`).
