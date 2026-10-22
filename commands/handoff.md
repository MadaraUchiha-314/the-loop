---
description: Hand this conversation to the-loop — draft the spec artifacts it supports, interview, file the GitHub issue (plus an optional Jira copy) with a handoff record, and start the loop at the stage reached.
argument-hint: "[short-title] (optional, e.g. \"export-to-csv\")"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, AskUserQuestion
---

# the-loop: handoff `$ARGUMENTS`

Hand the conversation so far to the-loop, so the work item starts at the stage the
developer reached instead of at the first phase.

**Read and follow the `handoff` skill**
(`${CLAUDE_PLUGIN_ROOT}/skills/handoff-to-the-loop/SKILL.md`; the same path in Cursor). It is the
whole procedure: draft, pick the transport, the four-question interview, the
confirmation summary, then post the issue, the Jira copy, the spec branch and draft PR,
the spec-chain artifact, the handoff record and the next step, in that order.

`$ARGUMENTS`, when given, is the slug for `docs/specs/draft-<slug>/` and the branch
`the-loop/<id>-<slug>`; otherwise derive one from the conversation.

Refuse in a daemon-spawned (`work-item` interaction mode) session: a handoff needs the
developer present. Post nothing before the developer confirms the summary.
