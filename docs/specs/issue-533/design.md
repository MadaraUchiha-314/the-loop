---
type: design
phase: design
workItem: "github:MadaraUchiha-314/the-loop#533"
status: draft                # the design-approval gate locks it (declared skipped here; review is on the PR)
approvedBy: []
collaborators: [engineer, security]
overrides: {}
riskTier: 4
---

<!-- Authored per the the-loop:writing skill. -->

# Design: opt-in session credentials, never on argv

> Phase 2 of 4. Derived from [`requirements.md`](requirements.md). Reviewed together
> with [`testing-plan.md`](testing-plan.md) on PR #535.

## Overview

Four changes, each small, all behind one config key that defaults to empty:

1. **Config → boundary.** `envstate` parses `env.sessionCredentials` into
   `SessionCredential` entries carried on `SessionEnvironment`, and resolves them per
   work item into an `inherit` mapping (name → value) plus the names that stay removed.
2. **Delivery.** `TmuxRunner` writes `inherit` to a `0600` file under
   `<state.root>/local/session-credentials/` and prefixes the pane command with a fixed
   `sh -c` loader that sources the file, deletes it and `exec`s the existing
   `env -u … harness` command. Only the path is on argv.
3. **Scrubbing.** A new module, `sessioncreds`, owns the configured values and a
   `scrub(text)` that masks them; the service applies it to every caller-text field of
   the session-facing routes, and `EventLog.emit` applies it to every string it writes.
4. **Visibility and drift.** `compare()` checks `inherit` like `forward`; the drift
   rows and `sessions list` gain a `credentials` map (name → fingerprint) read from the
   live process; the runner emits one warning event per spawn that hands one over.

```mermaid
sequenceDiagram
  participant D as daemon (dispatcher / restart)
  participant E as envstate
  participant R as TmuxRunner
  participant F as 0600 file<br/>state.root/local/session-credentials
  participant T as tmux client → server
  participant P as pane: sh loader
  participant H as harness
  D->>E: spawn_environment(config)
  E-->>D: SessionEnvironment(forward, remove, credentials)
  D->>R: spawn_in(target, …, work_item)
  R->>E: env.for_work_item(ref) → inherit, remove
  R->>F: write NAME='value' lines (O_EXCL, 0600)
  R->>T: new-session … -- sh -c LOADER sh <path> env -u … harness …<br/>(client env minus remove ∪ inherit names)
  T->>P: fork pane
  P->>F: . <path>; rm -f <path>
  P->>H: exec env -u … harness (NAME=value in environ)
  R-->>D: ok → eventlog warning session.credentials_inherited (names)
  Note over R,F: on failure the runner deletes the file;<br/>every spawn sweeps files older than 10 min
```

## Architecture

Nothing new runs. The pieces sit where issue-482 put the boundary:

| Concern | Module | Change |
|---|---|---|
| Parse & resolve | `cli/the_loop/envstate.py` | `SessionCredential`, `session_credentials(config)`, `SessionEnvironment.credentials` + `.for_work_item()`, `compare()` reads `inherit` |
| Deliver | `cli/the_loop/runner.py` | `_credential_file()`, loader prefix in `_harness_command`, client env strips inherit names, sweep, event |
| Scrub | `cli/the_loop/sessioncreds.py` (new) | `current_values(config)`, `scrub(text)`, `remember(value)` |
| Apply scrub | `cli/the_loop/api/routes.py`, `cli/the_loop/eventlog.py` | scrub caller text on the session routes; scrub strings in `EventLog.emit` |
| Visibility | `cli/the_loop/core/sessions.py`, `core/lifecycle.py`, `commands/sessions_cmd.py` | `credentials` per row, a status line, a list column |
| Schema & docs | `schemas/cli-config.schema.json`, `docs/…` | the key, the trade-off |

## Components & interfaces

### `envstate` — the boundary

```python
@dataclass(frozen=True)
class SessionCredential:
    name: str                     # the variable the session sees
    source: str                   # `from`; daemon-side
    value: Optional[str]          # resolved now; None = source unset (R1.4)
    repositories: Tuple[str, ...] # normalised "host/owner/repo", lowercase; () = any

@dataclass(frozen=True)
class SessionEnvironment:
    forward: Dict[str, str] = {}
    remove: Tuple[str, ...] = ()
    credentials: Tuple[SessionCredential, ...] = ()   # new, default empty
    inherit: Dict[str, str] = {}                      # new; set by for_work_item

    def for_work_item(self, ref: str) -> "SessionEnvironment": ...
```

- `session_credentials(config, file_values) -> Tuple[SessionCredential, ...]` reads
  `env.sessionCredentials`. Each invalid entry (R1.3), duplicate name (R1.8) is
  skipped with a warning naming the text. `value` comes from `file_values` (the env
  file re-read for this spawn) else `os.environ` (R1.5); unset → `None`. A source in
  `credential_names(config)` warns once per resolution (R1.6). A `name` among
  the-loop's own three identifiers is skipped with a warning (they are set last and
  would clobber it otherwise).
- `session_environment_and_lines` adds the credentials and extends `remove` with every
  entry's `name` and `source` (R2.1, R2.2) — so with **no** work item resolved, the
  boundary is strictly tighter than before. It returns non-`None` when
  `sessionCredentials` is set even without `env.file`/passthrough, so the drift check
  is "configured".
- `for_work_item(ref)` returns a copy with `inherit` = `{c.name: c.value}` for every
  credential whose value is set and whose `repositories` is empty or contains the ref's
  `host/owner/repo` (GitHub refs only; R1.7), and `remove` minus those names. It is the
  **only** place `inherit` is filled, so a caller that forgets it fails closed (nothing
  inherited, names stripped). Called with the same ref twice it is idempotent.
- `compare(wanted, actual)` adds `{n for n, v in inherit.items() if actual.get(n) != v}`
  (R4.1). `_wanted()` renders an inherited name as `NAME (wanted <fingerprint>)`, like a
  forwarded one (R4.3).
- With `sessionCredentials` empty every function returns exactly today's value (R1.2):
  `credentials == ()`, `inherit == {}`, `remove` unchanged.

### `runner` — delivery

`spawn_in` and `respawn_in` change in three lines each:

```python
env = self.spawn_environment().for_work_item(work_item)
cred_path = self._credential_file(target, env.inherit)       # None when nothing to inherit
argv += ["--"] + self._harness_command(adapter, harness_argv, env, cred_path)
result = self._run(argv, timeout, remove=env.remove + tuple(env.inherit))
```

- **`_credential_file(target, inherit) -> Optional[str]`.** Empty `inherit` → `None` and
  no disk touch (R1.2). Else: sweep, then `mkdir(<root>/local/session-credentials,
  0o700)` and chmod it to `0700`, then `os.open(path, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW,
  0o600)` with `path = <dir>/<target>.<secrets.token_hex(8)>.env`, then write one
  `NAME='value'` line per name (single quotes; `'` written as `'\''`), `fsync`, close.
  Any `OSError` → warning naming the names (never values) and `None`: the spawn
  proceeds **without** the credentials, and their names go back into `remove`
  (fail closed; requirements § Fail closed).
- **The loader.** `_harness_command` prefixes, when `cred_path` is set:

  ```
  sh -c 'set -a; [ -r "$1" ] && . "$1"; set +a; rm -f -- "$1"; shift; exec "$@"' sh <path>
  ```

  then the unchanged `env -u <remove…> <binary> <argv…>`. The path stays in `$1`, which
  an assignment in the sourced file cannot change (critic CR1-1: an earlier `f=$1` let a
  credential named `f` redirect the `rm`). The script is a constant;
  the path is the only variable on argv (R3.1, R3.2). `.` runs in the shell itself,
  so the values become exported variables of the process that `exec`s `env`, which
  then `exec`s the harness — the pane's pid becomes the harness's, as today. The file
  is deleted before the harness starts (R3.3). `env -u` never names an inherited
  name, so the values survive it.
- **Client environment.** `_run(..., remove=env.remove + inherit names)`: the `tmux`
  client never carries an inherited name, even when the daemon's own environment
  holds one of the same name (the daemon's `GH_TOKEN`) — so a server this spawn starts
  has neither the value nor the daemon's token in its global environment (R3.5), and
  the hub and other sessions cannot inherit it (R3.6). No `-e` names it, so no tmux
  session environment holds it either.
- **Failure cleanup.** When `_run` fails (including the duplicate-session retry path),
  the runner deletes the file (R3.4). On success it does not — the pane may not have
  read it yet; the pane deletes it.
- **Sweep.** Each `_credential_file` call first removes files in the directory older
  than `CREDENTIAL_FILE_MAX_AGE_SECONDS = 600` (R3.4). A file exists for the
  milliseconds between `new-session` and the pane's `rm`; ten minutes is far past any
  slow start, and bounds what a crash leaves on disk.
- **Event.** After a successful spawn/respawn with a non-empty `inherit`:
  `eventlog.emit("session.credentials_inherited", level="warning", work_item=…,
  tmux_target=…, names=[sorted names])` (R7.2). Names only.
- **State root.** The runner gains `credentials_dir: str` (constructor argument,
  default: resolved from `state.root` via `state.layout_from_config` of the config the
  provider reads). The dispatcher, standing-session and restart constructions pass it.

### `sessioncreds` — the scrubber (new module)

```python
MASK = "<redacted:session-credential>"
def current_values(config: Mapping, config_path: Path) -> FrozenSet[str]
def remember(values: Iterable[str]) -> None     # process-local registry
def scrub(text: str, config: Optional[Mapping] = None) -> str
def scrub_tree(node: Any, values) -> Any        # dicts/lists/strings, for the event log
```

- `current_values` resolves every configured entry's source value now (env file
  re-read, else `os.environ`), ignoring repository scope — any session may hold any of
  them. Values shorter than 8 characters are not masked (they would eat ordinary text;
  the same rule as `redact.scrub`, stricter bound) and warned about once.
- The env-file read is cached on the file's `(path, mtime_ns, size)`, so a busy event
  log does not re-parse it per line, and a rotation (a write changes mtime) is seen on
  the next call (R5.2).
- `remember` keeps every value seen in this process, so a value rotated **out** is
  still masked while a stale session may still hold it.
- `scrub(text)` replaces each value, longest first, with `MASK` (R5.1). With no entries
  configured it returns `text` unchanged without touching disk (R5.3).

### Where the scrub is applied

The service is the seam every session verb crosses (issue-482 R3.2). The routes that
take free text from a caller and post it outward or log it:

| Route | Fields scrubbed |
|---|---|
| `POST /sessions/ask` | `question`, `summary`, `default` |
| `POST /sessions/reply` | `text` |
| `POST /work-items/comments` | `body` |
| `POST /work-items/tickets` | `title`, `body` |
| `POST /work-items/pull-requests` | `title`, `body` |
| `POST /graph/force`, `POST /graph/skip` | `reason` |

One helper, `_scrubbed(body, *fields)`, returns a copy of the request model with those
fields scrubbed; each handler calls it first. Everything downstream (the bus, Slack,
the GitHub/Jira clients, `session.awaiting_input`) then sees masked text.

`EventLog.emit` runs `scrub_tree` over the record before `json.dumps` — defence in depth
for a value that reaches a log line by any other path (a hook's reason, an error
string). It masks the values this process has **remembered** — resolved by a route's
scrub, or handed to a pane by the runner — so it reads no disk and costs nothing when
none is known. The daemon remembers every value it spawns with; the service, every
value it has scrubbed with.

Self-diagnosis already runs `redact.scrub` over its composed issue; that scrub masks the
value of any environment variable whose name contains `TOKEN`/`SECRET`/…, which covers
`the-loop diagnose` run inside a session holding `GH_TOKEN`. `compose_issue` additionally
calls `sessioncreds.scrub` so a credential named without such a word is masked too.

### Visibility

- `_environment_row` adds `credentials: {name: fingerprint}` — for each name in the
  session's resolved `inherit`, the fingerprint of the value the **live process**
  holds (absent when it holds none). `environment_drift` resolves the boundary per
  session with `for_work_item(session.work_item.ref)` (R4.1, R7.1).
- `list_sessions` adds the same `credentials` map to each active session, computed only
  when `sessionCredentials` is configured (otherwise `{}`, and no `/proc` read).
  `sessions list` shows a `Credentials` column (`GH_TOKEN@ab12cd34`) only when some
  row has one, so today's table is unchanged otherwise.
- `status` gains `credentials_line(doc)`: `session credentials: <n> session(s) hold
  GH_TOKEN` — one line, only when some live session holds one, names only (R7.1).

## Data models

**Config** (`env.sessionCredentials`, schema):

```json
{
  "type": "array", "default": [],
  "items": {
    "type": "object", "additionalProperties": false, "required": ["name"],
    "properties": {
      "name":  {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
      "from":  {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_]*$"},
      "repositories": {"type": "array", "items": {"type": "string"}}
    }
  }
}
```

The schema rejects a malformed name at validation time; the runtime warning (R1.3) is
for a config the validator was not run on (hot reload, an SDK caller's dict).

**Delivery file**: `<state.root>/local/session-credentials/<target>.<16 hex>.env`, mode
`0600`, directory `0700`. Content: `NAME='value'\n` per inherited name.

**Event**: `session.credentials_inherited` — `work_item`, `tmux_target`, `names`.

**Drift row** (status, restart): `+ credentials: {NAME: fingerprint}`.

## Error handling

| Situation | Behaviour |
|---|---|
| Entry malformed / duplicate / names an own identifier | skipped, warning names the text |
| Source unset | not inherited, name stays removed, warning names `name` and `from` |
| Repository scope does not match | not inherited, name stays removed, no warning (expected) |
| Directory or file cannot be created `0600` | spawn proceeds without credentials, names removed, warning names the names |
| tmux spawn fails | file deleted by the runner |
| Daemon crash between write and pane read | file swept at the next spawn (≤ 10 min old stays) |
| Loader cannot read the file | harness starts without the credentials; `status` reads it `stale` |
| Value shorter than 8 characters | inherited, **not** scrubbed; warning at resolution says so |

## Security design

How each requirements-phase trust boundary is enforced:

- **Daemon ↔ session.** Only `for_work_item` fills `inherit`, from entries the operator
  named explicitly; `sessionPassthrough` still refuses credential names (R1.9, the
  existing `passthrough_names` is untouched). Every entry's `name` and `from` is in
  `remove` unless inherited, so a source variable never reaches a pane under its own
  name, and a non-matching scope leaves the name stripped (R2).
- **the-loop ↔ tmux.** Values appear in no `-e` flag and no command word: the argv is
  the constant loader, a path, and names. The tmux client's environment drops
  `remove ∪ inherit`, so neither the value nor a same-named daemon token can enter a
  server this spawn starts (R3.1, R3.5, R3.6). Asserted by an integration test on a
  private tmux socket that reads `ps`, `show-environment -g` and a second session.
- **Daemon ↔ disk.** `O_CREAT|O_EXCL|O_NOFOLLOW` with mode `0600` in a `0700`
  directory, under the operator's own `state.root`; a random suffix so names are not
  predictable; deleted by the pane before `exec`, by the runner on failure, by the sweep
  otherwise (R3.2–R3.4). `O_NOFOLLOW` + `O_EXCL` defeat a pre-placed symlink.
- **Loader injection.** The script is a constant; the path is passed as `$1`, never
  interpolated. The file is sourced, so its content is shell: names are validated by
  `NAME_RE` and values are single-quoted with `'` escaped, so a value cannot break out
  of its quotes. A NUL cannot occur in an environment value.
- **Session → outside world.** The service scrubs every caller-text field of the
  session routes before any side effect, and the event log scrubs every string it
  writes (R5). Masks are visible (`<redacted:session-credential>`), never silent.
- **Abuse cases → enforcement.** Each abuse case in the requirements maps to one control
  and one negative test:

  | Abuse case | Control | Test (testing plan) |
  |---|---|---|
  | A1 `ps` shows the value | loader argv carries only a path | T2 `ps -eo args` scan |
  | A2 server keeps it globally | client env drops `remove ∪ inherit` | T2 `show-environment -g` |
  | A3 another user reads the file | `0600`/`0700`, `O_EXCL` + `O_NOFOLLOW`, deleted before `exec` | T1 mode/symlink, T2 file gone |
  | A4 agent pastes the token | route-layer scrub + event-log scrub | T1 route + event-log tests |
  | A5 `sessionPassthrough` forwards it | `passthrough_names` unchanged | T1 existing + new case |
  | A6 `from` is the daemon's token | warning at resolution | T1 caplog |
  | A7 scope mismatch | `for_work_item` leaves the name removed | T1 |

- **Residual.** Text the agent sends with the token itself (`gh`, `git push`, `curl`)
  and a session that sets `THE_LOOP_SERVICE_LOCAL=1` to run a verb in-process with the
  token it holds bypass the service, and with it the scrub. Both are what holding a
  token means; R8's documentation says so and recommends least-privilege tokens.

## Testing strategy

Detailed in [`testing-plan.md`](testing-plan.md). Unit tests per component
(`test_envstate.py`, `test_tmux_runner.py`, a new `test_sessioncreds.py`, the route
tests), and one real-tmux integration test on a private socket that asserts the
acceptance criteria end to end: pane environment, `ps`, global environment, a second
session, the file's mode and removal, and rotation reading `stale`.

## Trade-offs & decisions

- **File + `sh` loader over `tmux update-environment`.** The file keeps tmux out of the
  value's path entirely, works on every tmux the runner supports, and needs nothing in
  the pane but `/bin/sh`. `update-environment`/`set-environment` would put the value in
  tmux's session environment (readable with `show-environment` from any pane on the
  server) and on a `tmux` argv unless sent through the client's environment.
- **`sh` over a Python loader.** A Python loader would need the daemon's interpreter
  path and the package importable from the pane. `sh` is everywhere a pane runs, and
  the quoting needed is one rule.
- **Scrub at the route layer, not at each sink.** There is no single outbound funnel
  (the bus covers comments and asks but not tickets or PRs; the GitHub, Jira and Slack
  clients have separate writers). The routes are the one place session text enters;
  scrubbing there means every sink downstream sees masked text, including ones added
  later. The event log is scrubbed as well because non-session paths can also carry
  text into it.
- **Scrub every configured value, ignoring scope.** Cheaper to reason about than
  per-session scoping, and a value that leaked across a scope is still masked.
- **No routing flag** (R6): out of scope; the issue asks only that routing stay
  unchanged.

## Open questions

None blocking.

## Review comments

> Appended by the-loop's `record-feedback` hook when a human gate approves with
> comments (issue-109).
