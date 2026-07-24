# the-loop CLI

A lightweight, **extensible** command-line companion to the the-loop plugin, written in
Python (stdlib-only core — zero runtime dependencies). Python is intentional: it leaves
room to add self-learning / ML capabilities later (mostly exposed as Python SDKs).

## Install

From PyPI (published as **`the-loopy-one`** — the base name `the-loop` was taken; the
import package and CLI keep the natural `the_loop`/`the-loop`):

```bash
pip install the-loopy-one            # or: uv pip install the-loopy-one
pip install "the-loopy-one[config]"  # + PyYAML, for reading config-file defaults
the-loop --help
```

For local development the-loop uses **uv** (its declared Python package manager). From the
repo root:

```bash
uv sync                     # installs the workspace (this CLI + dev tooling) from uv.lock
uv run the-loop --help      # run the CLI
```

Or install this package on its own with any PEP 517 installer:

```bash
uv pip install -e .            # or: pip install -e .
uv pip install -e ".[config]"  # PyYAML, for reading config-file defaults
uv pip install -e ".[dev]"     # pytest + commitizen
```

This exposes the primary CLI: `the-loop`. Releases are **automatic**: on merge to `main`,
`.github/workflows/release.yml` runs `cz bump` to derive the next version from the
Conventional Commits / PR titles since the last tag (`feat` → minor, `fix` → patch,
`BREAKING CHANGE` → major), tags it, and publishes to PyPI via Trusted Publishing (OIDC —
no stored token). Merges with no `feat`/`fix`/breaking change publish nothing. See
`docs/decisions/decision-019.md`.

## Two independent config files (decision-032)

The-loop's config is split into two files that never overlap keys:

- **Plugin config** — `.the-loop/harness-config.yaml`, installed **per repo** (Claude/Cursor
  plugin), read by `/the-loop:*` commands and the skill: `ticketing`, `workflow`,
  `tooling`, `reviews`, `autonomy`, `security`, `personas`, … Validated against
  `.the-loop/harness-config.schema.json`.
- **CLI config** (`cli-config.yaml`) — read only by this CLI's daemon commands below
  (`gh-webhook`, `poll`, `sessions`, `events`): `webhooks`, `polling`, `eventLog`. The
  CLI is expected to work across multiple repos, so it isn't required to live in any
  one of them — resolved in priority order:

  1. **`--config`/`-c`** — an explicit flag, e.g. `the-loop --config path/to/cli-config.yaml gh-webhook start` (must precede the subcommand).
  2. **`$THE_LOOP_CLI_CONFIG`** — an explicit env var, same priority as `--config`
     (handy for containers/systemd units where a flag is less convenient).
  3. **`./.the-loop/cli-config.yaml`** (repo-relative) — an operator can choose to
     track their CLI config in a specific repo (e.g. a "dev box" repo, checked in and
     versioned) instead of their home directory; picked up automatically when
     `the-loop <command>` runs from that checkout.
  4. **`~/.the-loop/cli-config.yaml`** — the always-available fallback, not tied to
     any repo.

  Validated against `.the-loop/cli-config.schema.json`; a commented starting point
  ships at `skills/the-loop/templates/cli-config.yaml`.

Each command's defaults below note which file they come from. The CLI daemon reads
**only** the CLI config — it never reads a repo's plugin config for anything, including
`routing.authorizedUsers` (who may trigger it) or a GitHub poll source's `repos` (what
it watches): both are CLI-config-only settings with no plugin-config fallback, set
them explicitly.

### CLI config reference (`cli-config.yaml`)

Every key the CLI config accepts, its type, default, and meaning. Validated against
[`.the-loop/cli-config.schema.json`](../.the-loop/cli-config.schema.json); a commented
starting point ships at
[`skills/the-loop/templates/cli-config.yaml`](../skills/the-loop/templates/cli-config.yaml).
(For the separate per-repo **plugin** config — `.the-loop/harness-config.yaml` — see the
[configuration reference](https://madarauchiha-314.github.io/the-loop/reference/configuration).)

#### Top level

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `version` | string | `0.1.0` | Schema version of this file. |
| `webhooks` | object | — | Config for the webhook receiver (`the-loop gh-webhook`). |
| `polling` | object | — | Config for the poller (`the-loop poll`). |
| `eventLog` | object | — | Config for the structured event log (`the-loop events`). |
| `collaborators` | object[] | `[]` | The operator's own notification recipients — same structure as `.the-loop/collaborators.schema.json` (see below). |
| `notifications` | object | — | Which daemon-side events notify which roles from `collaborators` (see below). |

#### `webhooks.ghWebhook` — the GitHub webhook receiver

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `host` | string | `127.0.0.1` | Interface/IP the receiver binds. |
| `port` | integer | `8787` | Listen port (1–65535). |
| `path` | string | `/gh-webhook` | HTTP path the receiver serves. |
| `secretEnv` | string | `THE_LOOP_GH_WEBHOOK_SECRET` | Env var holding the webhook secret for HMAC verification (never stored in config). |
| `pidfile` | string | `.the-loop/gh-webhook.pid` | Pidfile written on `start`, read on `stop`. |
| `events` | string[] | `[]` (all) | GitHub event names of interest (e.g. `issues`, `pull_request`, `workflow_run`); empty accepts all. |
| `routing` | object | — | Route received events to registered harness sessions (see below). |

#### `webhooks.ghWebhook.routing` — session routing / auto-execution (also reused by the poller's dispatch)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Default for `gh-webhook start --route/--no-route`. |
| `registryDir` | string | `.the-loop/sessions` | Directory of per-session registry JSON files (git-ignored). |
| `defaultHarness` | `claude` \| `cursor` | `claude` | Harness used when spawning a session for an unmatched event. |
| `spawnOnUnmatched` | `never` \| `always` \| `labeled` | `never` | Policy for events matching no session: log-and-drop / spawn+register / spawn only when `autoExecuteLabel` is present. |
| `autoExecuteLabel` | string | `the-loop: auto-execute` | Issue/PR label that opts a work item into autonomous execution (read from the payload, no API call). |
| `authorizedUsers` | string[] | `[]` | **SECURITY (prompt-injection guard):** GitHub logins whose actions the-loop may act on. **REQUIRED**, no plugin-config fallback; empty fails closed (all human-authored events ignored). |
| `spawnWorkdir` | string | `.` | Working directory for sessions spawned on unmatched events. |
| `runner` | `process` \| `tmux` | `process` | How spawned sessions are hosted: headless one-shot subprocess, or an interactive TUI in a named tmux session humans can attach to. |
| `webTerminal` | object | — | Optional ttyd-served browser terminal onto the tmux sessions (see below). |
| `maxConcurrentDispatches` | integer | `4` | Cap on harness dispatches running in parallel (per-session dispatch is always serialized). |
| `dedupCacheSize` | integer | `1024` | Bounded LRU of `X-GitHub-Delivery` ids for at-most-once processing. |
| `dispatchTimeoutSeconds` | integer | `1800` | Timeout for a single harness resume/spawn subprocess. |
| `promptTemplate` | string | `skills/the-loop/templates/webhook-event-prompt.md` | `string.Template` for the resume prompt; the dispatcher falls back to a built-in default when the path is absent. |
| `spawnPromptTemplate` | string | `skills/the-loop/templates/webhook-autoexecute-prompt.md` | `string.Template` for a newly spawned (auto-execute) session; built-in default when absent. |
| `harnessArgs.claude` | string[] | `[]` | Extra CLI args passed to Claude Code (e.g. `[--permission-mode, acceptEdits]`). |
| `harnessArgs.cursor` | string[] | `[]` | Extra CLI args passed to `cursor-agent` (e.g. `[--force]`). |
| `reactions` | object | — | Dispatch-lifecycle emoji reactions on the triggering GitHub entity (see below). |

#### `webhooks.ghWebhook.routing.reactions` — dispatch-lifecycle emoji acknowledgements

When the dispatcher picks an event up it reacts with `started` (default 👀 `eyes`) on
the comment that triggered it — or on the issue/PR itself for presence/label/review
events — then adds `completed` (default 🎉 `hooray`) or `error` (default 😕
`confused`) from the dispatch outcome, so a human watching the thread can see the-loop
working before any reply comment exists. Shared by the webhook receiver **and** the
poller, and hot-reloaded with the rest of `routing`.

Best-effort by design: reactions post through your own `gh` CLI (like the poller's
reads — the daemon holds no token); a reaction failure never affects the dispatch, and
a missing `gh`, a non-GitHub provider, or an event with no reactable target is a
silent no-op. GitHub's reaction palette is fixed (`+1 -1 laugh confused heart hooray
rocket eyes`) — ✅/⁉️ don't exist, so the defaults are the closest supported match.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Opt-in: reacting is the daemon's first **write** to GitHub, posted with your own `gh` auth — never turned on silently. |
| `started` | palette name \| `""` | `eyes` | Reaction added when the event is dequeued for delivery/spawn. `""` skips this state. |
| `completed` | palette name \| `""` | `hooray` | Reaction added when the dispatch succeeds. `""` skips this state. |
| `error` | palette name \| `""` | `confused` | Reaction added when the dispatch fails or the worker crashes. `""` skips this state. |
| `ghBinary` | string | `gh` | Path/name of the gh CLI used to post reactions. |

#### `webhooks.ghWebhook.routing.webTerminal` — browser terminal for tmux sessions (`runner: tmux`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `false` | Serve tmux sessions over HTTP via ttyd (verified at receiver start). |
| `host` | string | `127.0.0.1` | Interface/IP ttyd binds. Keep `127.0.0.1` unless the network layer protects wider exposure. |
| `port` | integer | `7681` | ttyd listen port (1–65535). |

#### `polling` — pull-based ingress (`the-loop poll`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `intervalSeconds` | integer | `60` | Seconds between poll cycles (all sources). |
| `stateFile` | string | `.the-loop/poll-state.json` | Durable JSON tracking which comments each item has processed (cross-poll/restart dedup; git-ignored). |
| `sources` | object[] | `[]` (nothing polled) | Ordered provider-specific poll sources (see below). |

#### `polling.sources[]` — one entry per source (`provider: github` ships today)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `provider` | `github` | — (**required**) | Which poll provider handles this source. |
| `label` | string | `""` | Label gating what this source polls. Empty reuses `webhooks.ghWebhook.routing.autoExecuteLabel`. |
| `repos` | string[] | — (**required**) | *(github)* Repositories to poll as `OWNER/REPO`. No plugin-config fallback; a source with none discovers nothing. |
| `monitor.issues` | boolean | `true` | *(github)* Poll issues. |
| `monitor.pullRequests` | boolean | `true` | *(github)* Poll pull requests. |
| `ghBinary` | string | `gh` | *(github)* Path/name of the `gh` CLI (uses the user's existing `gh auth`). |

#### `eventLog` — structured JSONL o11y trail (`the-loop events`)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Emit the event log; `false` turns emission off. |
| `path` | string | `.the-loop/logs/events.jsonl` | Append-only JSONL file (git-ignored runtime state). |

#### `collaborators` — the operator's own notification recipients (issue-82, decision-035)

The same collaborator structure as the per-repo `.the-loop/collaborators.schema.json`,
**declared** here rather than looked up: the daemon never reads any repo's
`collaborators.yaml`. Typically just the operator themself.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `handle` | string | — (**required**) | GitHub handle or group, e.g. `@octocat`. |
| `kind` | `individual` \| `group` | `individual` | What the handle names. |
| `roles` | string[] | — (**required**) | Roles held (`engineer`, `approver`, …) — `notifications.events` targets roles. |
| `notifications.enabled` | boolean | `true` | Per-user master switch. |
| `notifications.channels` | object[] | `[]` | Channels: each with `type` (`slack` only for now), `enabled`, `via` (`mcp` \| `cli` \| `api`) and `config.channel-list` (slack channels to notify). |

#### `notifications` — daemon-side event filters (issue-82, decision-035)

Disjoint from the harness-side taxonomy in `harness-config.yaml` (decision pending,
PR review, … — raised by the harness inside a repo checkout); these concern the daemon
itself. Each event maps to the roles (from `collaborators` above) to notify; an
omitted event notifies nobody.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `enabled` | boolean | `true` | Master switch for daemon-raised notifications. |
| `events.work-item-spawned` | string[] (roles) | — | A session was spawned for a work item. |
| `events.dispatch-failed` | string[] (roles) | — | A harness dispatch failed terminally (after `polling.maxRetries`). |
| `events.session-died` | string[] (roles) | — | A registered tmux session was found dead (respawned when possible). |
| `events.event-dropped-unauthorized` | string[] (roles) | — | An event was dropped by the authorized-actor guard. |

## Commands

### `gh-webhook` — GitHub webhook receiver

```bash
the-loop gh-webhook start [--host 127.0.0.1] [--port 8787] [--path /gh-webhook] \
                          [--pidfile .the-loop/gh-webhook.pid] \
                          [--secret-env THE_LOOP_GH_WEBHOOK_SECRET] \
                          [--route | --no-route]
the-loop gh-webhook stop  [--pidfile .the-loop/gh-webhook.pid]
```

- Verifies the GitHub `X-Hub-Signature-256` HMAC when the secret env var is set
  (export `THE_LOOP_GH_WEBHOOK_SECRET=...`). The secret is read from the environment,
  never a flag, so it doesn't leak into process listings.
- `GET /health` returns `200 ok`.
- Defaults can come from the **CLI config** (`webhooks.ghWebhook`, see
  "Two independent config files" above for the `--config`/env/cwd/home resolution
  order) when PyYAML is installed; flags always override.
- **`--route`** (default from `webhooks.ghWebhook.routing.enabled`) routes each verified
  event to the registered harness session working that item: the router extracts the
  work item(s) from the payload (issue/PR number, PR head-branch `issue-<n>` convention,
  closing keywords, `workflow_run`/`check_*` PRs), deduplicates on `X-GitHub-Delivery`,
  and the dispatcher resumes the matched session via its official CLI
  (`claude -p … --resume <session-id>` / `cursor-agent -p … --resume <chat-id>`), one
  event at a time per session, in parallel across sessions. Unmatched events follow
  `routing.spawnOnUnmatched` (`never` drops; `always` spawns + registers a session).
  Design: `docs/specs/issue-15/design.md`, `docs/decisions/decision-016.md`.
- **Config hot-reload:** while the receiver runs, edits to `webhooks.ghWebhook.routing` /
  `events` are picked up on the next received event — no restart. The soft policy (events
  filter, label, spawn policy, harness/runner, per-harness args, prompt templates) swaps
  live; the dedup cache, per-session queues and registry are preserved. Infrastructural
  settings (`host`/`port`/`path`, `secretEnv`, `maxConcurrentDispatches`, `dedupCacheSize`,
  `registryDir`, `webTerminal`) still need a restart. An invalid edit is logged and the
  previous config kept.
- **Authorized-actor guard (prompt-injection remediation):** the receiver acts only on
  actions by logins in `routing.authorizedUsers` (CLI config — REQUIRED, no fallback to
  any repo's plugin config) — comments/reviews and issue/PR labels/opens from anyone
  else are dropped before dispatch (CI/system events, which carry no human
  instructions, still pass; a PR-close still auto-closes the session). Empty fails
  closed with a warning. Each operator runs their own instance for their own login(s).
  See `docs/decisions/decision-023.md`.
- **Self-reply guard (loop prevention):** the harness posts its own replies under the
  operator's own credentials, so authorship alone can't tell them apart from a human
  comment. Every comment/review/reply the-loop posts carries an embedded marker
  (`the_loop.authz.SELF_COMMENT_MARKER`); the receiver drops a marker-carrying event
  before dispatch, regardless of actor, so the-loop's own reply never resumes the
  session that wrote it. See `docs/decisions/decision-031.md`.
- **Structured event log:** every receive/reject/route/dispatch/spawn/close decision is
  appended to `.the-loop/logs/events.jsonl` — query it with `the-loop events` (below).

### `sessions` — link work items to harness sessions (webhook routing)

```bash
the-loop sessions register --work-item github:OWNER/REPO#N --harness claude \
    --harness-session-id "$CLAUDE_SESSION_ID" [--cwd .] [--force]
the-loop sessions list  [--status active|closed] [--format table|json]
the-loop sessions close --work-item github:OWNER/REPO#N
```

- The registry lives in `webhooks.ghWebhook.routing.registryDir` (default
  `.the-loop/sessions/`, git-ignored) as one human-inspectable JSON file per session;
  writes are atomic, so concurrent sessions on the same machine are safe.
- One work item ↔ one active session; `--force` replaces a stale registration.
- Claude Code sessions register with `$CLAUDE_SESSION_ID`; Cursor sessions register
  with the chat id they were launched with (non-interactive `cursor-agent ls` is
  unreliable for id discovery, so the id is captured at registration time).
- When a work item's PR is merged or closed, the receiver **auto-closes** the session
  (on the `pull_request` `closed` event) — no manual `sessions close` needed.

**Label-gated auto-execution** (`spawnOnUnmatched: labeled`): give an issue/PR the
configurable `routing.autoExecuteLabel` (default `the-loop: auto-execute`) and the
receiver spawns a session and starts `/the-loop:work-on` on it — then routes that item's
later activity (comments, reviews, CI, its linked PR) to the same session, and
auto-closes on PR merge. Label presence is read straight from the webhook payload (no
extra API call). A new issue *without* the label is received and ignored.

The label applies to **PRs directly** too — a labelled PR with no linked issue is routed
as its own work item (`github:OWNER/REPO#<pr-number>`). That makes PRs monitorable even
when the ticketing system is **Jira or another provider**: the ticket can't be routed,
but the PR delivering it can. `/the-loop:work-on <jira-id>` adds the label to the PR it
opens and registers its session against the PR's ref automatically, so PR activity
resumes the session and merge/close ends it — same as a GitHub-ticketed item.

### `poll` — pull ingress (provider-agnostic) when a webhook can't reach you

```bash
the-loop poll start [--interval 60] [--once] \
                    [--state-file .the-loop/poll-state.json] \
                    [--pidfile .the-loop/poll.pid]
the-loop poll stop  [--pidfile .the-loop/poll.pid]
```

A **pull-based** alternative to `gh-webhook` for hosts a webhook cannot reach (behind
NAT/a firewall, a laptop, unreachable infra). Every `--interval` seconds it asks each
configured **provider** for the label-gated work items in its scope and drives them
through the **same** routing/dispatch/session stack the webhook receiver uses — so
spawning, one-session-per-work-item, the `tmux` runner, harness adapters and prompt
templates are all reused unchanged.

- **Provider-agnostic:** the poller core and CLI carry no GitHub knobs. Which systems
  are polled is defined purely by `polling.sources` in the **CLI config** — each entry
  names a `provider` (GitHub ships; the seam admits others). GitHub is reached *only*
  through a configured source:

  ```yaml
  polling:
    intervalSeconds: 60
    sources:
      - provider: github
        repos: [octo/repo]         # REQUIRED — no fallback to any repo's plugin config
        monitor: { issues: true, pullRequests: true }
        label: ""                  # empty = reuse routing.autoExecuteLabel
  ```

- **Label-gated:** only items carrying the configured label are polled. A source's
  `label` defaults to `webhooks.ghWebhook.routing.autoExecuteLabel`, so one label drives
  both ingresses.
- **No duplicate sessions:** a session is spawned for a labelled item only when the
  registry has none; a live session is never doubled (the registry is the source of
  truth), so a work item maps to exactly one session — the same one on later polls.
- **Spawns tmux sessions** when `webhooks.ghWebhook.routing.runner: tmux` — attach with
  `the-loop sessions attach --work-item github:OWNER/REPO#N` (issue-32).
- **New comments** are forwarded to the item's session exactly once, deduped across
  polls **and restarts** via `--state-file` (git-ignored runtime state). The pre-existing
  thread is baselined on first sight, not replayed.
- **Config:** ingress defaults come from `polling` in the **CLI config** (when PyYAML is
  installed); dispatch behaviour is reused from `webhooks.ghWebhook.routing` (same
  file). Flags cover only the run loop.
- **Hot reload:** edit `polling.sources` / `intervalSeconds` while it runs and the change
  is picked up on the next cycle — no restart. An invalid edit is logged and the previous
  config kept. (The shared dispatch config still needs a restart.)
- **Authorized-actor guard (prompt-injection remediation):** the poller spawns only for
  items authored by a login in `routing.authorizedUsers` (CLI config — REQUIRED, no
  fallback to any repo's plugin config), and forwards only comments from authorized
  authors — everything else is ignored. Empty fails closed with a warning. See
  `docs/decisions/decision-023.md`.
- **Self-reply guard (loop prevention):** same marker check as the receiver — a comment
  the-loop itself posted is excluded from "new comments" (and can't retrigger a spawn),
  even though it was posted under an authorized login. See
  `docs/decisions/decision-031.md`.
- **`--once`** runs a single cycle and exits (for a cron/systemd timer); otherwise it
  loops until `poll stop` (or SIGINT/SIGTERM), writing a pidfile like the receiver.
  Design: `docs/specs/issue-34/design.md`, `docs/decisions/decision-022.md`.
- **Structured event log:** cycle summaries, spawns, forwarded comments and
  provider/item errors are appended to the same event log as the receiver — query with
  `the-loop events --source poll`.

### `events` — query the structured event log (end-to-end o11y)

```bash
the-loop events [--file .the-loop/logs/events.jsonl] [--type PATTERN ...] \
                [--work-item github:OWNER/REPO#N] [--delivery-id ID] \
                [--source gh-webhook|poll|sessions] [--level warning] \
                [--since 2h|2026-07-22T10:00:00Z] [--limit 50] \
                [--format table|json|jsonl] [--follow]
the-loop events --types      # the documented catalog of event types
```

The receiver, the poller and the sessions CLI append **every decision they make** —
webhook accepted/rejected (and why), event routed/dropped (with a machine-readable
`reason` like `unauthorized-actor` or `duplicate-delivery`), session spawned/resumed
(naming the triggering event and delivery id), dispatch failed (with the error and
whether redelivery/the next poll cycle retries it), session closed/auto-closed — as one
JSON object per line to `eventLog.path` in the **CLI config** (default
`.the-loop/logs/events.jsonl`, git-ignored). This command is the query surface:

- `--work-item` shows one item's full history ("which events triggered this
  session?"); `--delivery-id` follows a single GitHub delivery end to end.
- `--type` takes fnmatch patterns (repeatable): `--type 'dispatch.*' --level error`
  answers "what failed?".
- `--since` accepts ISO-8601 UTC or relative (`30s`/`15m`/`2h`/`1d`); `--follow`
  tails the log live; `--limit` keeps the last N (default 50, `0` = all).
- `--format json|jsonl` is machine-readable (for agents and dashboards); the file
  itself is plain JSONL, so `grep`/`jq`/`tail -f` work directly on it.

Every record carries `ts`/`source`/`event`/`level`/`pid` plus documented per-type
fields; the catalog (`the-loop events --types`) is enforced against the emitted types
by a unit test. Writes are append-only and multi-process safe, a broken log never
breaks ingress, and `eventLog.enabled: false` (CLI config) turns emission off.
Schema + agent guidance: `skills/the-loop/reference/observability.md`; storage decision
(JSONL, not SQLite): `docs/decisions/decision-025.md`.

### `scenarios` — query the Gherkin scenarios integration tests cover

```bash
the-loop scenarios [--root .] [--glob PATTERN ...] [--format table|markdown|json]
```

- Scans integration-test files for the Gherkin-syntax docstrings the-loop requires
  (`Feature:` / `Scenario:` / Given-When-Then, plus an optional `Requirement:` link to a
  `requirements.md`) and presents them as a table — so a coding-agent harness can answer
  "what scenarios are tested?" without running anything.
- Language-agnostic: Python docstrings, JS/TS block comments and Go comments all work.
- Globs come from `--glob` (repeatable), else `testing.integrationTestGlobs` in
  `.the-loop/harness-config.yaml` (when PyYAML is installed), else built-in defaults covering
  common layouts.
- `--format markdown` emits a GitHub-flavoured table (for PR briefings); `--format json`
  is machine-readable (includes each scenario's steps and `file:line`).

## Adding a command (extensibility)

1. Create `the_loop/commands/<your_command>.py`.
2. Subclass `Command`, set `name`/`help`, implement `add_arguments` and `run`, and
   decorate the class with `@register`.
3. Import the module in `the_loop/commands/__init__.py`.

The CLI discovers registered commands automatically.

## Test

```bash
pytest        # from this directory
```
