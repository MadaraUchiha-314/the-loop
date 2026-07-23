# Quickstart

This walks through taking a single GitHub issue through the whole loop.

## 1. Scaffold the-loop into your repo

```text
/the-loop:init
```

A guided, schema-driven onboarding writes `.the-loop/config.yaml` (validated against
`.the-loop/config.schema.json`) with sensible defaults. Idempotent — safe to re-run.
Pass `--defaults` to skip the interactive walkthrough.

## 2. Run the whole spec workflow on a ticket

```text
/the-loop:work-on <ticket>
```

`<ticket>` is a GitHub issue or Jira id. This is the superset command: it runs
requirements → design → tasks → execute, pausing for human review at each phase gate,
and is resumable per phase if you stop partway through.

## 3. Or drive phases one at a time

The granular commands run the same flow a step at a time — useful when you want to
pause and think between phases, or a fuzzy idea needs to be brainstormed before it's
worth writing requirements for:

```text
/the-loop:brainstorm <title>        # optional — free-form scratchpad for a fuzzy idea
/the-loop:new-requirement <title>   # draft requirements.md before a ticket exists
/the-loop:create-ticket <path>      # create the ticket from requirements.md
/the-loop:create-design <id>        # design.md from approved requirements
/the-loop:create-tasks-plan <id>    # tasks.md DAG from requirements + design
/the-loop:execute-tasks <id>        # implement, self-check, self/critic-review, evidence
/the-loop:finish-tasks <id>         # cleanup once all tasks are complete
/the-loop:work-status <id>          # read-only status from specs, tasks, execution log
```

See the full [command reference](/reference/commands) for what each one does.

## 4. Watch the artifacts land

Each phase writes to `docs/specs/<id>/` in your repo:

```text
docs/specs/<id>/
  brainstorm.md       # optional root artifact
  requirements.md      # or bugfix.md for bug work
  design.md             # + design/ for UI/UX artifacts, when user-facing
  tasks.md               # the DAG of small, verifiable tasks
  execution-log.md        # progress log written during execution
```

The ticket's phase label moves through `not-started → requirements-definition → design
→ tasks-breakdown → implementation → needs-review → complete` as the loop advances —
`work-status` reads it back out for you at any point.

## Next

- [How it works](/guide/how-it-works) — configuration, templates, and where knowledge
  lives.
- [Command reference](/reference/commands) — every command in one table.
- [CLI reference](/cli/) — the optional `the-loop` companion CLI (webhooks, polling,
  observability).
