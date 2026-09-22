---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#409"
---

# Self-review: the bus keeps an outbox, and `status` reads it

> The `self-review` node's proof, per `reference/reviewing.md`. Critic rounds: no critic is
> configured on this machine (`critics[]` is empty in the checked-in CLI config and no
> critic CLI is installed), so they are recorded **unavailable** and do not count toward
> the operator's `criticReviewCount`.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (this session) | new findings | 6 found, 4 fixed, 2 accepted as designed — below |
| 2 | self (this session) | zero (converged) | re-read the whole diff against the acceptance criteria and the security design; no new finding |
| critic 1–3 | — | **unavailable** | no critic configured on this machine |

## Round 1 findings

**F1 — the backlog was not reliably ordered.** Entry ids were stamped to the second, so two
events queued inside the same second sorted by their random suffix. "Oldest first" is load
bearing twice — the drain's order and the cap's eviction — and the cap test caught it by
dropping `q4`, `q0`, `q3`. **Fixed**: the id carries a fixed-width microsecond stamp, which
sorts lexicographically; the drain and eviction tests now assert the order by content.

**F2 — an entry the CLI could not read counted as delivered.** The settle step keyed on
"empty error means delivered", so an entry whose payload named no event type left the queue
*and* incremented `delivered`. **Fixed**: removal and delivery are now separate lists, and
an unreadable entry is dropped with a `warning` and counted as neither.

**F3 — the status line promised a retry nothing would perform.** `— retried every 60s` was
printed unconditionally, but the drain lives in the poller and the webhook receiver: a
deployment running neither holds a backlog forever. **Fixed**: the line reads the report's
own service rows and says `nothing is draining them: start the poller or the webhook
receiver` when neither is running. Both variants are asserted.

**F4 — the channel name appeared twice in the error.** `_first_error` prefixed every
message with the channel, and the Slack channel already names itself, producing
`slack: slack: could not open a thread`. **Fixed**: the prefix is added only when the
message does not already carry it.

**F5 — a burst of comment mirrors can evict an older question.** The cap drops the oldest
entry, and `comment.agent` / `comment.human` mirrors go through the same `publish`. During a
long outage a stream of comment mirrors can push a question past the 200-entry cap.
**Accepted as designed**: the alternative — a per-type priority — buys a rarer loss at the
cost of a queue whose behaviour an operator cannot predict, and the loss is loud
(`channel.undelivered_dropped` at `warning`, counted in `status`) and never silent. The
question also still stands on its ticket, which is where it was recorded first. Recorded in
`design.md` § What it costs and in the state page.

**F6 — the reporter's own remedy was not implemented.** The issue asks for
`publish_comment` to treat the envelope as "already delivered" only when a recorded publish
reached `posted >= 1`. **Accepted as designed, and answered in writing**: the ledger records
*before* the fan-out (so the record's URL can ride onto the event every channel renders), so
a delivery count can only reach the comment as a second write — and both ingresses read the
comment before that write lands, the webhook router within about a second. The fix would
appear to work under polling and silently not work under webhooks. A mirror is also not the
delivery that failed: `comment.agent` reaches a different subscriber set with a different
rendering. `bugfix.md` § What about the envelope refusal the report names carries the
argument, and the envelope's claim becomes true again once an undelivered event is
remembered rather than dropped.

## Round 2

Re-read the diff end to end against each acceptance criterion and each claim of
`design.md` § Security design. Checked in particular:

- every new `except` is the module's documented best-effort contract, and none of them
  swallows a failure without a log line;
- `publish`'s three guards are each exercised by a test that fails without them;
- the drain's two locked sections are short and hold no network call between them;
- nothing new writes to the ledger, and `the_loop.channels.bus.publish` is monkeypatched to
  fail the test if the drain ever calls it;
- the three new event payloads carry ids, counts and provider errors only.

No further finding.

## Evidence trail

- Verification: [verification.md](verification.md) — the whole matrix.
- Security: [security-review.md](security-review.md).
- Docs: [documentation.md](documentation.md).
