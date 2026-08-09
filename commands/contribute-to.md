---
description: Join an EXISTING, in-progress work item (issue or PR) as a contributor — walk the contribution loop toward a human-stated goal and success criteria, without the full spec chain.
argument-hint: "<ticket-id> (e.g. 12 | issue-12 — an item that already has work in progress)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: contribute-to `$ARGUMENTS`

Make a **scoped intervention** in a work item the-loop does not own: an issue or pull
request that already exists, is already in progress, and may have been produced by a
bespoke process — do **not** assume any spec-chain artifact exists. The process is the
**contribution loop** (`pdlc-contribution-loop`), the third shipped graph; ask
`the-loop check <id>` / `the-loop graph show` where the item stands rather than
re-deriving it. Load `.the-loop/harness-config.yaml` first and honor every custom
instruction doc it registers, exactly as `work-on` does. **If the file does not
exist, the repository has not adopted the-loop**: run on the defaults (specs at
`docs/specs/`), treat the spec tree as working state only — the runtime excludes it
from git; never commit or push it, the contribution PR carries only the
intervention — and let the `publish-artifact` hook post the plan and verification
results to the thread, the review surface such a repository offers.

**Before acting, read the `the-loop` skill and its reference files** — this command
follows all the same rules (paper trail, self-marked comments, reviews, context
management); only the node set differs.

## What is different from `work-on`

1. **The goal is the human's, and it is mandatory.** The loop's first node,
   `goal-definition`, is `required: true`: it waits until an authorized user has
   stated, in one comment:

   ```
   Goal: <what the-loop should accomplish here>
   Success criteria:
   - [ ] <how we will know it worked>
   ```

   Never invent, infer, or "helpfully complete" a goal — if none is stated, the gate
   posts the format once and waits. The frozen criteria are the definition of done.

2. **One artifact, not four.** The planning nodes (`context-intake`, `scoped-plan`)
   author a single `<workflow.specDir>/<id>/contribution.md` — goal, success criteria,
   context, approach, verification plan — from the bundled `contribution.md` template.
   Requirements-and-design thinking still happens; it just lands in sections, not
   files. Lock it (`status: approved`) at `scoped-plan`, iterate it with the human at
   `plan-approval`.

3. **Do not bloat the existing item.** Post only what the gates require (goal request,
   phase-selection checklist, confirmations, review requests). Work products live in
   the repo's spec directory, commits and PRs — not as walls of comments on someone
   else's thread. Every comment carries the self-authored marker.

4. **Done means the criteria are met.** At `implementation`, work strictly toward the
   frozen criteria; tick each `- [ ]` in `contribution.md` only when it is actually
   met. `verification` blocks until all boxes are ticked and the
   `Verification results` section records how each was proved (in the execution log
   instead, when the planning phases were declared away).

5. **The phase choice is the human's.** `phase-selection` runs exactly as in the outer
   loop: post the checklist of this loop's skippable phases, wait for an authorized
   `the-loop execute`. A small contained instruction may keep only
   implementation + verification; that is the requester's call, never yours.

## Walk

`goal-definition → phase-selection → context-intake → scoped-plan → plan-approval →
implementation → verification → self-review → critic-review → security-review →
reviewer-briefing → human-approval → complete` — claim each finished node with
`the-loop graph complete <id>`. Reviews record into the shared
`execution-log.md` sections, exactly as every loop does.
