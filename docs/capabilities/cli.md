# Capability: cli

> The `the-loop` Python CLI companion — lightweight, one-dependency, extensible
> quality-of-life commands the plugin (and users) can call.

## What it is

A Python package (`cli/`, import package `the_loop`, console script `the-loop`) with an
extensible command registry. Python is deliberate: it leaves room for future
self-learning/ML capabilities.

## Current behaviour

- The CLI SHALL register commands via an extensible registry (`the_loop.commands`).
- The CLI SHALL have **exactly one** runtime dependency, `pyyaml>=6`, and be stdlib
  otherwise. PyYAML is REQUIRED, not an extra: the CLI config, the harness config and
  every default the daemons read are YAML, so a missing parser used to degrade each
  read to empty, with the cause logged at `debug` or not at all — leaving `poll` to
  exit with "no polling sources configured" against a file that listed sources
  (issue-97, decision-038).
  The `[config]` extra that once carried it SHALL be retained as an empty, deprecated
  no-op so pinned install lines keep resolving.
- `the-loop --version` SHALL report the installed package version, derived from package
  metadata (`importlib.metadata.version("the-loopy-one")`) rather than a hardcoded string,
  so it always tracks the actually-installed release (issue-78).
- The lifecycle surface SHALL run/stop the HMAC-verified GitHub webhook
  receiver (see [webhook-triggers](webhook-triggers.md)).
- `the-loop sessions register|list|attach|close` SHALL manage the work-item ↔
  harness-session registry used for webhook routing.
- `the-loop sessions start|pause|resume|stop|cleanup` SHALL give an operator with shell
  access the **same five commands** an authorized user issues by keyword in a comment
  (issue-106, issue-186, see [webhook-triggers](webhook-triggers.md)): `start` spawns
  through the same dispatcher the daemon uses — workspace checkout, harness trust, tmux
  hosting, session announcement — or resumes a paused session; `stop` takes the normal
  close path; `cleanup` releases the work item's local resources through that same
  dispatcher (every endpoint's tmux session, the workspace checkout, the machine-local
  record), keeping the portable record and touching nothing remote, and reports each
  irreversible fact on its own line. Each invocation SHALL record the command in that work item's portable
  record (`<state.root>/portable/<slug>.json`, `control` section — issue-128) and SHALL
  post the **same keyword** back to the work item
  so its thread stays the full record of who asked for what. That comment SHALL carry
  the loop-prevention marker (`authz.mark_self_authored`), because the action has
  already been applied locally and neither ingress path may read it back and re-apply
  it. Posting is best-effort — `--no-comment` skips it, and a missing/failing `gh`
  warns without undoing the local action. `sessions list` SHALL show each session's
  status (including `paused`) and its last control command.
- `the-loop ask --work-item <ref> --question <text>|--question-file <path>` SHALL post
  an agent's question on its work item with the loop-prevention marker stamped
  **centrally** and SHALL record the wait as a `session.awaiting_input` event —
  emitted (as a warning, `comment_posted: false`) even when `gh` fails, since the agent
  is waiting either way (issue-208, [decision-078](../decisions/decision-078.md)). It
  SHALL execute in-process rather than through the service: the escalation path must
  not depend on anything else of the-loop running. The answer arrives as a forwarded
  ticket comment, or straight into the pane via `POST /api/v1/sessions/reply` (see
  [control-plane](control-plane.md)).
- `the-loop sessions reset --work-item <ref> [--work-item …] | --all [--dry-run]` SHALL
  remove everything this machine remembers about a work item (issue-137,
  [decision-050](../decisions/decision-050.md)) — the verb for "I fixed a bug in the-loop
  itself; start this item over on the new code". A **live** session (active or paused)
  SHALL first be ended through the same close path `stop` takes, so no harness is left
  running against records that have gone; the session record SHALL then be **deleted**
  rather than closed (a closed record still lists and still attaches, which is the "still
  remembered" a reset ends); the `control` section SHALL be cleared, which **disarms** the
  work item, and the `poll` section cleared, which makes its thread first-sight again. The
  portable sections SHALL be cleared through the work-item store, never by unlinking the
  file, so a pre-issue-128 tree leaves a `sealed` record instead of resurrecting what was
  just removed. The command SHALL post **no** comment on the ticket, and there SHALL be no
  `reset` control keyword: a comment must not be able to delete local state, and posting
  `stop-execution` would record intent the reset has just cleared. The event log SHALL be
  **appended to and never rewritten** — one `session.reset` per work item, including when
  nothing was found. A bare `reset` (no selector) SHALL be refused rather than read as
  "everything", one invalid ref SHALL reset none of them, one failing work item SHALL NOT
  strand the rest, and `--dry-run` SHALL report the same list while changing nothing and
  emitting nothing. The operator SHALL be warned when the receiver is running (it can write
  poll state back) and when `control.requireStartCommand` is false (a first-sight item may
  re-spawn on the next poll cycle) — warnings, not refusals. Nothing in the **repository**
  is touched: `docs/specs/<id>/graph-state.json` is checked in and re-derived from the
  artifacts.
- Everything the CLI **generates** SHALL live under one configured root
  (`state.root`, default `.the-loop`, issue-106), organised by **portability** rather
  than by which component writes it (issue-128, decision-046): `<root>/portable/<slug>.json`
  is one record per work item carrying a `control` section (the last authorized
  start/stop/pause/resume) and a `poll` section (which comments have been seen);
  `<root>/local/<slug>.json` is that work item's session handle; the event log and
  pidfile keep their places. The root supplies **defaults only** for the local paths —
  an explicitly configured `registryDir`, `eventLog.path` or `pidfile` is used verbatim —
  while `portable/` always follows the root, so "where is the half I track?" has one
  answer. Two components write a work-item record, so every write SHALL replace only its
  own section (read-modify-write): a poll cycle must never erase a control command the
  other ingress recorded a moment earlier. A session listing SHALL consider only the
  files the registry itself wrote (`<slug>.json`, i.e. a name ending in `-<number>`) and
  SHALL ignore its neighbours silently, so the "skipping unreadable registry file"
  warning stays reserved for genuine corruption (issue-111).
- Because `portable/` is the one generated directory that is **tracked**, it SHALL be
  readable as well as writable (issue-130, decision-047): every record SHALL carry a
  `url` beside its `ref`, and the directory SHALL carry `index.json` — one entry per
  record (`ref`, `url`, `file`, the `sections` it holds, `sealed` when it is an upgrade
  tombstone), ordered by `ref`. The index SHALL be **derived** by scanning the directory
  on every write and removal, SHALL be removed with the last record, and SHALL be read by
  nothing in the-loop, so a stale, hand-edited or forged index changes no behaviour and
  the next write repairs it; a failure to write it SHALL be logged and SHALL NOT fail the
  record write it accompanies. A URL SHALL be derived only for a `github` ref whose owner
  and repo match GitHub's own name shape, and SHALL be omitted otherwise rather than
  guessed.
- A work-item ref SHALL be `<provider>:[<host>/]<owner>/<repo>#<number>` (issue-130,
  decision-048): a work item that does not live on the provider's default host names that
  host, and one that does leaves it unwritten — so every ref written before this is
  unchanged, and so is its file name. Both ingresses SHALL identify the host **from the
  event**, never from configuration or assumption: the webhook receiver from the
  repository's `html_url` (falling back to the issue/PR URL, which is what the poller's
  synthesised payloads carry), and a polled work item from its own URL. The two
  derivations SHALL agree, because one keys the routing and the other keys the poll
  ledger. A path that is neither `<owner>/<repo>` nor `<host>/<owner>/<repo>` — where a
  host is a dotted name or one with an explicit port — SHALL be rejected as a malformed
  ref rather than read as a work item whose identity is a path fragment.
- The pre-issue-128 locations (`<root>/sessions/`, `<root>/sessions/control/`,
  `<root>/sessions/poll-state.json`, and the pre-issue-106 `.the-loop/poll-state.json`)
  SHALL still be **read** when a work item's new record has no such section, and written
  forward on the next write, so an upgrade neither re-baselines a watched thread nor
  forgets what an authorized user armed. Nothing writes to them. `polling.stateFile`
  SHALL be **removed** — a file path cannot address a per-work-item ledger — and a config
  still declaring it SHALL be refused with the replacement named, never ignored.
- Every generated path SHALL be classified as **portable** or **local**
  (`the_loop.state.GENERATED_PATHS`, issue-128, decision-046): the work-item records are
  facts about the work — what was armed, which comments have been seen — and travel to
  another machine; the session registry, the event log and the pidfile are handles to the
  machine that made them and SHALL NOT be tracked. The session registry is excluded
  emphatically: a copied record is still counted **live** by `find_by_work_item`, so the
  duplicate guard would refuse the spawn the new machine needs and route events to a
  conversation that is not there — and it carries an absolute `cwd` and a resumable
  session id besides. The classification SHALL be declared as data and pinned by a test,
  so a new generated path cannot be added without answering whether it travels, and SHALL
  be published as a `.gitignore` block this repository itself uses
  ([state on disk](https://madarauchiha-314.github.io/the-loop/cli/state)). the-loop SHALL
  never commit state on the operator's behalf.
- `the-loop check [<work item>|--all]` SHALL evaluate a work item's nodes against its
  checked-in artifacts and report what is unmet (`--format table|json`). It SHALL be
  **pure** — no network, no subprocess, no mutation — which is what lets the same code run
  on every harness turn *and* in CI, so the gate is the runtime rather than a
  reimplementation of it. `--recompute` ignores stored graph state and derives the verdict
  from the artifacts alone.
- `the-loop graph show|status|advance|run|force` SHALL inspect and drive the process graph
  (see [process-graph](process-graph.md)). `run` is bounded by `--max-nodes` and detects
  loops — a runaway loop is the one failure mode a deterministic driver can still have, so
  it gets an explicit ceiling rather than trust. `force` is the authorized-operator escape
  hatch: it requires a reason and moves the pointer without ever forging the bypassed
  gate's verdict. `--ref` is optional on every verb that runs hooks: omitted, it is
  **derived** from the repository's `ticketing.github` plus the `issue-<n>` work-item id
  (issue-194). WHEN a verb's outbound call could not be made — no derivable ref, no
  credentials, an outage — THEN the command SHALL say so on stdout as a `warning:` /
  `WARNING:` line and SHALL keep its exit code: a degraded side effect is not a failed
  verb, and it is not a silent one either.
- The CLI config SHALL carry a `version`, and the CLI SHALL **refuse to run** against a
  config older than the current schema version rather than guessing at the old shape
  (issue-109). Per-provider settings SHALL live under one `integrations` block —
  `integrations.github.cli.binary` replaces the `ghBinary` key that was previously
  duplicated across three consumers. Dispatch policy SHALL live under a **top-level**
  `routing` key, not under `webhooks.ghWebhook`: the poller and `the-loop sessions`
  dispatch on the same block, so nesting it under one ingress misstated its scope
  (issue-142). Both are **breaking** changes, handled by `/the-loop:upgrade-the-loop`,
  which shells out to `the-loop migrate-config`.
- The CLI SHALL declare a second runtime dependency, `slack-sdk`, only as an **optional
  extra**: it is Slack's official SDK and has zero required dependencies of its own, but
  the dependency-free `webhook` transport remains available so the base install stays
  one-dependency.
- The Slack incoming-webhook URL SHALL be resolvable from **either** the CLI config
  (`integrations.slack.url`) or the environment (`integrations.slack.urlEnv`, default
  `THE_LOOP_SLACK_WEBHOOK_URL`), with the **config taking precedence** — otherwise the
  effective configuration would depend on ambient environment and reading the file would
  not tell you where a notification goes (issue-203, decision-075). An empty `url` counts
  as absent and falls back. Both transports resolve through the same method, so they
  cannot drift. WHEN neither source is set THEN the failure SHALL name **both** remedies
  and never the URL itself. This carve-out is Slack's alone: a webhook URL is post rights
  to one channel, so its secrecy is the operator's call to price, while
  `github.api.tokenEnv` and `webhooks.ghWebhook.secretEnv` remain **env-only**.
- `the-loop scenarios` SHALL output the table of every Gherkin scenario covered by the
  integration tests (`--format table|markdown|json`; see
  [testing-and-contracts](testing-and-contracts.md)).
- `the-loop instructions` SHALL report every doc registered in `customInstructions.docs`,
  in configured order, with its configured path, resolved absolute path, `notes` and state
  (`present` / `missing` / `unreadable` / `invalid`), in `--format table|markdown|json`.
  Everything not `present` counts as unresolved, and `customInstructions.onMissing`
  decides the exit code (`error` → 1, `warn`/`ignore` → 0) independently of the format.
  Like `check` and `scenarios` it is repo-scoped and pure — filesystem reads only — and it
  SHALL report facts *about* each doc, never its contents (see
  [spec-workflow](spec-workflow.md)).
- `the-loop critic list|run` SHALL list the configured critic harnesses and run **one**
  named critic-review round, printing its result as a single JSON envelope on stdout — the
  seam by which the running harness hands work to a *different* harness and reads back what
  it said (see [review-loop](review-loop.md)). Like `check` and `scenarios` it is
  repo-scoped: it reads the harness config of the project it is invoked in, and is no part
  of the daemon (decision-032).
- `the-loop events` SHALL query the structured JSONL event log of the CLI's own
  routing/dispatch/session decisions (see [observability](observability.md)).
- `the-loop install` / `the-loop upgrade` SHALL install and upgrade **the-loop itself** —
  this CLI and the **Claude Code** plugin — at `--scope user` (default) or
  `--scope project`, naming `cli`, `claude` or `all` (default: the CLI plus every harness
  found on `PATH`). Cursor SHALL NOT be a component until issue-157 establishes how a
  Cursor plugin is installed from a terminal (owner decision on PR #153); `the_loop.install`
  is harness-shaped, so adding it is a `BINARIES` entry plus a planner, not a new command. Both verbs SHALL build an ordered **plan of steps**,
  print the exact argv (or file) of each, and report one outcome per step (`applied` ·
  `already` · `skipped` · `failed`, and `planned` under `--dry-run`), exiting non-zero
  only when a step failed; `--dry-run` SHALL be that same plan with the execution left
  out, and `--format json` SHALL emit the same records (issue-152, decision-057).
- Installing a plugin SHALL be delegated to the **harness's own installer** where it has
  one: the-loop SHALL determine that by asking the binary (`<binary> plugin --help`, and
  `plugin install --help` for a `--scope` flag) rather than assuming a version, and SHALL
  pass the requested scope through instead of emulating it. A binary offering
  `plugin marketplace` but no working `plugin install` SHALL count as **no surface** —
  the split is real (Cursor 2.5) and running an install that cannot work would report a
  failure for an absent feature. WHERE no usable surface exists it SHALL fall back only to
  an already-documented route — the decision-054 settings keys, in the user file or
  `<project>/.claude/settings.json` at project scope, through the same non-destructive
  writer — and WHERE a requested scope cannot be expressed it SHALL report the component
  **skipped** with the manual instruction rather than install at a scope that was not
  asked for.
- `the-loop upgrade` SHALL determine how the **running** CLI was installed from where its
  package lives (`uv tool` / `pipx` / `pip`) and use that method's upgrade command; a
  source checkout SHALL be reported skipped, naming the checkout, never installed over
  (issue-78's failure mode, closed from the other side). At project scope the CLI SHALL be
  installed into the project's `.venv` and SHALL NOT modify the project's `pyproject.toml`.
- The marketplace source for both verbs SHALL resolve `--from` → the CLI config's
  `routing.harnessPlugins.marketplaceRepo` → the shipped default, SHALL be validated as
  `owner/repo` before it can reach a command line, a URL or a settings file (an invalid
  value exits 2 and touches nothing), and SHALL be printed in the plan header before
  anything is trusted. Every step SHALL be executed as an argv list with no shell.
- The package SHALL be installable from PyPI as **`the-loopy-one`** (import package
  `the_loop` and the `the-loop` script unchanged; see
  [release-publishing](release-publishing.md)).
- `gh-webhook`/`poll`/`sessions`/`events` SHALL read their defaults from a **CLI
  config** (`cli-config.yaml`) independent of any repo's `.the-loop/harness-config.yaml` (the
  plugin config) — resolved via `--config`/`-c`, else `$THE_LOOP_CLI_CONFIG`, else
  `./.the-loop/cli-config.yaml` (repo-relative, so an operator can track it in a
  chosen repo), else `~/.the-loop/cli-config.yaml`, so the CLI is not tied to a single
  repo (`cli/README.md`, decision-032).
- A repository's harness config SHALL configure work done **on that repository** and
  SHALL NOT configure the daemon itself (decision-044). Concretely: the daemon's graph
  coupling reads a work item's own checkout for `workflow.phaseLabelPrefix`,
  `workflow.specDir` and `notifications` — after `graphlink` has proved via the checkout's
  `origin` remote that it is that repository's — while `authorizedUsers`, a poll source's
  `repos` and every other ingress setting remain CLI-config-only with no fallback.
- The CLI SHALL read a repository's harness config in exactly one module
  (`the_loop.harness_config`), which SHALL declare its complete read surface as data
  (`READS`); a test SHALL fail the build when a key is read that is not declared, when a
  declared key is undocumented, or when any other module opens the file.

- **`the-loop start|stop|status|restart` SHALL be the whole system's lifecycle surface**
  (issue-228, decision-084). `start` reads the CLI config and starts, detached, every
  service it enables — the control-plane service (`service.enabled`, default on, with
  the MCP endpoint mounted per `service.mcp.enabled`), the webhook receiver
  (`webhooks.ghWebhook.enabled`, default off) and the poller (`polling.enabled`,
  default off) — reporting one outcome per service
  (`started | already-running | disabled | misconfigured | failed`, an enabled poller
  with no `polling.sources` being the misconfigured case) and exiting `0` only when
  every enabled service came up; one service's failure SHALL NOT hide the others'
  outcomes. `stop` SHALL stop every running service regardless of the `enabled` flags.
  `restart` SHALL compose stop → start, `--with-upgrade` running the issue-152
  installer plan (CLI component only) in between — a failed upgrade is reported and the
  start half still runs. `POST /api/v1/restart` SHALL schedule the same restart as a
  detached, fixed-argv process and answer immediately. The `poll` command is removed;
  `python -m the_loop.daemon_entry poller [--once]` is the foreground/cron form, running
  the same relocated loop (`the_loop.poller.daemon`); the `gh-webhook` and `service`
  commands are removed with it (owner review on PR #229 — *"It should all fold into
  `the-loop start`"*), the receiver's run loop relocated the same way
  (`the_loop.webhook.daemon`, `daemon_entry gh-webhook` as its foreground form).
- **`start` SHALL boot one process by default** (issue-231, decision-084 §8): with
  the service enabled and `service.hostIngresses` true (the default), the enabled
  ingresses run as threads inside the service's lifespan — one pid, one logfile —
  each still holding its own pidfile flock under the service's pid, so
  `status`/`stop`, the single-instance guarantee and the daemons API answer
  unchanged. Hosted-ness SHALL be detected from the lock (holder pid equals the
  service's), never recorded in a file; an ingress lock already held by another
  process SHALL be skipped with a warning, never fought over; an enabled poller
  with no sources SHALL refuse to host while the service keeps serving; and `stop`
  SHALL report a hosted ingress stopped only once its lock is released.
  `hostIngresses: false` restores one process per enabled service, and a disabled
  service always means standalone ingresses.
- Every core-capability command SHALL execute through the control-plane service as
  its only mode (issue-161). The exceptions are inherent, not transitional:
  `sessions attach` hands the terminal to tmux, `sessions reset` must work when
  nothing is running, the lifecycle commands and the daemon entry point run the
  processes themselves, and the bootstrap commands (`install`, `upgrade`,
  `migrate-config`, `--version`) precede any service. See
  [control-plane](control-plane.md), the capability that owns this behaviour.

- **A start SHALL be honest** (issue-191, re-shaped by issue-228): `the-loop start`
  reports a daemon as started only once it holds its pidfile lock (the service, only
  once `/health` answers), so a process that exits during startup is a reported
  failure pointing at its logfile — never a silent one. Daemons are spawned into their
  own session with stdout/stderr appended to `<state.root>/logs/`, and the working
  directory is never changed — every path the-loop resolves is relative to it.
- The poller's pidfile SHALL be written by the surviving process under the
  single-instance lock, and a pidfile no live poller holds SHALL be
  reported as stale and removed by the next poller start rather than left for the operator.
- **`the-loop status` SHALL answer "is each service running, and is the poller making
  progress"** in one command: per service enabled/running/pid (plus the service's URL,
  health and MCP exposure), and for the poller `startedAt`, `lastCycleAt`
  and the last cycle's counters, as text or `--format json`, exiting `0` iff every
  enabled service is running. **Liveness and the reported pid SHALL come from the lock
  and never from the heartbeat** — the only formulation immune to pid reuse, and the only
  one a file cannot forge. The poller SHALL record that heartbeat at
  `<state.root>/poll-status.json` after every cycle, atomically; a heartbeat that cannot be
  written SHALL warn once and SHALL NOT interrupt polling, and an absent or unreadable one
  SHALL cost only the progress lines. The same facts SHALL be carried by the control
  plane's `daemon_status`.
- **The heartbeat SHALL NOT carry a pid** (issue-205, [decision-076](../decisions/decision-076.md)):
  the pidfile is the single source of truth for which process is polling, and a `pid` left
  in a heartbeat by an older poller SHALL be read without error and ignored. The two files
  SHALL remain separate — the heartbeat's atomic rewrite replaces the inode the lock is
  held on, their lifetimes are opposite (the pidfile is removed on release, the heartbeat
  is kept), and so are their failure policies (a pidfile that cannot be written aborts the
  start; a heartbeat that cannot be written is swallowed).
- A daemon started **by the control plane** SHALL have its output redirected to that
  daemon's logfile rather than to `/dev/null` — no start path silently discards the log.

## Design

[CLI documentation](https://madarauchiha-314.github.io/the-loop/cli/) (source: [`docs/cli/`](../cli/)) ·
[`cli/README.md`](../../cli/README.md) (the PyPI package readme) ·
[architecture § CLI companion](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-228 | The CLI's lifecycle became one surface (2026-08-14): `the-loop start\|stop\|status\|restart` compose the control-plane service, webhook receiver and poller per new per-service `enabled` flags (service + MCP on by default, ingresses opt-in), the `poll`, `gh-webhook` and `service` commands were removed with the run loops relocated to `the_loop.poller.daemon` / `the_loop.webhook.daemon` (`daemon_entry <poller\|gh-webhook> [--once]` is the foreground/cron form; the fold of the latter two is the owner's PR #229 review), the issue-191 double-fork went with them, `restart --with-upgrade` reuses the issue-152 installer plan, and `service.enabled: false` also refuses implicit auto-start. Amended in the same PR (issue-231, owner review round 2): `service.hostIngresses` (default true) makes `start` boot one process — the enabled ingresses run as threads inside the service, each keeping its own pidfile flock under the service's pid, hosted-ness detected from the lock and never recorded | [spec](../specs/issue-228/), [decision-084](../decisions/decision-084.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/228), [issue-231](https://github.com/MadaraUchiha-314/the-loop/issues/231) |
| issue-208 | `the-loop ask` joins the CLI: an agent's question is posted with the loop-prevention marker stamped centrally and the wait recorded as `session.awaiting_input`; runs in-process because the escalation path must not depend on a running service | [spec](../specs/issue-208/), [decision-078](../decisions/decision-078.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/208) |
| issue-205 | The poller's heartbeat stopped carrying a `pid` nothing read: `poll.pid` — the flock — is the single source of truth for which process is polling, and an older heartbeat's pid is now dropped on read. The two files stay separate because the heartbeat's atomic rewrite would free the lock it is held on | [spec](../specs/issue-205/), [decision-076](../decisions/decision-076.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/205) |
| issue-203 | `integrations.slack` gained an optional inline `url`, taking precedence over `urlEnv`, so the one value that turns notifications on stops living outside every config file the-loop owns — and a resolution failure now names both remedies instead of only the env var. Slack's webhook URL alone; tokens and signing secrets stay env-only | [spec](../specs/issue-203/), [decision-075](../decisions/decision-075.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/203) |
| issue-194 | `graph advance`/`run`/`skip`/`force` stopped posting nothing when `--ref` was omitted: the ref is derived from the repository's `ticketing.github` plus the `issue-<n>` id, and an outbound hook that could not do its job now prints a `warning:` line (and records `graph.hook_degraded`) instead of leaving a clean `wait` over a ticket nobody was asked | [spec](../specs/issue-194/), [process-graph](process-graph.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/194) |
| issue-191 | `poll start --daemon` detaches for real (double-fork + `setsid`, stdout/stderr to `<state.root>/logs/poller.out`, pidfile written after the final fork under the lock), reports startup success or failure to its caller over a handshake instead of into a logfile, removes a stale pidfile instead of leaving it, and gains `poll status` — liveness from the lock, progress from a new per-cycle heartbeat, exit `0`/`1` so it is a health check. Control-plane starts log to a file instead of `/dev/null` | [spec](../specs/issue-191/), [decision-072](../decisions/decision-072.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/191) |
| issue-186 | `sessions cleanup` — a fifth control verb (CLI, HTTP and MCP) that releases a work item's local resources through the daemon's own dispatcher and keeps the portable record, unlike `reset` | [spec](../specs/issue-186/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/186) |
| issue-161 | Re-layered as core → API → clients: `the_loop.core` facade, the control-plane service (`service start\|stop\|status`, no extras — it ships in the base install), every core-capability command routed through it, and the `/mcp` endpoint on the official MCP SDK. The UI was descoped from this work item on owner review | [spec](../specs/issue-161/), [decision-058](../decisions/decision-058.md), [control-plane](control-plane.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/161) |
| issue-156 | Process runner removed; tmux is the only runner (2026-08-05): `sessions start` spawns tmux-hosted sessions unconditionally — there is no configured runner to pick | [spec](../specs/issue-156/), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/156) |
| issue-152 | Added `install` and `upgrade`: one plan-then-execute implementation, two verbs, covering the CLI and the **Claude Code** plugin at user or project scope. Drives the harness's own plugin CLI (probed, not assumed — a marketplace command without a working `plugin install` counts as no surface), falls back to the decision-054 settings keys, detects how the running CLI was installed, and reports every step's argv and outcome — `--dry-run` being the same plan minus the execution. Cursor parked on review and split out as issue-157 | [spec](../specs/issue-152/), [decision-057](../decisions/decision-057.md), [distribution](distribution.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/152) |
| issue-142 | `webhooks.ghWebhook.routing` promoted to a top-level `routing` through the version-gated config migration (`0.4.0`), and the import seam that expressed the same misfiling removed: `poll` and `sessions` read dispatch policy through `cli_config.load_routing_config` instead of importing the webhook command's helper. A relocation only — no option's name, default or behaviour changed | [spec](../specs/issue-142/), [decision-053](../decisions/decision-053.md), [webhook-triggers](webhook-triggers.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/142) |
| issue-137 | Added `sessions reset`: one, several or all work items lose their session record, control and poll sections (and their checkout, per the close policy) so a work item starts over after a CLI fix. Composes the existing close and section-clearing paths — the seal rule is what stops a pre-issue-128 record coming back — adds `SessionRegistry.forget`, posts nothing to the ticket, and appends `session.reset` to a log it cannot rewrite | [spec](../specs/issue-137/), [decision-050](../decisions/decision-050.md), [interactive-sessions](interactive-sessions.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/137) |
| issue-132 | Added `instructions`, the sixth harness-config read: it resolves every doc registered in `customInstructions.docs` and turns `onMissing` into an exit code, so a mistyped path stops being silent. Reports facts about each doc, never its contents | [spec](../specs/issue-132/), [decision-049](../decisions/decision-049.md), [spec-workflow](spec-workflow.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/132) |
| issue-130 | `portable/` made readable: a derived `index.json` listing every record (ref, url, file, sections), rebuilt on every write and read by nothing, plus a `url` beside each record's `ref`. On PR review, refs learned about **hosts** — `[<host>/]<owner>/<repo>`, identified at both ingresses from the event's own URLs — so a GitHub Enterprise work item links, and is identified, correctly | [spec](../specs/issue-130/), [decision-047](../decisions/decision-047.md), [decision-048](../decisions/decision-048.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/130) |
| issue-128 | Generated state classified portable vs local (`GENERATED_PATHS`), documented file by file in `docs/cli/state.md`, and **reorganised by that classification**: one `portable/<slug>.json` per work item (control + poll, read-modify-write) tracked in git, machine-local handles under `local/`, three writer-shaped stores gone, `polling.stateFile` retired through the config migration, and the old locations read forward on upgrade | [spec](../specs/issue-128/), [decision-046](../decisions/decision-046.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/128) |
| issue-121 | The harness-config read surface stated as a direction rule and pinned: one reader module (`the_loop.harness_config`) with a declared `READS` tuple replacing three duplicated readers, a test asserting it against the schema and the docs, and the four pages that claimed the daemon never reads a repo's harness config corrected — it has, on the `graphlink` path, since issue-113 | [spec](../specs/issue-121/), [decision-044](../decisions/decision-044.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/121) |
| issue-117 | Documented as a product: an onboarding path plus one page per command under `docs/cli/`, every config option under `docs/config/cli/`, and a parity test that fails when a registered command has no page or a documented key is absent from the schema. `check`, `graph` and `migrate-config` documented for the first time; the `integrations`, `routing.workspace`, `routing.graph` and `polling.maxRetries` blocks written up; the removed `ghBinary` deleted from the docs | [spec](../specs/issue-117/), [documentation](documentation.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/117) |
| issue-111 | Session listings recognise the registry's own files instead of every `*.json` in the shared `<root>/sessions/` directory, so `poll-state.json` no longer reports as a corrupt registry entry on every poll cycle | [spec](../specs/issue-111/), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/111) |
| issue-109 | Added `check` and `graph` (the process-graph runtime), the `integrations` config block with configurable transports, a `version`-gated **breaking** CLI-config migration retiring `ghBinary`, and the `slack` extra | [spec](../specs/issue-109/), [process-graph](process-graph.md), [decision-041](../decisions/decision-041.md), [decision-042](../decisions/decision-042.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/109) |
| issue-97 | PyYAML promoted from the `[config]` extra to a required runtime dependency; the three silent `ImportError` fallbacks removed and the zero-runtime-dependency guarantee retired | [spec](../specs/issue-97/), [decision-038](../decisions/decision-038.md) |
| issue-82 | Plugin config renamed `config.yaml` → `harness-config.yaml` (`scenarios` reads the new name with a pre-rename fallback); CLI config gained operator-declared `collaborators` + daemon-side `notifications` event filters | [decision-035](../decisions/decision-035.md) |
| issue-78 | `--version` derives from package metadata instead of a hardcoded string that had frozen at 0.1.0 | [spec](../specs/issue-78/) |
| issue-63 | Split the CLI daemon's config (`webhooks`/`polling`/`eventLog`) out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-50 | Added the structured event log and the `events` query command | [spec](../specs/issue-50/), [decision-025](../decisions/decision-025.md) |
| issue-21 | Published to PyPI as `the-loopy-one` with automatic semantic releases | [spec](../specs/issue-21/), [decision-019](../decisions/decision-019.md) |
| issue-106 | `sessions start`/`pause`/`resume`/`stop` (CLI parity with the comment keywords, mirrored back to the ticket), `paused` sessions in `sessions list`, and one `state.root` for every generated file | [spec](../specs/issue-106/), [decision-040](../decisions/decision-040.md), [issue](https://github.com/MadaraUchiha-314/the-loop/issues/106) |
| issue-15 | Added `sessions` registry commands and webhook `--route` dispatch | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-11 | Added `scenarios` (queryable integration-test scenario table) | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
| issue-1 | Established the CLI skeleton and the `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
