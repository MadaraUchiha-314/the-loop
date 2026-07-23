# Capability: cli

> The `the-loop` Python CLI companion — lightweight, stdlib-only, extensible
> quality-of-life commands the plugin (and users) can call.

## What it is

A Python package (`cli/`, import package `the_loop`, console script `the-loop`) with an
extensible command registry. Python is deliberate: it leaves room for future
self-learning/ML capabilities.

## Current behaviour

- The CLI SHALL have zero runtime dependencies (stdlib only) and register commands via
  an extensible registry (`the_loop.commands`).
- `the-loop gh-webhook start|stop` SHALL run/stop the HMAC-verified GitHub webhook
  receiver (see [webhook-triggers](webhook-triggers.md)).
- `the-loop sessions register|list|close` SHALL manage the work-item ↔ harness-session
  registry used for webhook routing.
- `the-loop scenarios` SHALL output the table of every Gherkin scenario covered by the
  integration tests (`--format table|markdown|json`; see
  [testing-and-contracts](testing-and-contracts.md)).
- `the-loop events` SHALL query the structured JSONL event log of the CLI's own
  routing/dispatch/session decisions (see [observability](observability.md)).
- The package SHALL be installable from PyPI as **`the-loopy-one`** (import package
  `the_loop` and the `the-loop` script unchanged; see
  [release-publishing](release-publishing.md)).
- `gh-webhook`/`poll`/`sessions`/`events` SHALL read their defaults from a **CLI
  config** (`cli-config.yaml`) independent of any repo's `.the-loop/config.yaml` (the
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
| issue-63 | Split the CLI daemon's config (`webhooks`/`polling`/`eventLog`) out of the per-repo plugin config into an independent, repo-agnostic CLI config | [spec](../specs/issue-63/), [decision-032](../decisions/decision-032.md) |
| issue-50 | Added the structured event log and the `events` query command | [spec](../specs/issue-50/), [decision-025](../decisions/decision-025.md) |
| issue-21 | Published to PyPI as `the-loopy-one` with automatic semantic releases | [spec](../specs/issue-21/), [decision-019](../decisions/decision-019.md) |
| issue-15 | Added `sessions` registry commands and webhook `--route` dispatch | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-11 | Added `scenarios` (queryable integration-test scenario table) | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
| issue-1 | Established the CLI skeleton and the `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
