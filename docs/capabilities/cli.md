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
  receiver (see [webhook-triggers](webhook-triggers.md)), reading its defaults from the
  user/machine-level CLI config (see [configuration](configuration.md)).
- `the-loop sessions register|list|close` SHALL manage the work-item ↔ harness-session
  registry used for webhook routing.
- `the-loop scenarios` SHALL output the table of every Gherkin scenario covered by the
  integration tests (`--format table|markdown|json`; see
  [testing-and-contracts](testing-and-contracts.md)).
- The package SHALL be installable from PyPI as **`the-loopy-one`** (import package
  `the_loop` and the `the-loop` script unchanged; see
  [release-publishing](release-publishing.md)).

## Design

[`cli/README.md`](../../cli/README.md) ·
[architecture § CLI companion](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-63 | CLI reads webhook defaults from a user-level CLI config (`the_loop.config`), split out of the per-repo plugin config | [spec](../specs/issue-63/), [decision-021](../decisions/decision-021.md) |
| issue-21 | Published to PyPI as `the-loopy-one` with automatic semantic releases | [spec](../specs/issue-21/), [decision-019](../decisions/decision-019.md) |
| issue-15 | Added `sessions` registry commands and webhook `--route` dispatch | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-11 | Added `scenarios` (queryable integration-test scenario table) | [spec](../specs/issue-11/), [decision-014](../decisions/decision-014.md) |
| issue-1 | Established the CLI skeleton and the `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
