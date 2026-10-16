# Documentation: issue-494

## Capability docs

- [`docs/capabilities/spec-workflow.md`](../../../capabilities/spec-workflow.md): the
  gate rule, the brainstorm EARS line, and a History row for issue-494.
- [`docs/capabilities/process-graph.md`](../../../capabilities/process-graph.md): the
  `absentOutcome` / `gate` / `whenPresent` rule and its fail-closed behaviour (with
  `HookContext.visited`), what `--recompute` reports for a present brainstorm, the
  `lock-artifacts` note, and a History row.

## Documentation

Files updated to describe `brainstorm-approval`:

- `skills/the-loop/SKILL.md`: the chain intro, artifact 0, and the *Gate-less artifacts*
  rule (now `tasks.md` only)
- `skills/the-loop/reference/workflow.md`: the approval-node list, the locking list,
  Phase 0, *Brainstorming is optional*
- `skills/the-loop/templates/brainstorm.md`: front-matter comments and the header note
- `commands/brainstorm.md`, `commands/work-on.md`, `commands/new-requirement.md`: the
  gate, and the declared-skip and pre-ticket cases for an unlocked brainstorm
- `docs/capabilities/spec-workflow.md`: the gate rule, the brainstorm EARS line, a
  History row
- `docs/capabilities/process-graph.md`: the `absentOutcome` / `gate` / `whenPresent`
  rule, the `lock-artifacts` note, a History row
- `README.md`: the gate-less sentence

T9 check: `grep -rn "no approval gate\|no gate approves a brainstorm\|gate-less\|advances
on shape alone\|advance on shape alone" skills commands docs/capabilities README.md
rules | grep -i brainstorm` returns only the new wording and the issue-281 History row,
which records what was true then.
