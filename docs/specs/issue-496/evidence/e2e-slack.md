---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T4 — the Slack Socket Mode path, end to end

> The author's one live proof (R12): one Slack app (the author's, tokens by variable
> name from `~/.the-loop/the-loop.env`), one gateway, one instance `laptop-a` with Slack
> disabled locally, against [the-loop-testing#7](https://github.com/MadaraUchiha-314/the-loop-testing/issues/7),
> gateway and instance on one machine (R14). Slack ids, paths and peer ids are redacted.

## Step 1 — arm through the gateway, routed by the author's registered actor

the-loop-testing#7 was opened with the two auto-execute labels. The gateway's poller
listed it and offered a presence event; the gateway routed it to `laptop-a` **by actor**
(the issue's author is `laptop-a`'s registered GitHub actor); `laptop-a` fetched it,
prepared its checkout and — `requireStartCommand` being on for the first attempt —
dropped it as `awaiting-start`, which the gateway's poll ledger learned from the commit
and offered again on the next cycle. With the start command requirement off, the next
presence spawned the work item's record: `laptop-a` posted the phase-selection checklist
on #7 and parked at the human start gate (`session.spawn_deferred:
parked-at-human-start-gate`). Its own checklist comment came back through the gateway
(routed by actor) and its router dropped it as `self-authored` — the self-marker check
running on the instance, as designed (R5.6).

Gateway log:

```text

```

Instance log (`gateway_event_id` beside the delivery id on every record, R10.2):

```text

```

```text
the-loop gateway subjects --config …
subject                                          claimants  events  held  pending  oldest  dead
loop-github-MadaraUchiha-314-the-loop-testing-7  -          3       0     0        -       0
unassigned                                       -          2       2     0        -       0
```

The two events held on `unassigned` are the bot's own Slack messages (Slack delivers an
app's posts back over its connection; their `user` is the bot's id, which no instance
registers), so they wait for retention. Harmless; a follow-up may drop bot-authored
messages at the gateway.

## Steps 2–5

Steps 2 and 3 need the author (a reply in the session's Slack thread; two replies while
`laptop-a` is stopped), asked for on the ticket on 2026-10-19. Recorded below as they
happen, with the second-instance (`laptop-b`), duplicate-name (`laptop-a` copy) and
close steps.
