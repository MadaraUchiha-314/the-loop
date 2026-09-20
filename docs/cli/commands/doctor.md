# `doctor`

Deployment-wide diagnosis of one integration. Today that is Slack
([issue-393](https://github.com/MadaraUchiha-314/the-loop/issues/393), F2): the three
questions an e2e failure could not answer from any log — does the installed app hear what
the manifest says it should, does every room this daemon declares resolve in its own
directory, and is a **second Socket Mode consumer** quietly taking half of the events.

```bash
the-loop doctor slack [--beats N] [--window SECONDS] [--no-heartbeat]
```

Where [`channels status --probe`](/cli/commands/channels) asks Slack about the *app*, the
doctor asks about the *deployment*. It prints ids and channel names only — never a token —
and it is honest about its limits: a probe that cannot run prints `[?] unverifiable`, never
`[ok]`, and the heartbeat verdict always calls itself **evidence, not proof**. Exit 1 when
any `[!]` finding was printed, 0 otherwise.

| Flag | Default | Meaning |
|------|---------|---------|
| `--beats N` | `3` | How many heartbeat messages to post. With two consumers sharing the token, a split hides one time in 2^N. |
| `--window SECONDS` | `5` | How long to wait for the heartbeats to come back. |
| `--no-heartbeat` | off | Skip the second-consumer probe; the doctor then posts nothing to Slack. |

## The report

```
slack doctor — ids and channel names only, never tokens; where a line says evidence it is not proof
app:
  channel kind: …
  probe:        conversations.info says private channel; granted bot scopes: …
  events:       the manifest subscribes the bot to message.channels, message.groups, message.im, message.mpim, app_mention — not verifiable through the API …
channels:
  [ok] C0123ABCD — listed in the bot's directory (channels.slack.channel)
  [ok] test-room → G0456EFGH (declared by owner/repo#12)
  [!]  nowhere → resolves to no channel this bot can see (declared by owner/repo#13) — …
consumers:
  [ok] 3/3 heartbeats reached the running listener (read back from its event log) within 5s — no second Socket Mode consumer observed. Evidence, not proof: …
```

**app** — the same lines `channels status --probe` prints, plus the `events:` line: the bot
events the packaged manifest subscribes to. Slack's API has **no method that lists an app's
event subscriptions**, so an app imported from an older manifest reads as healthy on every
probe while hearing nothing; the line says so and names the test — send the bot a mention.

**channels** — `channels.slack.channel` and every room a work item declared, each resolved
in the bot's own directory (its memberships first, then the workspace listing). A declared
*name* that resolves to nothing is a miss; a declared *id* the directory never lists means
the bot is not in that room; a miss over a listing the page cap cut short says so, because
the name may exist beyond the cap — declare the id instead.

**consumers** — the heartbeat probe. Slack load-balances an app's events across every open
Socket Mode connection, so a second the-loop instance, a stale `channels listen` or another
host on the same app-level token silently halves what each one hears — and Slack exposes
**no API that lists an app's connections**. So the doctor measures: it posts `--beats`
fixed-format nonce messages into the configured channel, counts how many come back within
`--window`, and deletes them again. Who receives them depends on what runs here:

- when this instance's **listener is running**, it is the receiver — it records each
  heartbeat it hears as a `channel.heartbeat` event, and the doctor reads the
  [event log](/cli/state) back (a second connection beside the listener would itself split
  the events and measure the doctor, not the deployment);
- when **no listener runs here**, the doctor opens its own Socket Mode connection and
  receives directly, acknowledging only its own heartbeats so a member's real message is
  left for Slack to redeliver.

A shortfall reads `[!] … another Socket Mode consumer may hold this app's connection` — find
every process connected with this app-level token and stop all but one. A full count reads
`[ok]`, still hedged: a consumer that was idle or reconnecting during the window would not
show. A listener started on a build older than this one records no heartbeat at all —
`the-loop restart` on this build first.
