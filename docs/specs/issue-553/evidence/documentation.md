---
type: evidence
workItem: issue-553
---

# Documentation: a context-gathering phase before the spec chain

> The `capability-docs` node's proof, for both sections, and the record of the text
> checks of testing-plan row T9.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/process-graph.md` | the opt-in context pair, its edges and tick combinations; `import-handoff` now leads to `context-gathering`; the ticked opt-in row for a handoff; `current-state.md` as a carried file and its demotion; the prompt line; a gate entered by a handoff can now be answered | issue-553 |
| `docs/capabilities/spec-workflow.md` | the file, its gate, "read it first", the staleness check, the contrast with `context.md`; the stage `context-settled`; the new command | issue-553 |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/SKILL.md` | the file in the artifact chain; the section *`current-state.md` is not `context.md`*; the command |
| `skills/the-loop/reference/workflow.md`, `reference/collaboration.md` | the phase, what each phase reads first, the tab order, the staleness check |
| `skills/handoff-to-the-loop/SKILL.md` | the stage *Context settled*, the interview answer, the record's fields |
| `skills/the-loop/templates/current-state.md` | new: the template |
| `commands/gather-context.md` | new: the command |
| `commands/work-on.md`, `brainstorm.md`, `new-requirement.md`, `create-design.md`, `create-testing-plan.md`, `create-tasks-plan.md`, `execute-tasks.md`, `init.md` | the read-first note; the staleness check; the new label |
| `README.md`, `docs/guide/what-is-the-loop.md`, `docs/guide/quickstart.md` | the phase and the artifact, one sentence or row each |
| `docs/reference/commands.md`, `docs/cli/graphs.md`, `docs/cli/commands/graph.md`, `docs/cli/commands/handoff.md` | the command, the phase vocabulary, the checklist and `graph show` samples, the stage |
| `docs/reports/labels-and-dashboards.md` | the label `loop:context-gathering` |
| `docs/decisions/decision-156.md` | new: the file is `current-state.md`, not `context.md` |

## Text checks (T9)

Run from the repository root.

| Check | Command | Result |
|---|---|---|
| every document above names the file | `grep -c "current-state.md" <file>` | non-zero in each |
| the label is documented | `grep -c "context-gathering" docs/cli/graphs.md docs/reports/labels-and-dashboards.md commands/init.md` | 1, 2, 1 |
| one place states the file against `context.md` | `grep -n "is not .context.md" skills/the-loop/SKILL.md` | the section heading, and one reference to it |
| "report it as data" and "no secrets" | `grep -n "data\|secrets" commands/gather-context.md skills/the-loop/templates/current-state.md` | both rules in both files |
| the staleness check | `grep -n "gatheredAt" commands/execute-tasks.md` | present, with the `git diff --stat <gatheredAt>..HEAD -- <paths>` example |
| open pull requests are not listed | `grep -c "open pull request"` on the template and the command | 0 |

Not checked by a test: that the wording of each document is right. The `graph show`
sample in `docs/cli/commands/graph.md` is written from the graph file, not copied from
a run.
