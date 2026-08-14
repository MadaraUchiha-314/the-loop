---
description: Do an ad-hoc, tactical task on a work item with NO PDLC process — no spec chain, no phase gates, no review chain. Work, ask follow-ups on the thread, continue until the requester says it is done.
argument-hint: "<ticket-id> (e.g. 12 | issue-12 — the work item that carries the instruction)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: do-task `$ARGUMENTS`

Do the thing the work item asks for, and nothing else. The process is the **ad-hoc
loop** (`pdlc-adhoc-loop`), the fourth shipped graph and the smallest one: three nodes,
no artifacts, no gates on files. Ask `the-loop check <id>` / `the-loop graph show` where
the item stands rather than re-deriving it. Load `.the-loop/harness-config.yaml` first
and honor every custom instruction doc it registers — that config is what tells you this
project's test, lint and type-check commands, and running them is the one piece of rigor
this loop keeps.

**Before acting, read the `the-loop` skill** — the rules that are *not* about phases still
apply in full: the paper trail, the self-authored marker on every comment you post
(`reference/collaboration.md` § loop prevention), context management, and the minimalism
ladder. Only the process is absent.

## What this loop is

The requester armed this item with `the-loop do` instead of `the-loop start`. That is an
authorized human's explicit, recorded declaration that **this work item runs without the
PDLC** — it is frozen in `graph-state.json`'s `loop` field and the arming comment stands
on the thread. Honor it: the fastest correct path from the instruction to a working
change is the whole job.

```text
work  ⇄  review  →  complete
```

- **`work`** — do it. Report back on the thread when you have something.
- **`review`** — the requester replies. Anything that is not "done" is more work, and
  routes straight back to `work`. Silence leaves the gate open.
- **`complete`** — the requester said it is finished. Closing the issue ends it too.

## What is different from `work-on` and `contribute-to`

1. **The work item is the instruction.** There is no `goal-definition` gate and no
   `Goal:`/`Success criteria:` format to wait for — unlike `contribute-to`, which cannot
   start without one. Read the ticket title, body and thread; if the ask is genuinely
   ambiguous, **ask on the thread and keep working on the unambiguous part**, rather than
   stopping with nothing delivered.

2. **Author no spec chain.** No `requirements.md`, no `design.md`, no `testing-plan.md`,
   no `tasks.md`, no `contribution.md`, no `evidence/` tree, no capability-doc row — none
   of these is gated here and creating one anyway is exactly the bloat this loop exists to
   avoid. The only thing the-loop writes into the repository for an ad-hoc item is
   `<workflow.specDir>/<id>/graph-state.json`, a cache. If the task turns out to deserve
   the full PDLC, say so on the thread and propose a *new* work item — do not quietly
   start a spec chain inside this one.

3. **There is no phase selection, because there are no phases.** Do not post a
   phase-selection checklist and do not wait for `the-loop execute`. The phase labels the
   loop does apply are the ordinary ones (`loop:implementation`, then `loop:complete`),
   kept in sync by the graph.

4. **There is no review chain.** No self-review rounds, no critic rounds, no
   security-review gate, no reviewer briefing. This is a real reduction in guardrails and
   it is the requester's declared call. What does *not* go away: you still run the
   project's own lint, type-check and tests before reporting back, and you still say
   plainly on the thread if something you touched looks risky. "No review chain ran" is
   visible in the record; "I noticed a problem and said nothing" is not.

5. **Done is the requester's word, not your judgement.** Do not mark the item complete
   because the change looks finished to you. Report what you did, then wait. A reply
   asking for more is the normal case and costs nothing — the gate routes it back to
   `work` with the new instruction attached.

## Walk

`work → review → complete` — claim each finished node with
`the-loop graph complete <id>`, exactly as every loop does. `review` loops back to `work`
on `more-work` as many times as the requester needs. The terminal `cleanup` node releases
the item's local resources when the work is over, and a closed issue (or a merged/closed
PR) ends the session on the shared close path.
