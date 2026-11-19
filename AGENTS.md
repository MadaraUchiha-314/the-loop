# Working in the-loop

Read `.the-loop/harness-config.yaml`, `skills/the-loop/SKILL.md`, and the relevant
skill references before implementing a work item. This repository builds and uses
the-loop. Follow the work item's selected graph, record verification evidence
under `docs/specs/<id>/evidence/`, and update affected capability docs with code.
Use the-loop's ticket, comment, ask and PR verbs when available. Explicit user
instructions and the work item's frozen selections govern scope and approvals.

**Prompts and strings (issue-540).** Text the CLI sends to an agent goes in a Markdown file
under `cli/the_loop/prompts/`, read with `the_loop.prompts`; never a Python string literal.
A human-facing message the-loop posts goes in `cli/the_loop/strings/en.json`, read with
`the_loop.strings.t`. See [`docs/capabilities/prompts-and-strings.md`](docs/capabilities/prompts-and-strings.md).
