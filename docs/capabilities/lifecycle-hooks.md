# Capability: lifecycle hooks

> Code of the operator's own, asked at the moments a work item's delivery turns — a start,
> a session launch, a wait on a person, a phase change, the end — before the-loop acts;
> declared once in the CLI config; run in-process or over JSON-RPC (issue-344).

## What it is

A **curated catalog of seven lifecycle points**, each with a typed context of facts a hook
reads and decisions a hook may change, and one executor interface — a `LifecycleHooks`
subclass — that the-loop runs synchronously in the path of the thing it decides. The
operator declares executors under the top-level `hooks` of `cli-config.yaml`; each runs
locally (`module`/`path`) or as a remote JSON-RPC service (`url`), authored against
`the_loop.sdk.hooks`.

It is distinct from the [process graph](process-graph.md)'s hooks (a check at a node
boundary, `pass | block | wait | skip`) and from the [event log](observability.md) (a
record of what happened). The closed first attempt (PR #357) made every event type an
attach point; the owner's ruling — *"centered around events … a disaster"* — is the
constraint this capability is built around ([decision-137](../decisions/decision-137.md)).

## Current behaviour

### The catalog

- The system SHALL define exactly these points, in this order, as the only names a
  declaration may reference: `work_item_start`, `session_spawn`, `session_spawned`,
  `waiting_for_input`, `input_received`, `phase_changed`, `work_item_complete`. `the-loop hooks points` SHALL
  list them with their facts and decisions. `EVENT_TYPES` SHALL NOT be a source of points.
- Each point SHALL fire synchronously, before the thing it decides: `work_item_start` once
  per arming before the workspace is prepared; `session_spawn` before every harness
  launch (first spawn, pull-request session, respawn); `session_spawned` after
  registration, before the announcement; `waiting_for_input` before an agent's question is
  published and when a human node is entered; `phase_changed` when the phase label changes
  or a terminal node is reached, before the channels are told; `work_item_complete` when
  the item's ticket or pull request closes, before the closure is announced.
- Every context SHALL be facts plus marked decision fields with JSON types, and SHALL carry
  the work item as a modelled entity (`WorkItem`: ref, provider, host, owner, repo,
  repository, number, kind, url, id), never as a bare string. The system
  SHALL read back decisions only, refuse a wrong-typed decision as that hook's failure, and
  ignore a changed fact.

### Decisions and their effects

- `input_received` SHALL fire when a person's input reaches the loop — an answer through
  `the-loop reply` (CLI, API, a channel), a comment or review about to be delivered into a
  session, a control command from the ticket or a control verb — before the-loop delivers,
  reads or runs it. Its `text` decision SHALL replace what is delivered (an answer, a
  comment's body); `proceed: false` SHALL drop it: a comment is not delivered and the ticket
  gets one marked comment (`input-refused`), a ticket command is rejected
  (`control.rejected`, reason `input-refused`), a reply or verb is refused to its caller.
- `proceed: false` at `work_item_start` SHALL disarm the work item, post one marked
  comment naming the reason, settle the event without retry, and record `hooks.refused`.
- `proceed: false` at `session_spawn` SHALL prevent the launch (first spawn, respawn:
  settled as refused with the comment; a pull request's session: delivered into the work
  item's session instead). `prompt` SHALL replace the text the harness boots on.
- `announce: false` at `session_spawned` SHALL skip the session announcement; at
  `work_item_complete` it SHALL skip the `work-item.closed` publish. `notify: false` at
  `phase_changed` SHALL skip the `phase.*` publishes for that transition. `question` and
  `summary` at `waiting_for_input` SHALL replace an agent's published question; for a gate
  they SHALL be empty and ignored.
- With no hooks declared, every one of those behaviours SHALL be exactly what it was.

### Declaration and loading

- The CLI config SHALL accept a top-level `hooks[]`: `name` (`^[a-z][a-z0-9-]*$`, unique)
  and exactly one of `module`, `path` (resolved against the config file's directory, never
  a checkout), `url`; `executor`/`with` on a local entry; `tokenEnv`/`headers`/
  `timeoutSeconds` (default 10) on a remote one; `on` (a subset of the catalog), `required`
  (default false), `enabled` (default true). A malformed entry SHALL fail the load naming
  it.
- The key `on` SHALL be accepted bare, as every documented example writes it, as well as
  quoted: `yaml.safe_load` follows YAML 1.1 and reads the bare key as the boolean `True`,
  and the loader SHALL map that key back to `on` before any other rule sees the entry.
  An entry carrying both spellings SHALL be refused. A refusal for an unknown key SHALL
  be a `HooksConfigError` naming the entry and every offending key whatever its type
  (issue-433).
- A `url` SHALL be `https`, or `http` to a loopback host; `http` elsewhere with a
  `tokenEnv` SHALL be refused at load. `tokenEnv` SHALL name a variable read at call time;
  an `Authorization` header in `headers` SHALL be refused.
- A local module SHALL define exactly one `LifecycleHooks` subclass, or `executor` SHALL
  name one (a class, constructed with `with`, or an instance); an import or construction
  failure SHALL fail the load naming the entry.
- A daemon (poller, receiver, service) SHALL load the declaration at start and refuse to
  start on one it cannot load. A one-shot command SHALL load it lazily on first use and,
  when that fails, run hookless and record `hooks.load_failed`. The declaration SHALL be
  read once per process.

### Execution and failure

- Executors SHALL run in declaration order; each SHALL see the earlier ones' decisions.
  A `None` return SHALL pass the context through; a returned context of the same type SHALL
  replace its decisions; a remote result object SHALL replace the decisions it names.
- A hook that raises, times out, answers badly or cannot be reached SHALL be recorded
  (`hooks.failed`) and skipped; the chain SHALL continue and the operation SHALL proceed.
  A `required` hook failing at a `proceed` point SHALL set `proceed: false` with a reason
  naming it. No exception from the chain SHALL reach a dispatch, an advance or an ask.
- A changed decision SHALL be recorded as `hooks.decided` (point, hook, changed fields).

### The remote protocol and the SDK

- A remote executor SHALL send one JSON-RPC 2.0 `POST` per invocation (`method` the point,
  `params` the context, an integer `id`) and read `result: null` or an object of decisions;
  `error`, a non-2xx status, a timeout or a mismatched `id` SHALL be the hook's failure.
- `the_loop.sdk.hooks` SHALL export `LifecycleHooks`, the seven contexts, `POINTS`,
  `handle_request` (the server half for any HTTP framework) and `HookServer` (a stdlib
  server with an optional bearer check and `GET /health`), importing no FastAPI, uvicorn or
  MCP.
- `the-loop hooks` SHALL report the declaration without importing a module or contacting a
  URL, exiting 1 on one that cannot be read.

## Design

[`docs/specs/issue-344/design.md`](../specs/issue-344/design.md) ·
[hooking the lifecycle](../cli/lifecycle-hooks.md) ·
[`hooks` options](../config/cli/hooks-options.md) ·
[`the-loop hooks`](../cli/commands/hooks.md) ·
[decision-137](../decisions/decision-137.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-433 | The declaration loader accepts the bare key `on` (2026-09-29): `yaml.safe_load` reads it as the boolean `True`, so a hook declared exactly as the docs show was refused as having an unknown key, and the refusal itself raised `TypeError` joining a non-string key instead of the `HooksConfigError` that names the entry. The key is normalised before the unknown-key check, both spellings on one entry are refused, and unknown keys are rendered with `repr` whatever their type | [spec](../specs/issue-433/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/433) |
| issue-344 | Capability minted: seven lifecycle points with typed contexts (facts + decisions), the `LifecycleHooks` executor interface, the top-level `hooks[]` declaration (local `module`/`path`, remote `url` over JSON-RPC), the chain runner with warn-and-continue and `required`, the-loop's own announcements consulting the seam, `the-loop hooks`, and `the_loop.sdk.hooks`. Supersedes the event-centred attempt of PR #357 | [spec](../specs/issue-344/), [decision-137](../decisions/decision-137.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/344) |
