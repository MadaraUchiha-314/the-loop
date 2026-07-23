# Context-window management — checkpoint, then reset

How the-loop keeps the harness's context window healthy across a work item's lifetime.
A work item spans many tasks and phases; left alone, the window grows monotonically —
stale exploration, finished-task diffs and old test output crowd out the attention the
current task needs, and performance degrades well before the hard limit. the-loop
manages the window **deliberately**, and it can afford to manage it aggressively because
everything that matters is already externalized in checked-in artifacts.

## Clearing vs. compaction — two different tools

| | **Clearing** | **Compaction** |
|---|---|---|
| What happens | The window is emptied; the next turn starts fresh | The history is summarized in place; the summary replaces the raw transcript |
| What survives | Nothing implicit — only what is on disk (specs, code, logs) | A lossy summary chosen at compaction time |
| Failure mode | Losing un-checkpointed intent | Summary silently drops a detail the next step needed |
| Right for | **Boundaries** — the finished unit's context is noise for the next unit | **Continuations** — the same unit of work goes on and recent history still matters |
| Cost | Re-reading the artifacts that matter (cheap: they are small and current) | Summarization is imperfect; repeated compaction compounds the loss |

The rule of thumb (Anthropic's guidance for Claude Code says the same: `/clear`
between tasks, `/compact` to lighten context while continuing one): **clear at
boundaries, compact in the middle**. Never clear mid-task — an unfinished task has
un-checkpointed intent by definition. And never rely on the harness's *automatic*
compaction as the strategy: it fires at an arbitrary moment (usually deep inside a
task, when the window is nearly full) with no knowledge of the loop's checkpoints.
Reset proactively at the loop's own boundaries so auto-compaction stays a safety net,
not the plan.

## Why the-loop can reset aggressively: the durable ledger

Clearing is only as safe as what survives it. the-loop's operating rules already
externalize all durable state into checked-in artifacts — that is what makes resets
cheap:

- `requirements.md` / `design.md` / `tasks.md` — the locked contract for the work.
  Nothing in the conversation supersedes them (edits go to the files, single source of
  truth), so re-reading them after a clear loses nothing.
- `tasks.md` checkmarks — exactly which tasks are done vs. outstanding.
- `docs/specs/<id>/execution-log.md` — what was done, what was checked, **what is
  next**, and any blockers. This is the resume anchor: a fresh window reads it first.
- The phase label on the ticket — where in the state machine the work item is.
- Code, tests and commits — the work itself, on disk and in git.

This is the same property that powers resumability (`reference/workflow.md`): a fresh
session can pick up a work item from the artifacts alone. Context management is
resumability applied *within* a session, on purpose, at moments the loop chooses.

## The protocol: checkpoint, then reset

**Never reset (clear or compact) without checkpointing first.** A checkpoint means all
of:

1. `tasks.md` checkmarks reflect reality (`- [ ]` → `- [x]` for the finished task);
2. an `execution-log.md` entry is appended — what was done, the test command and its
   result, and a concrete **Next:** the next window can act on without archaeology;
3. the phase label / front-matter are in sync if the phase moved;
4. work-in-progress is committed (or explicitly noted in the log entry if not).

After the checkpoint, apply the reset the boundary calls for (below). After a clear,
re-enter through the artifacts: read `execution-log.md` (the **Next:** of the last
entry), then only the spec files the next unit of work actually needs — `tasks.md`
names its requirements, so late tasks rarely need the full `requirements.md` re-read.

## Where each technique applies

Configured under `contextManagement` in `.the-loop/config.yaml`; defaults below.

- **Phase boundaries → clear** (`contextManagement.phaseBoundary`, default `clear`).
  The big one is **tasks-breakdown → implementation**: once the 3-phase spec is locked,
  the drafting/iteration history is pure noise for implementation — the approved files
  *are* the contract. Start implementation on a fresh window that reads
  `requirements.md`, `design.md`, `tasks.md` and the execution log from disk. This is
  the same move Claude Code's plan mode makes (plan in one context, execute from the
  approved plan, not the deliberation), and Cursor's "new chat per task" guidance.
  The earlier spec→spec transitions (requirements → design → tasks) benefit too: each
  artifact is derived from the locked file, not from the chat that produced it.
- **Task boundaries → compact** (`contextManagement.taskBoundary`, default `compact`).
  After each completed task in the DAG: checkpoint, then compact away the finished
  task's exploration, diffs and test output while keeping cross-task working knowledge
  (codebase layout, conventions discovered, the design's shape). Set it to `clear` for
  long DAGs or low-context harnesses — the execution log makes that affordable — or
  `off` to defer to mid-task compaction only. When compacting with a steerable harness,
  direct it: keep the current design constraints and discovered conventions; drop
  resolved errors and superseded attempts.
- **Mid-task → compact only** (`contextManagement.midTask`, default `compact`). If the
  window nears its limit inside a task, write an interim checkpoint (log entry with
  current state + next step), then compact. **Never clear mid-task.**
- **High-volume work → isolate it instead.** The cheapest context management is not
  ingesting noise in the first place: run wide exploration, log digging and verbose
  test analysis in **subagents** (Claude Code `Task` tool) that return conclusions, not
  transcripts. Critic reviews already run in a different harness/model
  (`reference/reviewing.md`) and cost the main window nothing.

## Per-harness mechanics

The protocol is harness-portable; only the reset verb differs:

| Harness / mode | Clear | Compact | Isolation |
|---|---|---|---|
| Claude Code (interactive) | `/clear` | `/compact <focus instructions>` | subagents via `Task` |
| Cursor | new chat (`@Past Chats` to recover selectively) | built-in summarization of older messages | scoped `@` context |
| Headless / CLI-spawned sessions (webhook, poller, tmux runner) | end the session at the boundary; the next session starts fresh and resumes from the checkpoint | harness auto-compaction (safety net) | spawn-per-task |

An agent that cannot invoke a reset on itself (headless runs) still follows the
protocol: checkpoint at every boundary and prefer ending the session at a phase
boundary over grinding on with a bloated window — the-loop's resumability guarantees
the next session continues exactly where the log says.

## Sources this guidance follows

- Anthropic, [Claude Code best practices](https://www.anthropic.com/engineering/claude-code-best-practices)
  — `/clear` frequently between tasks; `/compact` at natural breakpoints.
- Anthropic, [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
  — context as a finite attention budget; compaction, structured note-taking (external
  memory) and sub-agent architectures as the three levers. the-loop's execution log is
  the "structured note-taking" leg, done as a checked-in artifact.
- Cursor, [Summarization](https://cursor.com/docs/agent/chat/summarization) and
  [agent best practices](https://cursor.com/blog/agent-best-practices) — automatic
  summarization of long chats; start a new conversation when focus degrades and pull
  history back selectively with `@Past Chats`.
