# Decision 124: Every recorded event is an attach point — lifecycle hooks are declared in the operator's CLI config, run asynchronously, observe and never decide

- **Status:** proposed
- **Date:** 2026-09-12
- **Deciders:** @MadaraUchiha-314 (owner), the-loop agent session
- **Work item:** [issue-344](https://github.com/MadaraUchiha-314/the-loop/issues/344)

## Context

Issue-344 asks for hooks **throughout the lifecycle** of the-loop: telemetry on work start
and finish, operator actions around work items, and — over time — the-loop's own features
refactored onto the same points. the-loop had one hook surface,
[`routing.graph.hooks`](decision-096.md): a gate appended to a node boundary of the
process graph. None of the ticket's uses is a node boundary. All of them are already
**events the CLI records** — ~150 types in `EVENT_TYPES`, the enforced single source of
truth of [decision-025](decision-025.md).

Seven questions had to be answered, and each answer is a rule a reviewer can check.

## Decision

**D1 — The attach points are the event catalog, not a curated list.** A hook attaches to
an event type or an `fnmatch` pattern over `EVENT_TYPES` (minus `hooks.*`), expanded at
load; a pattern matching nothing fails the load. A curated list of "lifecycle points"
would be a second catalog exactly as complete as someone remembered to make it.

**D2 — Asynchronous, one thread, bounded.** Hooks run off one worker thread in emission
order; `emit` never waits. The queue holds 1024 records; overflow drops **for hooks only**
and records one `hooks.dropped` per episode; a normal exit drains for 5 s. Synchronous
hooks would put an HTTP round-trip inside every `api.request` and every poll cycle.

**D3 — A declaration that cannot be honoured fails the entry point that loads it.** The
receiver, the poller, the service and every one-shot command that records events
install the block from the same `configure_from_file` call; a `HooksConfigError`
propagates. The alternative — log and run without hooks — is the silent disarm the graph
hooks were built against, and a telemetry hook that silently stops is worse than a daemon
that refuses to start naming the line.

**D4 — A `path` module resolves against the CLI config file's directory.** The
declaration is the instance's (`server.started` has no checkout), so its code lives with
it; containment (no absolute, no `..`, no symlink out) is the graph loader's rule with
the root swapped. A graph hook's `path` keeps resolving against each checkout. Two roots
for two surfaces, documented rather than papered over; `module:` serves both.

**D5 — Shipped lifecycle hooks are attachable by the operator.** The graph rule
("only `x-` may be attached") exists because attaching `classify-feedback` elsewhere would
edit the process. An observer edits nothing, and the point of shipping `forward-event` is
that an enterprise attaches it. Shipped lifecycle hooks live in their own table, not the
graph registry, so `the-loop graph hooks` never invites attaching one to a node.

**D6 — A separate context type, one everything else.** `HookContext` is *for a node*;
filling it with placeholders would make every field a lie for half its users. A lifecycle
hook receives a `LifecycleEvent` (the record plus `params` and the instance name) and
returns `HookResult | None`. The decorator, the result type, the loader, the `x-`
namespace and the load-or-fail rule are shared.

**D7 — Refactoring internal features onto the seam is out of scope; the seam is proved by
`forward-event`.** The announcement, the reactions and comment mirroring each move an
injected test double into a config switch and are their own work items.

**Anti-recursion, as two guards:** `hooks.*` is never an attach point, and a record emitted
on the worker thread — by a hook, directly or through anything the-loop does for it — is
written and never re-dispatched.

## Consequences

- **Easier:** telemetry on any point of the lifecycle with one YAML entry; an enterprise's
  commonest case with no Python; one authoring API across both hook surfaces; the
  candidates for refactoring internal side effects have a seam to land on.
- **Harder / costs:** a second block of executable configuration to review like code; a
  hook's fields are the record's, typed per event in prose rather than per event in code;
  a slow hook shows up as `hooks.dropped` rather than as back-pressure; one-shot commands
  pay the same strictness on a bad declaration as the daemons.
- **Unchanged:** the graph hooks, their rules and their tests; the trust model
  ([decision-123](decision-123.md): the CLI config is the only declaration); the graph's
  authority — no lifecycle hook can move a pointer, answer a gate or choose an edge.

## Alternatives considered

- **Extend `routing.graph.hooks` with lifecycle attachments** — puts an instance-wide
  concern under `routing.graph`, and would either share the checkout-relative `path`
  root (wrong for the daemon's own events) or fork it inside one block.
- **Synchronous hooks with a per-hook timeout** — Python threads cannot be interrupted;
  a "timeout" would be a second thread anyway, with the emitter now blocked on it.
- **Hooks on the channel bus (`channels.*`) instead of the event log** — the bus carries
  sixteen conversational event types; the log carries every decision. The ticket's
  "extensive" is the log.
- **Fail soft on a bad declaration** — rejected for the reason D3 states.
- **Reuse `HookContext`** — rejected for the reason D6 states.
