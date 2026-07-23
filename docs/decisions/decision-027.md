# Decision 027: Checkpoint-then-reset context management (clear at phase boundaries, compact at task boundaries)

- **Status:** accepted
- **Date:** 2026-07-23
- **Deciders:** MadaraUchiha-314 + harness
- **Work item:** issue-48

## Context

A work item's context window grows monotonically across spec iteration and a long task
DAG, degrading harness output well before the token limit. Harness vendors ship the
primitives (Claude Code `/clear` and `/compact`, Cursor summarization / new chats) and
publish guidance — clear between tasks, compact within one — but the-loop never said
when to use them, so windows were managed reactively by auto-compaction firing at
arbitrary mid-task moments. Meanwhile the loop's own rules already externalize all
durable state (specs, `tasks.md` checkmarks, execution log, phase label): everything a
reset must survive is on disk, which is precisely Anthropic's "structured note-taking /
external memory" lever.

## Decision

Adopt an instruction-level **checkpoint-then-reset protocol**, configured by a new
`contextManagement` config section and defined in the skill's `reference/context.md`:

- **Never reset without a checkpoint** (checkmarks + execution-log entry with a
  concrete next step + phase label in sync + WIP committed or noted).
- **Phase boundaries clear** (default) — implementation starts on a fresh window that
  re-reads the locked spec from disk, as Claude Code's plan mode separates planning
  from execution.
- **Task boundaries compact** (default; `clear`/`off` selectable) — after each
  completed DAG task, drop that task's noise, keep cross-task working knowledge.
- **Mid-task, compact only — never clear**; auto-compaction is a safety net, not the
  strategy. Prefer isolating high-volume exploration in subagents over ingesting it.
- **Headless sessions** follow the same protocol by checkpointing and ending the
  session at boundaries — resumability starts the next session fresh.

## Consequences

- Long work items stay sharp: each task and phase runs against a window holding its
  contract, not the history of everything before it.
- Aggressive resets are safe by construction — the artifacts, not the conversation,
  are the single source of truth (this was already the rule; the protocol banks on it).
- The execution log gains a second job (resume anchor for resets), making stale
  checkpoint discipline more costly — the checkpoint-first invariant is stated at every
  entry point to compensate.
- Nothing is enforced in code; a harness can ignore the instructions. Acceptable for
  now — identical to every other process rule — and covered by the open
  hooks-vs-instructions question (`reference/workflow.md` § predictability).

## Alternatives considered

- **Rely on harness auto-compaction** — fires at arbitrary mid-task moments, undirected
  and unaware of the loop's checkpoints; kept only as a safety net.
- **Always clear (session-per-task)** — maximally clean but re-derives cross-task
  working knowledge n times per DAG; offered as `taskBoundary: clear`, not the default.
- **A retrieval/RAG store over past conversations** — new moving parts to answer
  questions the checked-in artifacts already answer; fails the minimalism ladder.
- **Hook-enforced resets in code** — harness hook APIs for context control are uneven
  across Claude Code/Cursor; premature until the predictability question resolves.
