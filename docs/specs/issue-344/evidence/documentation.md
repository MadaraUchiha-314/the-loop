---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#344"
---

# Documentation: programmatic hooks around the lifecycle of a work item's delivery

> The organized view must not rot: every capability and user-facing page this change makes
> wrong is updated in the same pull request.

## Capability docs

| Page | What changed |
|---|---|
| [`docs/capabilities/lifecycle-hooks.md`](../../../capabilities/lifecycle-hooks.md) (new) | The capability minted, in EARS form: the catalog, the decisions and their effects, the declaration and loading rules, execution and failure semantics, the remote protocol and the SDK; a history row |
| [`docs/capabilities/capabilities.md`](../../../capabilities/capabilities.md) | The index row, beside `process-graph` |

## Documentation

| Page | What changed |
|---|---|
| [`docs/cli/lifecycle-hooks.md`](../../../cli/lifecycle-hooks.md) (new) | *Hooking the lifecycle*: what it is and is not (graph hooks, the event log), writing one, declaring it, the six points with facts and decisions, running it as a service, the wire format, the failure table, what to review before adopting one |
| [`docs/config/cli/hooks-options.md`](../../../config/cli/hooks-options.md) (new) | The top-level `hooks` and every key of an entry (the docs-parity test requires a heading per schema leaf) |
| [`docs/cli/commands/hooks.md`](../../../cli/commands/hooks.md) (new) | `the-loop hooks` / `hooks points`: output, exit codes, JSON shape |
| [`docs/.vitepress/config.mts`](../../../.vitepress/config.mts) | The three pages in the *Commands*, *Extending* and *CLI config* sidebars |
| [`docs/cli/commands/index.md`](../../../cli/commands/index.md) | The `hooks` row in the repo-scoped table |
| [`docs/config/cli/index.md`](../../../config/cli/index.md), [`docs/config/index.md`](../../../config/index.md) | The options-by-area row and the link |
| [`docs/cli/hooks.md`](../../../cli/hooks.md) | A tip distinguishing graph hooks from lifecycle hooks, linking the new page |
| [`docs/sdk/reference.md`](../../../sdk/reference.md), [`docs/sdk/index.md`](../../../sdk/index.md) | The `the_loop.sdk.hooks` section and the *Next* link |
| [`docs/cli/state.md`](../../../cli/state.md) | The portable record's new `lifecycle` section |
| [`docs/decisions/decision-137.md`](../../../decisions/decision-137.md) (new) + [`decisions.md`](../../../decisions/decisions.md) | The decision record and its index row |
| [`skills/the-loop/SKILL.md`](../../../../skills/the-loop/SKILL.md) | The CLI-config table gains a *lifecycle hooks* row |
| [`skills/the-loop/reference/automation.md`](../../../../skills/the-loop/reference/automation.md) | A bullet on lifecycle hooks and what a session sees of them (a reworded question, a refused start explained on the ticket) |
| `.the-loop/cli-config.schema.json` + `cli/the_loop/schemas/cli-config.schema.json` | The top-level `hooks` block, every key described (identical copies, pinned by the parity test) |
| `.the-loop/cli-config.yaml`, `skills/the-loop/templates/cli-config.yaml` | A commented `hooks:` sample beside `graphs` and `critics` |
| `cli/the_loop/eventlog.py` (`EVENT_TYPES`) | `hooks.loaded`, `hooks.load_failed`, `hooks.decided`, `hooks.failed`, `hooks.refused` |

**Not affected**, checked rather than assumed:

- `docs/api-specs/openapi` — no route changes; `the-loop hooks` is local, like `graph hooks`.
- `README.md` — describes the loop at a level the change does not contradict; the CLI
  section lists the daemon verbs, not every repo-scoped command.
- `commands/*.md` (the slash commands) — no command's behaviour changes; a session learns
  what it needs from the skill's automation reference.
- `docs/config/harness-config.md` — the harness config gains nothing; the declaration is the
  operator's CLI config (decision-123).
