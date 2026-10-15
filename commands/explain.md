---
description: Write and publish the explainer for a work item — the spec explainer + spec quiz at `spec-explainer`, the explainer of the change + code quiz at `code-explainer`.
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | docs/specs/issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# the-loop: explain `$ARGUMENTS`

Write the page that teaches this work item, and the quiz that comes with it (issue-488).
The page is a slice of `/the-loop:work-on`, run at two nodes of the outer loop.

**Read `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/reference/explainer.md` first.** It has the
depth ladder, the section contract, the quiz rules and the publishing table. This command
is only the procedure.

## Steps

1. **Locate the work item.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `work-item-state.json`'s `currentNode`:
   - `spec-explainer`: write the **spec explainer** and the **spec quiz**. The subject is
     the approved `requirements.md` (or `bugfix.md`), `design.md` and `testing-plan.md`.
     Include no code-level detail unless `design.md` itself has it.
   - `code-explainer`: write the **explainer of the change** and the **code quiz**.
     Explore the diff against the default branch, grounded in the spec. Read the code
     around each hunk, and the tests, config and data models the change relies on. The
     quiz mixes code-level and spec-level questions.
   - Any other node: stop and say so. This command runs only at those two.

2. **Classify the depth** (`micro` / `standard` / `deep`) by the mental-model delta,
   never by line count, and write the page from
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/explainer.html`:
   - **The contract:** Background, Intuition, Code (by execution flow, `file:line`
     excerpts, Risks & limits), then Quiz.
   - **The question count:** 0, 3 or 5.
   - **Before publishing:** check every question against the quiz rules.

3. **Publish** per the reference's table:
   - a tab of the spec-chain artifact when `claudeArtifact` is true;
   - otherwise its own artifact;
   - with no artifact tool, `docs/specs/<id>/explainer/explainer.html`, redacted,
     committed and pushed.

   At `code-explainer`, update the same page and URL the spec explainer used.

4. **Write the record** from
   `${CLAUDE_PLUGIN_ROOT}/skills/the-loop/templates/evidence/`:
   - **Which record:** `spec-explainer.md` at `spec-explainer`, `explainer.md` at
     `code-explainer`.
   - **What it holds:** the depth, the **Location** (artifact URL or GitHub blob URL),
     how it was published, and the question count.
   - Commit it.

5. **Hand over:** run `the-loop graph complete <id>`. The next node posts the checkbox
   comment and waits for the author. **Never tick the box or post the attestation line
   yourself.**
