---
description: Finalize a work item after all tasks are done — cleanup (currently closing the ticket) and mark the work complete.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: finish-tasks `$ARGUMENTS`

Wrap up a work item once **all tasks are complete and reviewed**. This is the cleanup step
of the loop; the cleanup set is intentionally **extensible** (more may be added later).

**Read the `the-loop` skill and `reference/workflow.md`.** Load `.the-loop/harness-config.yaml`.

## Steps

1. **Verify done.** Resolve `$ARGUMENTS` to `docs/specs/<id>/`. Confirm **every** task in
   `tasks.md` is checked (`- [x]`), **every PR** in `evidence/pull-requests.md`'s table
   is merged or closed (a work item may be delivered by several), the required
   self/critic reviews and human review are recorded, and validated evidence has been
   presented. If anything is outstanding, stop and report what remains (point back to
   `/the-loop:execute-tasks <id>`).

2. **Mark complete.** Set the ticket phase label to `loop:complete`; the outcome and its
   evidence are already recorded where each gate left them, under `evidence/`.

3. **Post the completion summary — first, and promptly.** One comment on the ticket
   (it reaches the room through the mirror): what shipped, the evidence links, the
   accepted gaps. This is the endgame's one message a reader most wants, and it is
   **raced by the close** (issue-405 P2): when the merge's `Closes #N` has already
   closed the ticket, the daemon holds the session for `routing.tmux.finishGraceSeconds`
   (default 300 s) waiting for exactly this summary and the claim below, then ends it.
   Post the summary before anything else here; do no other work in between.

4. **Claim completion.** `the-loop graph complete <id>` — the claim that tells the
   graph, and through it the daemon, that the terminal node's work is done. The daemon
   reads it as "the session has finished" and ends the held closure at once, so the
   pane, the checkout and the record go the moment you are done rather than at the
   deadline.

5. **Cleanup (extensible):**
   - **Close the ticket(s)** for this work item (GitHub issue / Jira) **if still open**,
     referencing the merged PR(s) / evidence. A ticket a merge's `Closes #N` already
     closed is expected — say so in the summary and move on; do not reopen it. Closing
     the ticket is also what ends the work item's harness session — one of its PRs
     merging does not (see `reference/automation.md`).
   - _Future cleanup steps are added here_ (e.g. archiving branches, releasing artifacts,
     notifying channels). Keep this list the single place cleanup grows.

6. **Report** the final status and links.
