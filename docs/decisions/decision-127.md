# Decision 127: the state file is the work item's, not the graph's — and the repositories it contributes to are a choice the gate freezes

- **Status:** proposed
- **Date:** 2026-09-14
- **Deciders:** the-loop (architect, engineer), asked for by @MadaraUchiha-314 on PR #366
- **Work item:** [issue-365](https://github.com/MadaraUchiha-314/the-loop/issues/365)

## Context

Two asks from the owner's review of PR #366, which are one observation twice:

> - Can we change `graph-state` to `work-item-state`, make it more generic.
> - Can we move the "repos" that are linked to the work item in `work-item-state`?

`graph-state.json` was named after its first contents — a pointer and one record per
node. It has not been only that for some time: `surface` (issue-183), `sessionPerPr`
(issue-260), the bound `session`, and `model`/`effort` (issue-358) are facts about the
**work item**, true whichever loop it walks and read by things that never touch the graph.
The name had become the narrowest true description of the file.

The second ask lands in the same place from the other side. [decision-126](decision-126.md)
had just moved issue-183's `repos:` declaration out of the retired execution log and into
`tasks.md`'s front matter — still an artifact, still the wrong shape for what it is.

## Decision

**One: the file is `work-item-state.json`.** The class is `WorkItemState`, the lock is
`work-item-state.lock`, and the prose across the skill, the commands, the capability docs
and the site follows.

Existing files are **read** under the old name and **written** under the new one
(`WorkItemState.existing_path`, present-name-wins). A work item mid-flight keeps its
pointer with no migration step, `/the-loop:upgrade-the-loop` never deletes a file, and the
inner-loop scan globs both names so an outer gate cannot stop seeing a loop that started
before the rename and release on work that never finished.

**Two: `repos` is a per-work-item choice, frozen by the signed reply at
`phase-selection`.** It joins `surface`, `sessionPerPr`, `model` and `effort` — the same
gate, the same authorization, the same freeze:

```text
**Which repositories will this work item raise pull requests in?** Tick any number:

- [ ] `repo-octo/app`
- [ ] `repo-octo/infra`
```

Rows come from the instance's top-level `repositories` (issue-348) — the one declaration
every ingress already reads — so a tick names a **key into what the operator declared**,
never a string the reply invents. Any number may be ticked, unlike model and effort: a
work item contributes code to as many repositories as it needs. Ticking none is **no
declaration**, exactly what an absent `repos:` key meant before, so a single-repository
work item behaves as it always has. `declared_repos` reads the state file;
`await-inner-loops` is otherwise untouched.

## Why the gate rather than an artifact

This input decides **which repositories an unattended agent opens pull requests in**. In
front matter, anyone who can edit a file can answer it — and that is the argument the owner
already made about labels in [decision-124](decision-124.md): a channel that rides GitHub's
permission model rather than the-loop's is the wrong channel for an input that reaches an
argv or a path. `phase-selection` is where an authorized human already answers four
per-work-item questions with one signed reply; this is the fifth.

Three properties follow, none of them new:

- **A closed set.** The rows are the declared repositories, so a typo cannot become a
  directory name. A ticked row naming something not offered is dropped, exactly as an
  unoffered model is.
- **Provenance.** The choice is recorded with the reply that made it, in the state file and
  in the portable session record, rather than in a file's history.
- **Frozen.** It stops being a live comment the moment the gate passes.

## Alternatives considered

**Leave `repos:` in `tasks.md`** (what decision-126 shipped). Rejected on the owner's ask
and on the argument above. It also had a real gap: a work item that declared
`tasks-breakdown` away had nowhere to put the declaration at all.

**Free text in the execute comment** (`repos: octo/app, octo/infra`). More flexible, and
that is the problem: the value becomes a path segment and a thing a gate waits on, so it
should be a key into a declared set rather than a string a comment can invent. The
enumerated rows cost one thing — a repository the instance has not declared cannot be
picked — and that is the same bound every other ingress already enforces.

**Keep `GraphState` as the class name and rename only the file.** Rejected as the worst of
both: a reader would meet two names for one thing, which is the state the rename exists to
end.

## Consequences

- **Breaking** for anything that read `graph-state.json` by name from outside the-loop.
  Inside it, nothing: the old name is still read, and the CLI's own readers go through the
  constant.
- The `phase-selection` checklist grows one section, rendered **only** when the instance
  declared repositories — an install that declared none gets a byte-identical checklist.
- The checklist's token grammar admits `/` so a row can read `repo-octo/app`. No node id
  contains one, and a token that names no phase was already ignored, so the widening can
  only make a row readable — never make it route.
- `tasks.md` loses the `repos:` key from its bundled template.
