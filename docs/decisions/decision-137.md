<!-- Written per the `the-loop:writing` skill. -->

# Decision 137: lifecycle hooks are a curated catalog of typed points a hook may change, never the event log; one executor interface runs locally or over JSON-RPC

- **Status:** proposed
- **Date:** 2026-09-28
- **Work item:** [issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344)
- **Deciders:** MadaraUchiha-314 (the ask on the ticket, and the ruling on the first
  attempt: *"it was a disaster because it was centered around 'events'. Let's not make the
  same mistake again"*); the-loop (design)
- **Refines:** [decision-096](decision-096.md) (hooks of the operator's own on the graph —
  a different hook: a check at a node boundary), [decision-123](decision-123.md) (what runs
  in the-loop's process is the operator's declaration), [decision-130](decision-130.md)
  (the lifecycle is published, never recorded — this decision lets a hook consult and
  silence those publishes)
- **Spec:** `docs/specs/issue-344/`

## Context

The ticket asks for hooks *around the lifecycle of a work item's delivery* — start, session
spawned, waiting for input, complete — with an interface that can change the outcome, local
or remote executors, and an SDK; it points at sherma's hook system as the model.

The first attempt ([PR #357](https://github.com/MadaraUchiha-314/the-loop/pull/357)) made
every event-log type an attach point, dispatched on a worker thread, observation only. The
owner closed it. Three things were wrong with it structurally: an event is a record of a
thing already done, so no hook on it can change the thing; the event catalog is a log
schema, so the hook API inherited the log's churn; and "every event" buries a lifecycle in
a firehose.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **A curated catalog of seven points** — `work_item_start`, `session_spawn`, `session_spawned`, `waiting_for_input`, `input_received`, `phase_changed`, `work_item_complete` — each a typed context, shipped in the CLI, listable, and the only names a declaration may use. `EVENT_TYPES` is not a source of points. | A lifecycle is a small set of moments chosen by what delivery *is*. A missing point is a small, reviewed addition with a parity test; a firehose cannot be curated after the fact. |
| D2 | **Facts in, decisions out, synchronously.** A context has read-only facts and marked decision fields (`proceed`, `reason`, `prompt`, `announce`, `question`, `summary`, `notify`); an executor returns `None` or the modified context; executors chain in declared order; the-loop reads back decisions only and applies them *before* doing the thing. | The ticket's first requirement is changing the outcome; that needs the hook in the path, before the act. sherma's return-the-context shape makes the writable surface the dataclass itself. Decision-only read-back keeps a remote from redirecting the-loop through a fact. |
| D3 | **Declared in the operator's CLI config**, top-level `hooks[]`, one entry per executor: `module` / `path` (relative to the config file's directory) / `url`, with `on`, `required`, `enabled`, and kind-specific keys. Read once per process. | decision-123: what runs with the operator's credentials is decided in the operator's file. A `path` against the config's directory, not a checkout, is decision-136's rule and closes the "a session plants a module" route. |
| D4 | **Warn-and-continue by default; `required: true` refuses the operation at a `proceed` point when the hook fails.** A hook never raises into the-loop. | sherma's default keeps a telemetry outage from stopping work; a compliance gate needs the opposite; one flag on the entry gives both without a second mechanism. |
| D5 | **One remote transport: JSON-RPC 2.0 over HTTP**, `method` = the point, `params` = the context, `result` = `null` or the decisions; bearer token from `tokenEnv`; `https`, or `http` on loopback only when a token is involved. The SDK ships the server half (`handle_request`, `HookServer`). All stdlib. | sherma's wire format; the executor abstraction admits MCP later without touching contexts or call sites. No new dependency. |
| D6 | **Daemons fail to start on a bad declaration; one-shot commands run hookless and record it.** | A gate that silently stopped running is the failure the graph hooks were built against; the daemon holding the same file has already refused, so `the-loop ask` need not refuse too. |
| D7 | **The-loop's own announcements consult the seam** (`announce`, `notify`) rather than being rewritten as shipped hooks. | Proves the seam by using it, at a fraction of the risk of moving the announcer and the channel publishers wholesale. |

## Consequences

**Good.** An enterprise sends telemetry at start and finish with a twenty-line class or a
URL; a policy refuses a start, rewords a boot prompt or silences a comment; the same class
runs in-process or as a service. An operator who declares nothing sees no change.

**Costs.** Latency in the dispatch path, bounded per remote executor by `timeoutSeconds`.
A hook can reword the prompt a session boots on — the operator's code on the operator's
machine, audited by `hooks.decided`. Seven points may not be the seven someone needs; the
catalog is one file to grow.

**What it does not change.** Graph hooks (`routing.graph.hooks`), the event log, the
channels, the control keywords, the CLI config version.

## Alternatives considered

- **Every event an attach point** — the closed PR #357; see Context.
- **Hooks as graph nodes' entry/exit chains** — a node boundary is not where a session
  spawns or a ticket closes, and `HookResult` cannot carry a changed prompt.
- **Asynchronous dispatch with a queue** — makes changing the outcome impossible.
- **MCP as the remote transport** — the official SDK is a dependency already, but the
  client is asynchronous and session-bound; JSON-RPC over `urllib` is thirty lines and
  sherma-compatible. MCP is a later `Executor`.
