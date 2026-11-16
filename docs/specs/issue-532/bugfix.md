---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#532"
status: draft                # requirements-approval skipped by declaration at phase-selection
approvedBy: []
severity: medium
riskTier: 2
collaborators: [engineer]
overrides: {}
---

<!-- Written per the `the-loop:writing` skill. -->

# Bugfix spec: graph notifications on a gateway consumer fail first time with "no bot token"

## Summary

On an instance that reaches Slack through a gateway (`gateway.url` set, no
`THE_LOOP_SLACK_BOT_TOKEN`), every Slack post made by a graph hook — `notify`, and the
runtime's own phase lifecycle events — fails on its first attempt with
`slack: no bot token — export THE_LOOP_SLACK_BOT_TOKEN …`. The outbox drainer retries it
13–25 s later through the gateway, and it lands with `channel.delivered_late`. Posts
arrive, but late, and the error makes a correct configuration look broken
([#532](https://github.com/MadaraUchiha-314/the-loop/issues/532)).

## Steps to reproduce

1. Configure a gateway consumer: `gateway.url`, `channels.slack.enabled: true`,
   `channels.slack.channel`; leave `THE_LOOP_SLACK_BOT_TOKEN` unset.
2. `the-loop --config <abs path> start`.
3. Arm a work item and comment `the-loop start`.
4. Each phase notification logs the "no bot token" failure, then
   `channel.delivered_late` once the outbox drains.

## Expected vs actual

- **Expected:** graph notifications post through the gateway on the first attempt.
- **Actual:** the first attempt raises `ChannelError("slack: no bot token …")`; only the
  outbox retry, which reloads the channels from the daemon's full CLI config, succeeds.

## Root cause (confirmed)

`graph/bootstrap.py::build_runtime` hands every graph runtime a **derived** config — a
subset of the CLI config (`channels`, `state`, `repositories`, `integrations`, …). The
issue-519 posting path reads two more keys from the config it is given:

| Key | Reader | Effect when missing |
|-----|--------|---------------------|
| `gateway` | `slack.posting_path` → `cli_config.gateway_block` | path is `none` → `ChannelError` |
| `instance` | `GatewaySlackClient.from_cli_config` → `cli_config.instance_name` | gateway call made under the default name, not this instance's |

Both publishers that run inside a graph runtime pass that derived config:
`graph/hooks/sideeffects.py::notify` (`cli_config=ctx.config`) and
`graph/runtime.py` lifecycle events (`publish_lifecycle(…, self.config)`). The outbox
drainer (`channels/outbox.py`) reloads from the full config, which is why the retry
works. Every graph runtime is built by `build_runtime` (the daemon via
`graphlink._build_runtime`, the CLI via `core/graphs.py`), so that is the one place to
fix.

The second row was found during this audit; the ticket names only the first. Without
it, a fix for `gateway` alone would post first-time under the default instance name,
which the gateway's lease check may treat as a different peer.

## Requirements

### Requirement 1 — graph publishes reach the gateway on the first attempt

#### Acceptance criteria (EARS)

1. WHEN the CLI config carries a usable `gateway` block AND the Slack bot token
   variable is unset THEN the config `build_runtime` gives a graph runtime SHALL resolve
   `posting_path(...).kind == "gateway"`.
2. WHEN the CLI config names an instance (`instance.name`) THEN the gateway client built
   from a graph runtime's config SHALL call the gateway under that name.
3. WHEN a graph `notify` hook publishes on such an instance THEN the post SHALL be
   delivered through the gateway on the first attempt, with no `ChannelError` and
   nothing queued in the outbox.
4. WHEN the CLI config has no `gateway` block THEN the runtime config SHALL carry none,
   and posting behaviour SHALL be unchanged (local token, or `none` with today's error).

### Requirement 2 — regression coverage

1. The fix SHALL include tests for R1.1–R1.3 that fail before the fix and pass after.

## Security considerations

No new attack surface. The change copies two existing, operator-owned keys of the CLI
config (`gateway.url` and its timing knobs, `instance.name`) into the in-process config
graph hooks already receive. Neither carries a secret (the gateway is reached by URL;
credentials stay in env vars, unchanged). The source is the same file the daemon
already trusts for these keys, and the outbox retry already used them; the fix only
makes the first attempt use what the retry uses. The work-item thread and the
agent-writable state file cannot set either key: `build_runtime` reads them only from
the operator's CLI config. Fail-closed is unchanged: a missing or malformed block still
resolves to `none` (`gateway_block` returns `None`), and posting still raises.

## Out of scope

- Restructuring `build_runtime` to pass the whole CLI config through (see design
  trade-offs).
- The gateway's own posting policy (`slack.post.enabled`) — unchanged.

## Open questions

None.
