---
type: requirements
phase: requirements-definition
workItem: issue-48
status: draft
approvedBy: []
collaborators: [product-manager, architect, engineer]
overrides: {}
---

# Requirements: manage the context window efficiently

> Phase 1 of 3 (requirements → design → tasks). Ticket:
> [issue #48](https://github.com/MadaraUchiha-314/the-loop/issues/48). This phase should
> be reviewed and approved before moving to design.

## Introduction

As the-loop completes many tasks for a work item, the harness's context window grows
monotonically: spec-drafting iterations, finished-task diffs, resolved test failures and
wide exploration all stay resident, crowding out the attention the *current* task needs.
Harness vendors are explicit that this degrades output quality well before the hard
token limit, and both ship countermeasures (Claude Code's `/clear` and `/compact`,
Cursor's summarization and new-chat guidance) — but today the-loop never tells the
harness *when* to use them, so the window is managed reactively (auto-compaction firing
mid-task at an arbitrary moment) or not at all.

the-loop is unusually well positioned to manage its window deliberately: its operating
rules already externalize all durable state into checked-in artifacts (the 3-phase spec,
`tasks.md` checkmarks, the execution log, the phase label). Everything that must survive
a reset already lives on disk — the same property that powers resumability. This work
item adds a **checkpoint-then-reset context-management protocol** to the skill: clearing
at phase boundaries (as Claude Code's plan mode does between planning and execution),
compaction at task boundaries and mid-task, never resetting without a checkpoint, and a
`contextManagement` config section controlling the policy.

## Requirements

### Requirement 1 — clearing and compaction are distinguished and applied deliberately

**User story:** As a user running the-loop, I want the harness to know the difference
between clearing (fresh window, only disk state survives) and compaction (lossy
in-place summary) and which is applicable where, so that the window is managed with the
right tool instead of ad hoc.

#### Acceptance criteria (EARS)

1. The skill SHALL document the clearing-vs-compaction distinction — what each does,
   what survives, the failure modes, and where each applies — in a dedicated reference
   file the operating commands point to.
2. The guidance SHALL follow the harness vendors' published recommendations (Anthropic:
   clear between tasks, compact at natural breakpoints within one; Cursor: new chat when
   focus degrades, built-in summarization) and SHALL cite them.
3. The system SHALL treat the harness's automatic compaction as a safety net, not the
   strategy: resets happen proactively at the loop's own boundaries.
4. The system SHALL NOT clear mid-task; mid-task the only permitted reset is
   compaction, preceded by a checkpoint.

### Requirement 2 — a checkpoint always precedes a reset

**User story:** As a user, I want the loop to never lose work or intent to a context
reset, so that aggressive window management is safe by construction.

#### Acceptance criteria (EARS)

1. WHEN the loop is about to reset context (clear or compact) THEN the system SHALL
   first checkpoint: `tasks.md` checkmarks current, an `execution-log.md` entry appended
   with what was done and a concrete next step, the phase label in sync, and
   work-in-progress committed or explicitly noted.
2. WHEN a fresh window resumes after a clear THEN the system SHALL re-enter through the
   artifacts — the execution log's latest entry first, then only the spec files the next
   unit of work needs.
3. The execution-log template SHALL state that the log doubles as the resume anchor for
   context resets.

### Requirement 3 — phase boundaries start clean (plan-mode style)

**User story:** As a user, I want implementation to start on a fresh window once the
spec is locked, so that the spec-drafting deliberation does not pollute execution — the
approved files are the contract.

#### Acceptance criteria (EARS)

1. WHEN the phase advances across a locked artifact — most importantly
   tasks-breakdown → implementation — THEN the system SHALL apply the configured
   phase-boundary reset (`contextManagement.phaseBoundary`, default `clear`) and derive
   the next phase's work from the checked-in artifacts, not the conversation.
2. WHERE the harness cannot reset its own window (headless / CLI-spawned sessions) the
   system SHALL achieve the same by checkpointing and preferring to end the session at
   the boundary, letting resumability start the next session fresh.

### Requirement 4 — task boundaries are managed after every completed task

**User story:** As a user, I want the window managed after each task in `tasks.md`
completes, so that a long DAG does not accumulate every finished task's noise.

#### Acceptance criteria (EARS)

1. WHEN a task in the DAG completes THEN the system SHALL checkpoint and then apply the
   configured task-boundary reset (`contextManagement.taskBoundary`, default `compact`;
   `clear` and `off` selectable).
2. WHEN compacting with a steerable harness THEN the system SHALL direct the compaction
   at what to keep (design constraints, discovered conventions) and what to drop
   (resolved errors, superseded attempts, finished-task output).
3. The system SHOULD avoid ingesting noise in the first place: high-volume exploration,
   log digging and verbose test analysis run in subagents / isolated sessions that
   return conclusions, not transcripts.

### Requirement 5 — the policy is configurable and harness-portable

**User story:** As a user, I want the context policy in `.the-loop/config.yaml` like
every other loop behaviour, so that I can tune it per project (or per work item via
front-matter overrides) and the same protocol works on Claude Code, Cursor and headless
sessions.

#### Acceptance criteria (EARS)

1. The config schema SHALL gain a `contextManagement` section — `enabled`,
   `phaseBoundary` (`clear|compact|off`, default `clear`), `taskBoundary`
   (`clear|compact|off`, default `compact`), `midTask` (`compact|off`, default
   `compact`) — with defaults applied silently during onboarding (advanced group).
2. The skill reference SHALL map the protocol's reset verbs to each harness's
   mechanics (Claude Code `/clear` / `/compact` / subagents; Cursor new chat /
   summarization / `@Past Chats`; headless session-per-boundary).
3. WHEN `contextManagement.enabled` is `false` THEN the system SHALL leave window
   management entirely to the harness's own automatics.

## Out of scope

- CLI code or hooks that *force* a reset — the protocol is instruction-level (skill,
  commands, config), consistent with how the rest of the loop's process rules ship.
  Hook-enforced guarantees remain the open question tracked in
  `reference/workflow.md` § predictability.
- A retrieval/RAG store over past conversations — the checked-in artifacts are the
  loop's memory; anything more is speculative (minimalism ladder).
- Cross-work-item context policy (parallel sessions each carry one work item already).
