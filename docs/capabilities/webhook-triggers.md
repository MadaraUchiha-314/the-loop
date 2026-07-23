# Capability: webhook-triggers

> GitHub events (comments, reviews, CI results) reach the *right* running harness
> session on the user's own machine, programmatically.

## What it is

The local trigger path: an HMAC-verified webhook receiver plus event → session routing,
so a PR comment or workflow result resumes the Claude Code / Cursor session working
that item — the self-hosted equivalent of claude.ai/code PR watching.

## Current behaviour

- `the-loop gh-webhook start` SHALL run an HTTP receiver (default `127.0.0.1:8787`,
  path `/gh-webhook`) that verifies `X-Hub-Signature-256` HMAC using
  `THE_LOOP_GH_WEBHOOK_SECRET`, exposes `GET /health`, and logs events.
- Receiver/routing settings (`webhooks.ghWebhook`) SHALL be read from the
  user/machine-level **CLI config** (`$XDG_CONFIG_HOME/the-loop/config.yaml`, override
  `$THE_LOOP_CLI_CONFIG`), **not** a repo's plugin config, because the CLI works across
  repos (see [configuration](configuration.md), [decision-021](../decisions/decision-021.md)).
  For backward compatibility a legacy `webhooks:` block in `.the-loop/config.yaml` SHALL
  still be honoured with a deprecation warning.
- Supported events SHALL include `issues`, `issue_comment`, `pull_request`,
  `pull_request_review`, `pull_request_review_comment`, `workflow_run`
  (`webhooks.ghWebhook.events`).
- WHEN routing is enabled (`webhooks.ghWebhook.routing.enabled`) THEN a verified event
  SHALL be matched to a registered session (`.the-loop/sessions/*.json`, managed by
  `the-loop sessions`) and the harness SHALL be resumed via its official CLI
  (`claude -p --resume` / `cursor-agent -p --resume`), serialized per session and
  parallel across sessions (`maxConcurrentDispatches`).
- WHEN no session matches THEN the router SHALL spawn a new session per
  `spawnOnUnmatched` (`never | always | labeled`, default `labeled` — opt-in via the
  `the-loop: auto-execute` label) using the configured prompt templates.
- Duplicate deliveries SHALL be dropped via a dedup cache (`dedupCacheSize`).

## Design

[`docs/specs/issue-15/design.md`](../specs/issue-15/design.md) ·
[architecture § triggers](../architecture/architecture.md)

## History

| Work item | What changed | Links |
|-----------|--------------|-------|
| issue-63 | Moved `webhooks.ghWebhook` config to the user-level CLI config (repo-independent); legacy repo location still read with a deprecation warning | [spec](../specs/issue-63/), [decision-021](../decisions/decision-021.md) |
| issue-15 | Added session registry, event→session routing and harness resume (receiver shipped in v0 gained `--route`) | [spec](../specs/issue-15/), [decision-016](../decisions/decision-016.md) |
| issue-1 | Shipped the HMAC-verified `gh-webhook` receiver (v0) | [spec](../specs/issue-1/), [decision-005](../decisions/decision-005.md) |
