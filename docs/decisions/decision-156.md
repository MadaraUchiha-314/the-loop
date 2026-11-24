<!-- Written per the `the-loop:writing` skill. -->

# Decision 156: the file that describes today's system is `current-state.md`, not `context.md`

- **Status:** accepted
- **Date:** 2026-11-24
- **Deciders:** MadaraUchiha-314 (the approvals at the brainstorm, requirements and
  design gates), the-loop (the name)
- **Work item:** [issue-553](https://github.com/MadaraUchiha-314/the-loop/issues/553)
  (PR #554)
- **Spec:** [`docs/specs/issue-553/`](../specs/issue-553/)
- **Related:** [decision-133](decision-133.md) (`context.md`, the channel record)

## The short version

The opt-in `context-gathering` phase writes `docs/specs/<id>/current-state.md`. The file
is not named `context.md`, because that name is taken by a file with the opposite rules.

| | `current-state.md` | `context.md` |
|---|---|---|
| Holds | how the affected part of the system works today | what a channel told the loop |
| Lifecycle | written once, approved, locked | appended to for the whole work item |
| Gate | `context-approval` | none |

## Context

Issue-553 adds a phase that records how the affected part of the system works today,
before any spec is written. The ticket calls the phase *context gathering*, so
`context.md` was the first name for its file.

That name already exists. `docs/specs/<id>/context.md` is the append-only record of
what a channel told the loop (issue-389, [decision-133](decision-133.md)). It has no
phase and no gate, and the session appends to it for the whole work item. The new file
is written once, approved by its author and locked. `reference/context.md` in the skill
is a third meaning: the rules for the context window.

## Decision

1. **The file is `current-state.md`.** The name says what the file holds: the state of
   the system now, not a plan.
2. **`context.md` keeps its issue-389 meaning** and is not changed.
3. **The phase, the label and the nodes keep the ticket's words**: `context-gathering`,
   `loop:context-gathering` and `context-approval`. The command is
   `/the-loop:gather-context`.
4. **One place states the two files against each other**: the `the-loop` skill,
   § `current-state.md` is not `context.md`. Other documents say it in a clause, or link
   there.

## Consequences

- **An instruction that names a file is unambiguous.** "Read `current-state.md` first"
  and "append to `context.md`" cannot be confused.
- **The phase name and the file name differ.** A reader who knows the phase as
  *context gathering* has to learn that its file is `current-state.md`. The command,
  the template and the skill each say so.
- **The word "context" still has three uses** in the skill: the phase, the channel
  record and the context window. The skill's section names all three.
- **The handoff's closed list of file names gains `current-state.md`**, first in chain
  order. `context.md` is still not a carried file.
- **Nothing is renamed and nothing is migrated.** The cost is that the file does not
  carry the name the ticket asked for, and that two files now hold kinds of context.

## Alternatives considered

- **Share `context.md`**: one file with a gated part and an append-only part.
  Rejected: the gate writes `status: approved` into a file that the channel rule then
  keeps appending to, so "approved" stops meaning anything.
- **Give the new file the name `context.md` and move the channel record to
  `channel-context.md`.** This is the name the ticket asked for. Rejected: it renames
  the record across the skill, two reference files, a template, a prompt, the code, the
  Slack guide and decision-133, and a consuming repository that already has a channel
  `context.md` would need a migration.
