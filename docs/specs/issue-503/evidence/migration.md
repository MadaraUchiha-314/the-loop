---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#503"
---

# Migration (T10)

`migrate-config` rewrites 20.3.0's `gateway:` + `read.mode: socket` to `read.mode:
gateway`. A second run changes nothing. `channels status` flags the old form and
describes the new one.

## T10: `cd cli && uv run python -m pytest -q tests/test_migrations.py -k gateway`

```text
test_migrations.py::test_gateway_socket_is_rewritten_to_gateway_mode PASSED
test_migrations.py::test_gateway_read_mode_migration_leaves_other_configs_alone[config0] PASSED
test_migrations.py::test_gateway_read_mode_migration_leaves_other_configs_alone[config1] PASSED
test_migrations.py::test_gateway_read_mode_migration_leaves_other_configs_alone[config2] PASSED
test_migrations.py::test_gateway_read_mode_migration_leaves_other_configs_alone[config3] PASSED
test_migrations.py::test_gateway_socket_needs_migration_but_is_never_refused PASSED
======================= 6 passed, 98 deselected in 0.07s =======================
```

## A sample 20.3.0 config

The URL is a loopback placeholder.

```yaml
version: "0.12.0"
instance:
  name: laptop-a
gateway:
  url: http://127.0.0.1:8790
channels:
  slack:
    enabled: true
    channel: C0123ABCDEF
    publish: [work-item.reply, gate.feedback, control.command]
    read:
      mode: socket
```

## `the-loop migrate-config --path <sample> --dry-run`

```text
migrated the CLI config:
  · channels.slack.read.mode socket → gateway (a gateway consumer opens no Socket Mode connection, issue-503)

--- <scratchpad>/mig/cli-config.yaml (preview, not written) ---
version: 0.12.0
instance:
  name: laptop-a
gateway:
  url: http://127.0.0.1:8790
channels:
  slack:
    enabled: true
    channel: C0123ABCDEF
    publish:
    - work-item.reply
    - gate.feedback
    - control.command
    read:
      mode: gateway

```

## Written, then run again (idempotence)

```text
migrated the CLI config:
  · channels.slack.read.mode socket → gateway (a gateway consumer opens no Socket Mode connection, issue-503)

wrote <scratchpad>/mig/cli-config.yaml (previous version kept at <scratchpad>/mig/cli-config.yaml.bak)
--- second run ---
config is already current; nothing to migrate
```

## `the-loop channels status`, after (`cli-config.yaml`) and before (`before.yaml`)

```text
== cli-config.yaml
  read:         gateway — events arrive through the gateway client (http://127.0.0.1:8790); no Socket Mode connection here
  channel kind: public channel or private channel — needs bot scope channels:history / groups:history and bot event message.channels / message.groups
== before.yaml
  read:         socket, reconciling every 900s
  [!] read.mode is socket beside a gateway block — the listener stays off; run the-loop migrate-config to set read.mode: gateway
  split check:  2 heartbeat(s) every 900s — not run yet on this state root
== cli-config.yaml
  read:         gateway — events arrive through the gateway client (http://127.0.0.1:8790); no Socket Mode connection here
  buttons:      Approve / Request changes: on · Execute / Start: on
  commands:     /the-loop through the gateway — work-item: granted · create: not granted · instance: not granted · standing: not granted
  mentions:     @the-loop is the address in every channel — app_mention through the gateway; needs the bot scope app_mentions:read (`--probe` measures it). A DM with the bot and a room declared --listen all also hear plain messages
  shortcuts:    Add as the-loop context / Record the-loop decision (the-loop:record-context, the-loop:record-decision) through the gateway — each exactly the typed mention
  app token:    unset (THE_LOOP_SLACK_APP_TOKEN)
== before.yaml
  read:         socket, reconciling every 900s
  buttons:      Approve / Request changes: on · Execute / Start: on
  commands:     /the-loop over Socket Mode — work-item: granted · create: not granted · instance: not granted · standing: not granted
  mentions:     @the-loop is the address in every channel — app_mention over Socket Mode; needs the bot scope app_mentions:read (`--probe` measures it). A DM with the bot and a room declared --listen all also hear plain messages
  shortcuts:    Add as the-loop context / Record the-loop decision (the-loop:record-context, the-loop:record-decision) over Socket Mode — each exactly the typed mention
  app token:    unset (THE_LOOP_SLACK_APP_TOKEN)
```
