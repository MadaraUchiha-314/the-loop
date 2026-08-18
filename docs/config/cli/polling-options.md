---
configBase: polling
---

# Polling options

Options under `polling` — the pull-based ingress started by
[`the-loop start`](/cli/commands/start) when `enabled` is true (or run directly via
`python -m the_loop.daemon_entry poller`), for hosts a webhook cannot reach: behind NAT
or a firewall, a laptop, infrastructure with no inbound route.

Only the **run loop** is configured here. Everything the poller does with an item it
discovers — spawning, session mapping, harness args, prompt templates, the
guards — is reused verbatim from [routing options](/config/cli/routing-options). One
dispatch stack, two ingresses.

```yaml
polling:
  enabled: false
  intervalSeconds: 60
  maxRetries: 3
  sources:
    - provider: github
      repos: [octo/repo]
      monitor: { issues: true, pullRequests: true }
      label: ""            # empty = reuse routing.autoExecuteLabel
```

## The run loop

### `enabled`

- **Type:** `boolean`
- **Default:** `false`

Whether [`the-loop start`](/cli/commands/start) brings the poller up (issue-228,
[decision-084](/decisions/decision-084)). Explicit, never inferred from a non-empty
`sources` list — `sources` describes *how* to poll, not that polling is wanted on this
host. `start` names this key when it skips a disabled poller, and reports an enabled
poller with an empty `sources` list as *misconfigured* rather than starting a loop
that would exit at once. Where the enabled poller runs — inside the service process
(the default) or as its own — is
[`service.hostIngresses`](/config/cli/service-options#hostingresses) (issue-231).

### `intervalSeconds`

- **Type:** `integer`
- **Default:** `60`

Seconds between poll cycles, across all sources.

::: info Where the ledger lives — `stateFile` is gone
Which comments each item has already been forwarded is tracked in the `poll` section of
that work item's record under [`state.root`](/config/cli/#state-root)
(`<root>/portable/<work item>.json`), so a comment is delivered exactly once across cycles
**and** restarts. It is one record per work item now, not one file for the poller, which is
why `polling.stateFile` was removed in issue-128 — a file path has nothing left to point
at. A config that still sets it is refused rather than ignored; run
[`the-loop migrate-config`](/cli/commands/migrate-config).

Nothing is re-forwarded on upgrade: a pre-issue-128 `poll-state.json` (or the
pre-issue-106 `.the-loop/poll-state.json`) is read once per work item and written forward.
See [State on disk](/cli/state).
:::

### `maxRetries`

- **Type:** `integer`
- **Default:** `3`

Per-event delivery attempts before the poller gives up. A spawn or comment forward whose
dispatch keeps failing is retried each cycle up to this many attempts; after that the
poller logs a terminal failure (`poll.spawn_failed` / `poll.comment_failed`) and ignores
the event on later polls until new activity re-arms it. An in-flight, still-processing
dispatch is not counted as a failed attempt.

Only deliveries that could still *succeed* are counted. An event the daemon refused **on
purpose** — the work item is not started, its session is paused — or a comment that
**was** a control keyword spends no attempt at all: it is resolved as
`poll.comment_settled` and baselined, because no number of retries would change that
answer, and nothing is replayed when the item is started or resumed (issue-270). The
session reads the thread itself; the spawn prompt tells it to.

**An abandoned comment is reported on the work item** (issue-240). Giving up used to be
visible only here, in the event log, and as a 😕 reaction — so somebody who told an agent
to do something had no way to learn it was never told. The poller now posts one comment
naming the abandoned comment, the attempts, and the recovery: **post the instruction
again**, since a new comment carries a full retry budget and nothing on disk needs
editing. It is marked as the-loop's own, so the poller never reads its own notice back.
Best-effort in one direction only — no `gh` on PATH, a non-GitHub provider or an API error
logs `poll.giveup_report_failed` and the give-up stands regardless; a notice can never
make an undelivered comment count as delivered.

**An upgrade re-arms an abandoned comment, once** (issue-146). A give-up is a statement
about a failing environment, and a new the-loop version is the one event that can
invalidate it — the reason those events could not be delivered may be exactly what the
upgrade fixed. So the ledger records *which version* gave up, and the first time a
poller running a **different** version sees that work item it un-resolves those comments
with a full fresh budget (`poll.rearmed`), which is how an item stranded by a bug is
picked up instead of staying stuck forever. Gated on the version rather than on "the
poller started", so repeated `poll --once` runs from cron cannot re-forward abandoned
comments every minute.

The two rules compose, which is how a comment lost to a the-loop bug comes back by itself:
upgrading past the release that fixed it re-arms the comment, the delivery now works, and
if it somehow still does not, the notice above says so on the ticket. Nothing on disk needs
editing in either case.

## Sources

`sources` is an ordered list. Each entry names a `provider`; the remaining keys are that
provider's own config, unknown to the poller core — which is what keeps the core
provider-agnostic. GitHub ships today; the seam admits others.

::: warning An empty `sources` list polls nothing
A directly run poller exits with `no polling sources configured` rather than looping
quietly over an empty list, and [`the-loop start`](/cli/commands/start) reports an
enabled-but-sourceless poller as *misconfigured* without spawning one.
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

::: info All three comment surfaces, not just the conversation
A polled pull request is read on the three surfaces GitHub files instructions under
(issue-246): **conversation comments**, **review bodies**, and **inline review-thread
comments** — the same set the webhook receiver has always handled. Each is forwarded
exactly once, judged by its own author against
[`routing.authorizedUsers`](/config/cli/routing-options#authorizedusers), and an inline
comment arrives with the file and line it is anchored to.

Two reviews carry no instruction and are not forwarded: an **approval with an empty body**,
and a **`PENDING`** review its author has not submitted. A polled **issue** costs exactly
the one request it always did; a polled pull request costs two more (`gh api
repos/…/pulls/<n>/reviews` and `…/comments`, both paginated).
:::

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

- [`the-loop start`](/cli/commands/start) — the command that runs the poller, and how finished work
  items get closed without a `closed` webhook.
- [Routing options](/config/cli/routing-options) — everything the poller reuses.
