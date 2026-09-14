# Decision 127: the state file is the work item's, and the repositories it spans are the agent's to declare — once the design says what they are

- **Status:** proposed
- **Date:** 2026-09-14
- **Deciders:** the-loop (architect, engineer), asked for and corrected by @MadaraUchiha-314 on PR #366
- **Work item:** [issue-365](https://github.com/MadaraUchiha-314/the-loop/issues/365)

## Context

Two asks from the owner's review of PR #366:

> - Can we change `graph-state` to `work-item-state`, make it more generic.
> - Can we move the "repos" that are linked to the work item in `work-item-state`?

`graph-state.json` was named after its first contents — a pointer and one record per node.
It has not been only that for some time: `surface` (issue-183), `sessionPerPr`
(issue-260), the bound `session`, and `model`/`effort` (issue-358) are facts about the
**work item**, true whichever loop it walks and read by things that never touch the graph.

The second ask is the same observation from the other side.
[decision-126](decision-126.md) had just moved issue-183's `repos:` declaration out of the
retired execution log and into `tasks.md`'s front matter — still an artifact, still the
wrong shape.

**The first answer to the second ask was wrong, and the owner caught it.** It put the
declaration on the `phase-selection` checklist, reasoning from authorization: this input
decides which repositories an unattended agent opens pull requests in, and front matter is
editable by anyone who can edit the file, so it belonged on the gate where an authorized
human already answers four per-work-item questions with one signed reply. The owner's
reply:

> Repositories that a work item will span across can only be determined after the
> design.md and tasks.md is created. Before a design is created, its not evident which
> repos will be involved.

Which is decisive. `phase-selection` is the loop's **first** node. Asking there is asking
at the one moment nobody can answer, and the safe default — tick nothing — is the wrong
answer for every multi-repo work item. An authorization property was bought with a timing
property, and the timing one is load-bearing.

## Decision

**One: the file is `work-item-state.json`.** The class is `WorkItemState`, the lock is
`work-item-state.lock`, and the prose across the skill, the commands, the capability docs,
the site, the UI and the CI gate follows.

Existing files are **read** under the old name and **written** under the new one
(`WorkItemState.existing_path`, present-name-wins). A work item mid-flight keeps its
pointer with no migration step, `/the-loop:upgrade-the-loop` never deletes a file, and the
inner-loop scan globs both names — an outer gate that stopped seeing a loop started before
the rename would release on work that never finished.

**Two: `repos` is declared by the agent, through the CLI, once the task DAG exists.**

```bash
the-loop graph repos <id> --repository octo/app --repository octo/infra
the-loop graph repos <id>            # read the declaration back
the-loop graph repos <id> --clear    # declare none
```

- **Called at `tasks-breakdown`** (documented as a step of `/the-loop:create-tasks-plan`,
  with a fallback reminder in `execute-tasks`), because `design.md` and `tasks.md` are the
  first artifacts that say where the code lands.
- **The flags are the full set, not an append.** An agent that learns of a third
  repository states all three, so a declaration can be *corrected* — which an append could
  never do. `--clear` declares none; no flags prints what is declared.
- **Bounded by shape**, through `repo_state_key` — the boundary between a repository name
  and the filesystem (issue-183). It refuses `.` and `..`, which the repository-name
  grammar alone admits, and the value becomes a directory under `pr-loops/`.
- **Bounded by the instance's own `repositories`** (issue-348) when that list is set.
  Nothing routes events for an undeclared repository, so its inner loop would never start
  and `await-inner-loops` would wait forever. Refusing at declaration time, naming the set,
  is the difference between a message and a hang.
- **One bad entry declares nothing.** A partial declaration is a gate waiting on a set
  nobody chose; a half-applied correction is worse than a refused one.
- **No ticket comment.** Unlike `skip` and `force` this takes nothing away, and the
  declaration is a checked-in diff a reviewer reads in the pull request. It is recorded as
  `graph.repos_declared` in the event log.

The CLI routes through the control-plane service like every other core capability
(decision-058): `POST /api/v1/graph/repos`, authored in the OpenAPI contract first.

## Why not derive it from the sessions

The owner noted that sessions already carry a repository. They do —
`the-loop sessions link-pr`, and inner-loop state is keyed `pr-loops/<owner>__<repo>/pr-<n>/`
— but that metadata only exists **once a pull request has been opened**. The gap before
that is the entire reason the declaration exists (issue-183): a contribution that was
planned and never opened has to be distinguishable from one that was never needed. The
declaration is the *plan*; the session record is the *evidence*. Neither is derived from
the other.

## Alternatives considered

**The `phase-selection` checklist** — implemented, then reverted on the owner's review. The
authorization argument was right and the timing made it unusable: asked before the design
exists, its safe default is wrong for exactly the work items it exists to serve.

**`tasks.md` front matter** (what decision-126 shipped, for one commit). The right *moment*
— the DAG is where the repositories become knowable — and the wrong *medium*: an artifact
key is editable by anyone with write access and has no validation between writing and the
gate reading it. The verb keeps the moment and adds the boundary.

**Free text in an execute comment.** More flexible, and that is the problem: the value
becomes a path segment and a thing a gate waits on.

**Keep `GraphState` as the class name and rename only the file.** The worst of both — a
reader would meet two names for one thing, which is the state the rename exists to end.

## Consequences

- **Breaking** for anything outside the-loop that read `graph-state.json` by name. Inside
  it, nothing: the old name is still read and every reader goes through the constant.
- A new agent-facing verb, which means a new thing the agent has to be **told** about: the
  skill's multi-repo rule, `reference/workflow.md` § Several repositories, and the two
  commands that run at the moment it should be called all carry it. A verb the agent does
  not know about is a verb that does not exist.
- `phase-selection` is unchanged — no new checklist section, no widened token grammar.
- `tasks.md` loses the `repos:` key from its bundled template.
- `Runtime`'s config now carries the instance's `repositories`, so a graph-level verb can
  bound a declaration by it.
