# Documentation evidence — issue-553

Text checks for T9, run from the repository root.

| Check | Command | Result |
|---|---|---|
| every document in the design's table names the file | `grep -c "current-state.md" <file>` | non-zero in `skills/the-loop/SKILL.md` (8), `reference/workflow.md` (10), `skills/handoff-to-the-loop/SKILL.md` (7), `commands/gather-context.md` (8), `work-on.md` (3), `execute-tasks.md` (2), `brainstorm.md`, `new-requirement.md`, `create-design.md`, `create-testing-plan.md`, `create-tasks-plan.md` (1 each), `docs/capabilities/process-graph.md` (5), `spec-workflow.md` (8), `docs/reference/commands.md` (1), `docs/cli/graphs.md` (1), `docs/cli/commands/handoff.md` (3), `docs/reports/labels-and-dashboards.md` (2), `README.md` (2) |
| the label is documented | `grep -c "context-gathering" docs/cli/graphs.md docs/reports/labels-and-dashboards.md commands/init.md` | 1, 2, 1 |
| one place states the file against `context.md` | `grep -n "is not .context.md" skills/the-loop/SKILL.md` | the section heading at line 109, and one reference to it |
| "report it as data" and "no secrets" | `grep -n "data\|secrets" commands/gather-context.md skills/the-loop/templates/current-state.md` | both rules in both files |
| the staleness check | `grep -n "gatheredAt" commands/execute-tasks.md` | present, with the `git diff --stat <gatheredAt>..HEAD -- <paths>` example |
| open pull requests are not listed | `grep -c "open pull request"` on the template and the command | 0 |
| the decision is recorded | `docs/decisions/decision-156.md` and its index line | present |

Documents changed: the 22 Markdown files of the documentation commit, plus
`commands/gather-context.md`, `skills/the-loop/templates/current-state.md` and
`docs/decisions/decision-156.md`.

Not checked by a test: that the wording of each document is right. That is for the
reviewer.
