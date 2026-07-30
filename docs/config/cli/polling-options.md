---
configBase: polling
---

# Polling options

Options under `polling` — the pull-based ingress run by
[`the-loop poll start`](/cli/commands/poll), for hosts a webhook cannot reach: behind NAT
or a firewall, a laptop, infrastructure with no inbound route.

Only the **run loop** is configured here. Everything the poller does with an item it
discovers — spawning, session mapping, the runner, harness args, prompt templates, the
guards — is reused verbatim from [routing options](/config/cli/routing-options). One
dispatch stack, two ingresses.

```yaml
polling:
  intervalSeconds: 60
  maxRetries: 3
  sources:
    - provider: github
      repos: [octo/repo]
      monitor: { issues: true, pullRequests: true }
      label: ""            # empty = reuse routing.autoExecuteLabel
```

## The run loop

### `intervalSeconds`

- **Type:** `integer`
- **Default:** `60`

Seconds between poll cycles, across all sources.

### `stateFile`

- **Type:** `string`
- **Default:** `<state.root>/sessions/poll-state.json`

Durable JSON tracking which comments each item has already been forwarded, so a comment is
delivered exactly once across cycles **and** restarts. Git-ignored runtime state.

Unset, it resolves under [`state.root`](/config/cli/#state-root) with the rest of the
session tracking. A pre-issue-106 `.the-loop/poll-state.json` that still exists keeps being
used, with a warning, rather than silently re-baselining: adopting an empty state file
would make every watched thread first-sight again and re-forward its whole comment
history.

### `maxRetries`

- **Type:** `integer`
- **Default:** `3`

Per-event delivery attempts before the poller gives up. A spawn or comment forward whose
dispatch keeps failing is retried each cycle up to this many attempts; after that the
poller logs a terminal failure (`poll.spawn_failed` / `poll.comment_failed`) and ignores
the event on later polls until new activity re-arms it. An in-flight, still-processing
dispatch is not counted as a failed attempt.

## Sources

`sources` is an ordered list. Each entry names a `provider`; the remaining keys are that
provider's own config, unknown to the poller core — which is what keeps the core
provider-agnostic. GitHub ships today; the seam admits others.

::: warning An empty `sources` list polls nothing
`the-loop poll start` exits with `no polling sources configured` rather than looping
quietly over an empty list.
:::

### `sources[].provider`

- **Type:** `'github'`
- **Default:** none — **required**

Which poll provider handles this source.

### `sources[].label`

- **Type:** `string`
- **Default:** `""`

Label gating what this source polls. Empty reuses
[`routing.autoExecuteLabel`](/config/cli/routing-options#autoexecutelabel), so one label
drives both ingresses.

### `sources[].repos`

- **Type:** `string[]`
- **Default:** none — **required** *(github)*

Repositories to poll, as `OWNER/REPO`.

::: danger No fallback
There is no fallback to any repository's harness config. A source with no `repos`
discovers nothing.
:::

### `sources[].monitor.issues`

- **Type:** `boolean`
- **Default:** `true` *(github)*

Poll issues.

### `sources[].monitor.pullRequests`

- **Type:** `boolean`
- **Default:** `true` *(github)*

Poll pull requests.

::: tip Where the `gh` binary comes from
GitHub reads use your existing `gh auth` — the daemon holds no token. The binary is
configured once at
[`integrations.github.cli.binary`](/config/cli/integrations-options#github-cli-binary), not
per source. (It was a per-feature `ghBinary` before issue-109; that key is now refused, and
[`the-loop migrate-config`](/cli/commands/migrate-config) moves it.)
:::

## Hot reload

Edit `sources` or `intervalSeconds` while the poller runs and the change is picked up on
the next cycle — no restart. An invalid edit is logged and the previous config kept. The
shared dispatch config under `routing` still needs a restart.

## Next

- [`the-loop poll`](/cli/commands/poll) — the command, its flags, and how finished work
  items get closed without a `closed` webhook.
- [Routing options](/config/cli/routing-options) — everything the poller reuses.
