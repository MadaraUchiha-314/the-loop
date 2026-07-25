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
- `the-loop sessions register|list|show|pause|resume|attach|close|prune` SHALL be the
  operator's surface over the daemon: it manages the work-item ↔ harness-session
  registry used for webhook routing, and `list` SHALL print one table of every tracked
  work item — joining the registry, the poller's ledger (so an item tracked *without* a
  session, or one whose spawn was given up on, is visible) and live tmux state — with
  each row linking onward to the ticket, the tmux session (target, pane pid, liveness,
  attach command) or the owning daemon process for a `runner: process` session, and the
  PR observed for the item. Output SHALL be plain column-aligned stdio (no TUI) with
  `--format json` for scripting (issue-98).
- `the-loop sessions pause|resume <ref>` SHALL stop and restart the-loop acting on ONE
  work item — no spawn, no event delivery, on **either** ingress path — while leaving
  its session, tmux transcript and checkout untouched; a work item that **ends** while
  paused SHALL still have its session closed (pause stops work, never cleanup). The
  same control SHALL be available as the `routing.pausedLabel` GitHub label (default
  `the-loop: paused`), read from data the daemon already holds, composing with the
  local ledger (`routing.pauseFile`) as **OR**; `pause`/`resume` SHALL mirror the label
  onto the ticket best-effort (`--no-label` to skip), and a failed label write SHALL
  never fail the local pause (issue-98).
- `the-loop labels ensure --repo OWNER/REPO` SHALL create the operational labels the
  daemon reads (auto-execute, paused) under their configured names, idempotently, with
  `--dry-run`; `/the-loop:init` runs it during onboarding (issue-98).
- `the-loop scenarios` SHALL output the table of every Gherkin scenario covered by the
  integration tests (`--format table|markdown|json`; see
  [testing-and-contracts](testing-and-contracts.md)).
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

## Design

[`cli/README.md`](../../cli/README.md) ·
[architecture § CLI companion](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-98 | `sessions` became the operator surface: joined `list` table, `show`, `pause`/`resume` (CLI + `the-loop: paused` label), `prune`; new `labels ensure` command | [spec](../specs/issue-98/) |
| issue-97 | PyYAML promoted from the `[config]` extra to a required runtime dependency; the three silent `ImportError` fallbacks removed and the zero-runtime-dependency guarantee retired | [spec](../specs/issue-97/), [decision-038](../decisions/decision-038.md) |
| issue-82 | Plugin config renamed `config.yaml` → `harness-config.yaml` (`scenarios` reads the new name with a pre-rename fallback); CLI config gained operator-declared `collaborators` + daemon-side `notifications` event filters | [decision-035](../decisions/decision-035.md) |
| issue-78 | `--version` derives from package metadata instead of a hardcoded string that had frozen at 0.1.0 | [spec](../specs/issue-78/) |
| issue-63 | Split the CLI daemon's config (`webhooks`/`polling`/`eventLog`) out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-50 | Added the structured event log and the `events` query command | [spec](../specs/issue-50/), [decision-025](../decisions/decision-025.md) |
| issue-21 | Published to PyPI as `the-loopy-one` with automatic semantic releases | [spec](../specs/issue-21/), [decision-019](../decisions/decision-019.md) |
| issue-15 | Added `sessions` registry commands and webhook `--route` dispatch | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-11 | Added `scenarios` (queryable integration-test scenario table) | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
| issue-1 | Established the CLI skeleton and the `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
