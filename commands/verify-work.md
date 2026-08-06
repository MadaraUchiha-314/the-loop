---
description: Execute a work item's testing-plan.md after implementation — run the planned activities, record results, commit the evidence (verification phase).
argument-hint: "<ticket-id | spec-dir> (e.g. 42 | issue-42 | docs/specs/issue-42)"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Task
---

# the-loop: verify-work `$ARGUMENTS`

**Prove** the work item: execute the locked `testing-plan.md` and turn it into a record —
the `verification` node, between implementation and the review chain. A slice of
`/the-loop:work-on` (step 3 of `/the-loop:execute-tasks`); `work-on` remains the superset.

**Read the `the-loop` skill and `reference/testing.md` first.** Load
`.the-loop/harness-config.yaml` and every doc registered in `customInstructions.docs` —
the environment the plan references is usually described there.

## Steps

1. **Locate & load.** Resolve `$ARGUMENTS` to `docs/specs/<id>/` and read
   `testing-plan.md`, `tasks.md` and `execution-log.md`. Every task should be ticked; if
   the DAG is unfinished, say so and stop — verification proves finished work.

2. **Bring up the environment** declared in the plan's **Verification environment**:
   repositories, services, fixtures, using the **project's own** commands. Credentials
   resolve from the referenced env vars / secret store — the plan never contains values.
   **If bring-up fails:** record it under **Verification results**, leave the dependent
   activities unticked, and escalate. Do not pass the gate on an environment that never
   came up.

3. **Run each planned activity** in the plan's **Verification activities** checklist.
   Tick a line (`- [ ]` → `- [x]`) **only** once it has actually run and its evidence is
   recorded. An activity that cannot be executed stays unticked: write why under
   **Verification results**, then either replan the matrix (with the reason) or escalate.
   Silently dropping a planned activity is not permitted.

4. **Capture the evidence** under `docs/specs/<id>/evidence/` and commit it — test output,
   screenshots, recordings, reports. A link to a CI run that expires or to a local path is
   not evidence. For a user-facing surface: screenshots of each verified state, plus an
   **animated capture (GIF or equivalent) when the behaviour under test is a *flow***
   rather than a state. **Redact first** — that directory is as public as the repository,
   so strip tokens, cookies, personal data and internal hostnames; a capture that cannot
   be redacted is not committed, and the results row says so. A secret that reaches a
   commit is rotated, not merely edited out.

5. **Record the results.** Fill the plan's **Verification results** table: per activity,
   the exact command or manual procedure, the outcome, and a link to the committed
   evidence. When the change adds or alters integration behaviour, run
   `the-loop scenarios --format markdown` for the reviewer briefing and reference it here.

6. **Advance the phase.** Set the ticket label to `<phaseLabelPrefix>verification` while
   running, mirror `phase: verification` in the execution log, and tell the graph when the
   node's work is done: `the-loop graph complete <id>`.

7. **Next step:** the review chain — `/the-loop:execute-tasks <id>` step 4 onward
   (self/critic review, security review, evidence, capability docs, reviewer briefing),
   then `/the-loop:finish-tasks <id>`.
