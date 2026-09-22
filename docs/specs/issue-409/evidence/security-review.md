---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#409"
---

# Security review: the bus keeps an outbox, and `status` reads it

> The `security-review` gate's record (`reference/security.md`). Risk tier 3, so the
> autonomous review suffices: no auth, credential, secret or schema path is touched, and
> nothing here changes who may do what. Run with the repository's own
> security-review checklist over the whole diff.

## What the change introduces

One new artefact — `<state.root>/channels/undelivered.json` — and one new action: posting a
stored event to a channel later than it was published. Everything else is a guard, a log
line or a rendered string.

## Findings

**No findings requiring a decision.** The four claims of `design.md` § Security design were
each checked against the code and pinned by a test:

| Claim | How it is established | Where |
|---|---|---|
| A replayed entry can never write to the ledger | the drain calls `channel.post` directly and never `bus.publish`; the test monkeypatches `bus.publish` to fail the test if it is reached | `outbox._post`, `test_the_drain_posts_where_publish_would_have_and_never_records` |
| The event log carries no message text | the three new emits name event type, work item, channel names, counts, waited seconds and the provider's error | `test_an_event_no_channel_took_is_queued_with_everything_needed_to_repost` asserts the question's text is absent from the payload |
| The file never travels | declared `portable=False` in `GENERATED_PATHS` with its reason, and classified **local** on the state page | `state.py`, `docs/cli/state.md`, `test_state_portability.py` |
| The backlog is bounded | 200 entries, 20 posts per cycle, a per-entry backoff from 60s to 1h | `test_the_cap_drops_the_oldest_and_says_so`, `test_one_cycle_attempts_at_most_its_budget…` |

## The abuse cases considered

- **Text at rest.** An entry holds the event's text — an agent's question, a relayed reply,
  a decision. It sits under the deployment's state root, in a file `tempfile.mkstemp`
  creates `0600` and `os.replace` keeps at `0600`, beside the channel state that already
  holds thread ids, member ids and pending kickoff messages. It is the same text that was
  one API call from the channel, stored without re-deciding any scrub, and it leaves on
  delivery. Bounded at 200 entries.
- **Replay as an escalation.** The dangerous events are the ones the ledger records as
  *unmarked* comments (`gate.feedback`, `control.command`) and `work-item.create`. Each
  reaches the ledger through `publish`'s **record** step, which the drain does not have:
  the queued copy can only be posted to a channel. A replayed `work-item.create` posts a
  message; it cannot open a second issue.
- **Replay to the wrong room.** The drain resolves channels from the **current** config, so
  a channel an operator removed is never posted to, and a work item whose room changed is
  posted to the room it has now.
- **Recovery as a denial of service.** A rate limit is one of the failures that fills the
  outbox, so an unthrottled drain would re-create it. The per-cycle budget and the doubling
  per-entry backoff bound the recovery at 20 posts a cycle and one attempt per entry per
  hour once it has failed eleven times.
- **A poisoned outbox.** The file is under the operator's state root; anyone who can write
  it can already write the CLI config. Even so, every field is coerced on load, an entry
  that names no event type is dropped rather than retried, and a corrupt file reads as an
  empty backlog instead of raising — so the worst a malformed file costs is the backlog it
  was holding, never a crashed publish or a crashed `status`.
- **Hiding a failure.** The inverse risk, and the one the ticket is about: the change makes
  the failure *louder* — `warning` instead of `debug`, plus a line on the operator's
  primary status surface, which says explicitly when no daemon is running to drain the
  queue.

## Sign-off

Tier 3: no named human security sign-off is required (that threshold is tier 4). No
unresolved finding blocks completion.
