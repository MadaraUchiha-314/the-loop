---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#339"
status: draft                # draft | in-review | approved
approvedBy: []
severity: critical           # low | medium | high | critical
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: the poller dies silently and every health surface reports OK, because `state.root` resolves against each process's working directory

## Summary

`state.root` is a **relative** path (`.the-loop`), so every process resolves it against
its own `cwd`. The daemon and the CLI therefore read and write *different* files under
the same configuration, and nothing in the system notices. On the reporter's box this
hid a dead poller for **17 hours** (Sep 8 23:54 → Sep 10 16:57, 13.5.0): GitHub was
polled by nothing, no comment reached Slack, `/api/v1/health` answered `{"status":"ok"}`
throughout, and `the-loop status` reported a *healthy* daemon as `not running` off a
two-day-old heartbeat — which cost the reporter a needless kill and restart of a working
process.

Ticket: [issue-339](https://github.com/MadaraUchiha-314/the-loop/issues/339).

Three independent defects stack into one silent outage:

```mermaid
flowchart TD
    A["state.root is relative<br/>(.the-loop)"] --> B["daemon resolves it against ITS cwd<br/>CLI resolves it against ITS cwd"]
    C["the service is spawned with a fixed argv<br/>and no THE_LOOP_CLI_CONFIG"] --> B
    B --> D["two state roots:<br/>two heartbeats, two registries, two event logs"]
    D --> E["`status` reads the stale one<br/>— reports a live poller dead,<br/>and would report a dead one live"]
    F["a hosted ingress that fails to start<br/>writes no event, only a logfile line"] --> G["`poller.stopped` with no `poller.started`<br/>— the silence IS the signal, and nothing reads it"]
    H["/api/v1/health is a constant<br/>{status: ok, version}"] --> I["a service whose only job is polling<br/>reports healthy while polling nothing"]
    E --> J["17 hours of silent outage"]
    G --> J
    I --> J
```

## Steps to reproduce

1. `the-loop --config <repo>/.the-loop/cli-config.yaml start`, with `polling.enabled:
   true` and no explicit `state.root`, from `cwd=<repo>`. The service comes up and
   hosts the poller; the heartbeat is written to `<repo>/.the-loop/poll-status.json`.
2. From **any other directory**, run `the-loop --config <same file> status`.
3. `status` reports `poller  not running` and a `last cycle:` taken from
   `~/.the-loop/poll-status.json` — a file this instance has never written. The live
   heartbeat under `<repo>/.the-loop/` is not consulted.
4. `curl http://127.0.0.1:4114/api/v1/health` → `{"status":"ok","version":"…"}` whether
   the poller is hosted or absent.
5. Stop the poller (or start the service from a directory whose `.the-loop/` holds a
   different config, so it never hosts one). No event is written: the event log's last
   line stays `poller.stopped`, and `health` still says `ok`.

Reduced to one line, with no daemon at all:

```console
$ python3 -c "import os;from the_loop.state import layout_from_config as L;\
print(os.path.abspath(L({}).poll_status));os.chdir('/tmp');\
print(os.path.abspath(L({}).poll_status))"
/repo/.the-loop/poll-status.json
/tmp/.the-loop/poll-status.json
```

One config, two answers.

## Expected vs actual

- **Expected:** one configuration resolves to exactly one state root in every process
  that reads it, whatever each process's working directory; a health surface reports
  `ok` only when the components the configuration enables are actually running; a
  component that fails to start says so in the event log; `status` names the files it
  read rather than guessing between candidates.
- **Actual:** the root is `cwd`-dependent, so the daemon and the CLI silently address
  different files. `/api/v1/health` is the literal `{"status": "ok", "version": …}`
  regardless of what is running. A hosted ingress that fails to start writes a logfile
  line and no event. `status` reads one candidate root without saying which, or that
  another exists.

Verbatim from the ticket, with a live daemon polling 27 seconds earlier:

```
instance    (unnamed) [open] — 0 declared, 18 managed
service     not running [enabled]
poller      not running [enabled]
            last cycle: 2026-09-08T23:54:01Z (1d ago, before it stopped)
```

## Root cause (confirmed)

**`the_loop/state.py:360-364` returns a relative root and every caller resolves it
against its own working directory.**

```python
def layout_from_config(config: Optional[dict]) -> StateLayout:
    state = ((config or {}).get("state")) or {}
    root = str(state.get("root") or "").strip()
    return StateLayout(root=root or DEFAULT_STATE_ROOT)   # DEFAULT_STATE_ROOT = ".the-loop"
```

`StateLayout.root_path` is `Path(self.root)` — never anchored — so `poll_status`,
`poll_pidfile`, `portable_dir`, `local_dir` and `event_log` are all relative paths whose
meaning is decided by whoever calls them, and `docs/cli/state.md` documents exactly that
(“default `.the-loop`, relative to the process's working directory”).

Two aggravating factors turn a latent hazard into the reported outage:

1. **The spawn drops the operator's config.** `client/__init__.py:109` and
   `core/lifecycle.py:spawn_service` spawn `[sys.executable, "-m",
   "the_loop.api.serve"]` with no `--config` and no `THE_LOOP_CLI_CONFIG`, so the child
   re-resolves the config from scratch through `cli_config.default_cli_config_path()`
   and lands on whichever branch its inherited `cwd` happens to select
   (`cli_config.py:61-67`). `core/daemons.py:control_daemon` spawns `the_loop.daemon_entry`
   the same way. `lifecycle.schedule_restart` is the one spawn that already threads
   `--config` through — the others were never brought level with it.
2. **Nothing reports the divergence.** `/api/v1/health` (`api/routes.py:327-335`) is a
   constant; `api/ingress.py`'s failure paths log and emit nothing; `status` reads one
   root and names neither it nor the config it came from.

The ticket's own diagnosis — that `poller/daemon.py:_state_layout()` re-resolves the
config instead of using the selected one — is the same defect seen from the daemon's
side, and it is fixed by the same two changes: an anchored root, and a spawn that
carries the resolved config path.

## Requirements

### Requirement 1 — one configuration resolves to one state root, in every process

**User story:** as an operator, I want the daemon and the CLI to read and write the same
files whatever directory each was started from, so that `status` describes the daemon
that is actually running.

#### Acceptance criteria (EARS)

1. WHEN a CLI config is loaded from a path THEN the system SHALL resolve `state.root` to
   an **absolute** path before any consumer reads it.
2. WHEN `state.root` is absent or relative THEN the system SHALL anchor it on the config
   file's **base directory** — the directory that contains the config's `.the-loop/`
   directory, or the config file's own directory when it is not inside one — and SHALL
   NOT anchor it on the process's working directory.
3. WHEN `state.root` is absolute (or begins with `~`) THEN the system SHALL expand and
   use it verbatim.
4. WHEN the same config file is loaded by two processes with different working
   directories THEN both SHALL resolve every path in `StateLayout` to the same absolute
   location.
5. WHEN the control-plane service or an ingress daemon is spawned THEN the spawning
   process SHALL pass its own resolved config path to the child in
   `THE_LOOP_CLI_CONFIG`, so the child cannot select a different config file.
6. The fix SHALL include regression tests that fail before the fix and pass after.

### Requirement 2 — a health surface that reports on what it is hosting

**User story:** as an operator (or a monitor), I want `/api/v1/health` to be `ok` only
when the components the configuration enables are running, so that a poller-shaped
outage is visible to a `curl`.

#### Acceptance criteria (EARS)

1. WHEN `polling.enabled` (or `webhooks.ghWebhook.enabled`, or the Slack listener) is
   true and that ingress is not running THEN `GET /api/v1/health` SHALL answer
   `status: "degraded"` and SHALL name the ingress and why it counts as down.
2. WHEN every enabled ingress is running THEN `GET /api/v1/health` SHALL answer
   `status: "ok"`.
3. `GET /api/v1/health` SHALL report the **config path** and the **state root** this
   process resolved, so an operator can see which files the service is using without
   reading `/proc`.
4. `GET /api/v1/health` SHALL keep answering HTTP **200** in the degraded case: the
   status code is the service's reachability, which `client.healthy()` and
   `ensure_service` loop on, and a non-2xx would make an unrelated CLI command spawn a
   second service forever.
5. WHEN an enabled ingress is not running THEN `the-loop start` SHALL NOT report `ok`.
6. WHEN a hosted ingress's run loop **ends on its own** — a missing dependency, an
   unhandled exception — without a shutdown having been requested THEN the system SHALL
   release that ingress's pidfile lock and SHALL emit `ingress.hosted_failed`, so that
   every liveness surface reports it as not running. (The lock *is* liveness, and a
   hosted ingress holds it under the **service's** pid, so a dead thread inside a living
   service reads as a healthy ingress — the outage's exact shape.)

### Requirement 3 — a component that fails to come up says so where the trail is read

**User story:** as an operator, I want a poller that did not start to write an event,
so that `the-loop events` and self-diagnosis can see the thing that used to be visible
only as an absence.

#### Acceptance criteria (EARS)

1. WHEN the service hosts the ingresses and an **enabled** ingress does not start THEN
   the system SHALL emit an `ingress.hosted_failed` event at level `error`, naming the
   ingress and the reason.
2. WHEN a hosted ingress fails to start THEN the service SHALL keep serving, so the
   reason stays reachable over the API (today's posture, preserved).
3. An ingress that is **not enabled** SHALL emit no failure event.

### Requirement 4 — `status` names what it read, and refuses to guess

**User story:** as an operator, I want `the-loop status` to tell me which config and
which state root it is reporting on, and to warn me when a second root also holds
state, so I am never shown one instance's files as another's.

#### Acceptance criteria (EARS)

1. `the-loop status` SHALL print the resolved config path and the resolved state root.
2. WHEN a directory other than the resolved root also holds a poller heartbeat THEN
   `status` SHALL name that directory as a conflicting root rather than silently
   ignoring it, and SHALL state which one it reported.
3. The conflicting-root notice SHALL NOT change `status`'s exit code: it is an
   observation about the filesystem, not a statement about whether the enabled services
   are running.

### Requirement 5 — supervision is documented as the operator's job

**User story:** as an operator, I want the docs to say plainly that `the-loop start` is
not a supervisor and to hand me the unit file, so that a durable loop is something I can
set up rather than something I assume.

#### Acceptance criteria (EARS)

1. The documentation SHALL state that `the-loop start` starts the services once and
   does not restart them, and SHALL NOT imply that it is sufficient for a durable loop.
2. The documentation SHALL provide a copy-pasteable `systemd` user unit and a cron form
   for the `--once` poller, and SHALL name the health check a supervisor should watch.

## Security considerations

The bug is **availability**-relevant, not confidentiality-relevant: the split root makes
the-loop stop doing its job while reporting that it is doing it. Nothing here widens a
trust boundary, and the change removes one class of surprise rather than adding a
surface.

| Abuse case | Boundary | How it fails closed |
|---|---|---|
| AC1 — a caller sets `THE_LOOP_CLI_CONFIG` in a spawned child to point the daemon at a config it chose | process spawn | The value is only ever the path **this process already resolved** — the issue-222 property `schedule_restart` already holds. No request, comment or config value reaches the variable, and the child's own `--config` still takes precedence over it. |
| AC2 — a `state.root` in a hand-written config escapes to somewhere it should not write (`/`, another user's home) | config file | Unchanged authority: `state.root` was already an operator-written path used verbatim when absolute. Anchoring a *relative* root narrows where it can land (beside the config) rather than widening it. |
| AC3 — `/api/v1/health` becomes an unauthenticated inventory of the host (paths, pids) | the API's network boundary | The response gains the **config path** and the **state root** — two paths the caller already had to know to reach this loopback service, and which `GET /api/v1/config` already serves in full to the same callers. No pid, no token, no secret, no env. The exposure guard (`service.exposed`) and the gateway are unchanged. |
| AC4 — the degraded body is used to make an unrelated CLI command hammer a live service | `client.ensure_service` | R2.4: a degraded health is still HTTP 200, so `healthy()` still means "reachable" and the auto-start loop terminates exactly as it does today. |
| AC5 — the new `ingress.hosted_failed` event leaks a secret through its reason string | the event log | The reasons are the ones already logged: a lock holder's pid, a pidfile path, "polling.sources is empty", a missing env **variable name**. No variable's *value* is recorded, and the existing `redact` discipline over the event log is unchanged. |

## Out of scope

- **Shipping a supervisor.** R5 documents the unit; the-loop does not become a process
  manager, install a systemd unit, or grow a `--restart` flag. That is a separate ask
  with its own failure modes, and the reporter ranked it last.
- **Migrating an existing split state.** When two roots are found, the-loop **names**
  both and reports which it used (R4.2); it does not merge, copy or delete either.
  Moving state is destructive and is the operator's call.
- **`routing.registryDir` / `eventLog.path` / `webhooks.ghWebhook.pidfile`.** These are
  explicit overrides used verbatim today and stay verbatim; only the `state.root`
  *default* they fall back to becomes anchored.
- The poller's internal `_state_layout()` / `_config_path()` shape. With R1.5 the daemon
  resolves the operator's config, so re-deriving it from module state is no longer a
  divergence; threading a layout parameter through the poller is a refactor this bug
  does not need.

## Open questions

None. The reporter's five asks are the five requirements; items 1–4 are the outage and
item 5 is the documentation gap it exposed.
