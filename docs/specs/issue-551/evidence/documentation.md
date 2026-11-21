---
type: evidence
workItem: issue-551
---

# Documentation: a session never goes idle unnoticed

> The `capability-docs` node's proof, and it gates **both** sections (issue-174). Every
> statement in the docs below was checked against the code as built, not copied from
> `design.md`. Where the two differ, the docs follow the code.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`process-graph.md`](../../../capabilities/process-graph.md) | New § The Stop gate: the hook asks `the-loop sessions stop-check`, the six-step order, the allow reasons, the refusal's content, the attempt cap and `gate-gave-up`, the older-CLI fallback, the binding check. § What drives the graph: an inbound event reads an agent-owned node read-only unless a hook declared `reads_event`; blocks and escalations come only from a claim; the claim envelope's `assignment` and `next`. § The hook contract and § A repository's own hooks: the `reads_event` declaration and its default | issue-551 |
| [`interactive-sessions.md`](../../../capabilities/interactive-sessions.md) | New § Session states and the watcher: turn records per harness, the states with one state diagram, the watcher (tick, nudge budget per node visit, the one notice, what ends a stall, who is never nudged), ask deadlines, the declared wait, restarts. § Codex hosting names both hooks | issue-551 |
| [`channels.md`](../../../capabilities/channels.md) | New § Session notices: the four events, the default subscription, how each renders on Slack and on the ledger, the inert drawing of the default answer. The catalog bullet, the status-reaction table and the mention rule name the new events | issue-551 |
| [`cli.md`](../../../capabilities/cli.md) | `ask --after`, `the-loop wait`, `sessions stop-check` and `turn-start`, the `session:` line of `check`, the State column of `sessions list` | issue-551 |
| [`control-plane.md`](../../../capabilities/control-plane.md) | The three new operations and `defaultAfterSeconds`; the `session` object; attention kinds `stalled` and `declared-wait`; the corrected rule for when an ask closes; the watcher runs in the service | issue-551 |
| [`spec-workflow.md`](../../../capabilities/spec-workflow.md) | The context rule no longer says a headless session ends at a boundary: a daemon-driven session checkpoints, compacts or delegates, and continues; a turn ends only for one of five reasons | issue-551 |
| [`distribution.md`](../../../capabilities/distribution.md) | The plugin's hook list names the turn-start hook, for Claude Code, Codex and Cursor | issue-551 |
| [`observability.md`](../../../capabilities/observability.md) | The nine `session.*` event types, and that a session's state is derived from them | issue-551 |
| [`prompts-and-strings.md`](../../../capabilities/prompts-and-strings.md) | The Stop hook's three prompt files beside the script, and that the refusal text is the service's | none: one sentence corrected, no behaviour of this capability changed |
| [`capabilities.md`](../../../capabilities/capabilities.md) | The one-line summaries of process-graph and interactive-sessions | index, no history table |

Decision record: [`decision-155`](../../../decisions/decision-155.md), with its row in
[`decisions.md`](../../../decisions/decisions.md). It is linked from the history rows
above and from the two sections that state the mechanisms.

## Documentation

| Document | What changed |
|----------|--------------|
| `README.md` | One paragraph: a session never goes idle unnoticed (the Stop gate, the watcher, `the-loop wait`, `ask --default … --after …`), and that a claim's answer carries the next assignment. The Codex section names both hooks |
| `docs/cli/commands/ask.md` | New § Asking without blocking: the default at the deadline, the minimum wait, the one reminder. The note on routing was wrong since issue-482 (it said the verb never uses the service) and is corrected |
| `docs/cli/commands/sessions.md` | `stop-check` and `turn-start`, marked as for the harness hooks, with the JSON answer; the State column of `list` |
| `docs/cli/commands/check.md` | New § The `session:` line, with the JSON object's five keys |
| `docs/cli/commands/events.md` | The session turn and watcher events in the list of what the log holds |
| `docs/cli/commands/comment.md` | The pointer to `ask` mentions the non-blocking form |
| `docs/cli/commands/install.md`, `docs/cli/commands/upgrade.md`, `docs/cli/installation.md`, `docs/guide/installation.md` | Codex setup installs two hooks, not one |
| `docs/cli/hooks.md` | The `reads_event` flag for a graph hook of your own, and a pointer to the harness hooks |
| `docs/guide/how-it-works.md` | The repository map's `hooks/` line named only the SessionStart reminder |
| `docs/config/cli/channels-options.md` | One sentence: the Jira channel hears the three follow-up events only when its list names them. The rest of what the earlier tasks wrote was checked against the schema and is correct |
| `skills/the-loop/reference/observability.md` | One question in the audit-trail list: why a session went quiet, and what the-loop did |
| `skills/the-loop/templates/cli-config.yaml` | The commented `subscribe` example states the new default |

Checked and left unchanged, with the reason:

| Document | Why |
|----------|-----|
| `docs/cli/commands/wait.md` | Written by task 8; checked against the code and correct |
| `docs/config/cli/routing-options.md` | The `routing.watchdog` and `routing.asks` section, written by task 2, matches the schema key for key |
| `docs/index.md`, `docs/guide/what-is-the-loop.md` | Neither lists hooks or what the-loop guarantees about a session, so nothing in them became wrong |
| `docs/.vitepress/config.mts` | `wait` was registered in the sidebar by task 8; no page was added here |
| `skills/the-loop/SKILL.md`, `reference/context.md`, `reference/collaboration.md`, `reference/automation.md` | Updated by task 13 |

## After the reviews

The docs were corrected three more times, once after each review that changed
behaviour: `590d5d87` (self-review round 1), `cf4d13a9` (round 2) and `a0b978dd`
(security review), plus one sentence in `bf1ddf60` (critic). Round 2 checked twelve
behaviours against the docs and found six false or missing; all were corrected.
