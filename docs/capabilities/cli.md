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
- `the-loop gh-webhook start|stop` SHALL run/stop the HMAC-verified GitHub webhook
  receiver (see [webhook-triggers](webhook-triggers.md)).
- `the-loop sessions register|list|attach|close` SHALL manage the work-item ↔
  harness-session registry used for webhook routing.
- `the-loop sessions start|pause|resume|stop` SHALL give an operator with shell access
  the **same four commands** an authorized user issues by keyword in a comment
  (issue-106, see [webhook-triggers](webhook-triggers.md)): `start` spawns through the
  same dispatcher the daemon uses — workspace checkout, harness trust, configured
  runner, session announcement — or resumes a paused session; `stop` takes the normal
  close path. Each invocation SHALL record the command in that work item's portable
  record (`<state.root>/portable/<slug>.json`, `control` section — issue-128) and SHALL
  post the **same keyword** back to the work item
  so its thread stays the full record of who asked for what. That comment SHALL carry
  the loop-prevention marker (`authz.mark_self_authored`), because the action has
  already been applied locally and neither ingress path may read it back and re-apply
  it. Posting is best-effort — `--no-comment` skips it, and a missing/failing `gh`
  warns without undoing the local action. `sessions list` SHALL show each session's
  status (including `paused`) and its last control command.
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
  gate's verdict.
- The CLI config SHALL carry a `version`, and the CLI SHALL **refuse to run** against a
  config older than the current schema version rather than guessing at the old shape
  (issue-109). Per-provider settings SHALL live under one `integrations` block —
  `integrations.github.cli.binary` replaces the `ghBinary` key that was previously
  duplicated across three consumers. This is a **breaking** change, handled by
  `/the-loop:upgrade-the-loop`.
- The CLI SHALL declare a second runtime dependency, `slack-sdk`, only as an **optional
  extra**: it is Slack's official SDK and has zero required dependencies of its own, but
  the dependency-free `webhook` transport remains available so the base install stays
  one-dependency.
- `the-loop scenarios` SHALL output the table of every Gherkin scenario covered by the
  integration tests (`--format table|markdown|json`; see
  [testing-and-contracts](testing-and-contracts.md)).
- `the-loop critic list|run` SHALL list the configured critic harnesses and run **one**
  named critic-review round, printing its result as a single JSON envelope on stdout — the
  seam by which the running harness hands work to a *different* harness and reads back what
  it said (see [review-loop](review-loop.md)). Like `check` and `scenarios` it is
  repo-scoped: it reads the harness config of the project it is invoked in, and is no part
  of the daemon (decision-032).
- `the-loop events` SHALL query the structured JSONL event log of the CLI's own
  routing/dispatch/session decisions (see [observability](observability.md)).
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

## Design

[CLI documentation](https://madarauchiha-314.github.io/the-loop/cli/) (source: [`docs/cli/`](../cli/)) ·
[`cli/README.md`](../../cli/README.md) (the PyPI package readme) ·
[architecture § CLI companion](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
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
