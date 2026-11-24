# Manual evidence — issue-553 (T11)

**What was run.** The steps of `commands/gather-context.md`, by hand, for the draft
title "handoff stages". The slash command itself could not be invoked: the plugin
installed in this session is 20.18.0, which does not have it yet. So this proves the
command's steps and the template, not the slash-command wiring. The parity tests (T2)
cover that the command file is registered.

| Step | Result |
|---|---|
| write `docs/specs/draft-handoff-stages/current-state.md` from the template, with `gatheredAt` set from `git rev-parse --short HEAD` | written; `gatheredAt` holds a commit |
| `npx --yes markdownlint-cli2@0.18.1 docs/specs/draft-handoff-stages/current-state.md` | 0 errors |
| the node's shape check: the file copied into a temporary work item at `context-gathering` with both rows selected, then `Runtime.advance` | status `pass`, and the work item moved to `context-approval` |
| token or hostname in the file | none; it names two source paths only |

The draft folder was removed afterwards; it is not part of the change.
