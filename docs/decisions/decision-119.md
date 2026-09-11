# Decision 119: `state.root` is resolved once, at the load boundary, anchored on the config file — and a spawn carries the config path it resolved

- **Status:** proposed
- **Date:** 2026-09-11
- **Work item:** [issue-339](https://github.com/MadaraUchiha-314/the-loop/issues/339)
- **Deciders:** jc1993 (the report), the-loop (design); MadaraUchiha-314 (owner, at the PR)
- **Refines:** [decision-046](decision-046.md) (one root for everything generated, split by
  portability), [decision-108](decision-108.md) (a relative path in the config is resolved
  against the config file, not the working directory), [decision-084](decision-084.md)
  (a service's honest start is its lock, not its spawn)

## Context

`state.root` shipped as a **relative** default (`.the-loop`), and `StateLayout` never
anchored it, so every process resolved it against its own working directory. The daemon
and the CLI therefore addressed different files under one configuration: two heartbeats,
two session registries, two event logs. Issue-339 reports the third file this bit —
`poll-status.json` — and the consequence: a dead poller that `the-loop status` reported
as a *different* (live) poller's stale heartbeat, `/api/v1/health` answering a constant
`{"status":"ok"}` beside it, and 17 hours in which nothing polled GitHub and nothing said
so.

Three questions had to be settled: **where** the divergence is closed — at each read, or
once at load; **what a relative root is anchored on**; and **what a health surface owes**
when the component it hosts is absent.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **`state.root` becomes an absolute path inside `load_cli_config`,** beside the existing `apply_integrations` / `apply_instance` passes — for every document, the empty one included. | The ticket proposes threading a resolved layout into the poller. That fixes the poller and leaves ~30 other `layout_from_config(config)` call sites — the session registry, the event log, the channels store, the work-item ledger — resolving against `cwd`; the ticket itself notes the heartbeat is "the third file it has bitten". Closing it where the config is *read from a file* fixes every consumer at once, with no signature to thread and no call site to remember. `layout_from_config` is deliberately left alone, so a mapping with no file behind it (a test literal, an SDK caller's dict) keeps the behaviour it has. |
| D2 | **A relative root is anchored on the config file's BASE directory** — the directory the config's `.the-loop/` sits in — not on the config file's own directory and not on `cwd`. | This is decision-108's rule (`env.file`: "beside my config" is the one anchor that reads the same from all four resolution branches) shifted one directory out, because the config lives *inside* the directory the root names. It is also the only anchor that **moves no existing state**: `<repo>/.the-loop/cli-config.yaml` with no root, or with the common explicit `state.root: .the-loop`, resolves to the `<repo>/.the-loop` it already resolved to whenever the daemon and the CLI both ran from `<repo>` — which is the configuration that works today. Anchoring on the config's own directory would have nested a second `.the-loop` inside the first. |
| D3 | **Every spawn passes `THE_LOOP_CLI_CONFIG` = the path this process resolved** (`client._spawn_service`, `lifecycle.spawn_service`, `core.daemons.control_daemon`); `schedule_restart` already threaded `--config`. | A daemon is a different, long-lived process that never sees the CLI's `--config` — the module-level override `cli_config.py` documents is sound for a short-lived CLI and has never been true of the daemon it spawns. The variable is the **existing** mechanism at the **same documented priority** as the flag, it needs no argument parser on `the_loop.api.serve`, and it is *inherited*, so a standing session or a restart the daemon later spawns resolves the same file. The value is only ever a path this process already resolved — the issue-222 property, so no request or config value can name another file. |
| D4 | **`/api/v1/health` reports the enabled ingresses, the config path and the state root — and keeps answering HTTP 200 when degraded.** | A component whose entire job is polling must not report `ok` while its poller is absent; that is the ticket's item 2, and `enabled_services × RunLock.is_held()` is the same pair `the-loop status` already answers from, so the API and the CLI cannot disagree. The **status code** stays 200 because it means "the service answered" — it is what `client.healthy()` measures and what `ensure_service` loops on, and a 503 would make every unrelated CLI command conclude "no service" and spawn another, forever, on a box whose only fault is a stopped poller. Health lives in the body. `configPath`/`stateRoot` are no escalation: `GET /api/v1/config` already serves the whole document to the same callers on the same loopback boundary, and those two lines are what would have ended this outage in one `curl`. |
| D5 | **An enabled ingress that fails to start emits `ingress.hosted_failed` at level `error`, and a hosted run loop that ends on its own releases its lock; two roots holding a heartbeat are NAMED by `status`, never merged.** | The ticket's item 3 asks for "`poller.stopped` with no matching `poller.started`" to be noticed. That is a *derived* signal, only as good as the log's retention, when the failure can be recorded as a fact at the moment it is true — and recorded where the trail is actually read (`the-loop events`, the SSE stream, self-diagnosis), instead of a logfile line nobody was tailing. For item 4, `status` names its config, its root and any rival root, and does **not** move its exit code: whether another directory holds an old file is an observation about the filesystem, not a statement about whether this instance's enabled services are running. Moving state is destructive and stays the operator's call. |
| D6 | **Supervision is documented as the operator's job, with the unit — the-loop ships no supervisor.** | The ticket's item 5 offers exactly this alternative, and ranks it last. A supervisor inside the process being supervised is a second outage mode with no bound on its retry loop; every target platform already has one. What was actually missing was the sentence saying so, and a health check worth watching — which D4 is what makes possible. |

## Consequences

**Good.** One configuration names one directory in every process, whatever each was
started from — so `status` describes the daemon that is running, the poller writes the
ledger the CLI reads, and the split that produced two registries and two event logs on the
reporter's box cannot recur. A monitor can watch `/api/v1/health` and see a poller-shaped
outage. A poller that never came up leaves a record instead of a silence. An operator who
does have two roots is told, and told which one was reported on.

**Costs, accepted.** A process started with **no config file anywhere** now writes to
`~/.the-loop/` from every directory instead of creating a state root wherever it was run;
that is the intended correction, and it is the only path whose meaning changes for a
working setup. A deployment that *relied* on `cwd` to select between state roots — one
checkout per root, with no `state.root` and no `--config` — must now say which root it
means, in `state.root` or in `THE_LOOP_CLI_CONFIG`; `status`'s conflicting-root line names
the second directory when one exists. `~` in `state.root` is now **expanded**, where it
used to create a directory literally *named* `~` in the working directory — documented as
a trap rather than a feature, and the expansion `routing.workspace.root` has always done;
an operator who has such a directory moves its contents to the expanded path while nothing
is running. `/api/v1/health` costs three `flock` probes per call, which is what
`the-loop status` already pays.

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Thread a resolved `StateLayout` into the poller, per the ticket's item 1 | D1: fixes one of ~30 call sites; the next generated file bites the same way |
| Anchor a relative root on the config file's own directory | D2: `<repo>/.the-loop/.the-loop`, and a silent state move for every config carrying an explicit `state.root: .the-loop` |
| Make `state.root` required | Breaks every existing config to make the operator restate a default that can be derived correctly |
| Pass `--config` on the `the_loop.api.serve` argv | D3: an argument parser on the service entry point to carry a value that already has an environment form, and one that no longer travels to what the daemon itself spawns |
| `/api/v1/health` returns 503 when degraded | D4: `ensure_service` spawns a second service forever, for a stopped poller |
| The service restarts a hosted ingress that failed | D6: a supervisor inside the supervised process, unbounded |
| Have `status` pick the newest of the two heartbeats | D5: guessing, more confidently. The reporter's whole complaint is a tool that answered without saying which file it answered from |
| Merge or migrate a split state root automatically | D5: destructive, and unrecoverable when the guess is wrong |
