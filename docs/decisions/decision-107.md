# Decision 107: a work item's channel conversation opens on the spawn path, as a channel operation, best-effort

- **Status:** proposed
- **Date:** 2026-09-03
- **Work item:** [issue-317](https://github.com/MadaraUchiha-314/the-loop/issues/317)
- **Deciders:** MadaraUchiha-314 (owner, via the ticket), the-loop (design)
- **Refines:** [decision-105](decision-105.md) (the thread is the work item's, opened
  once under a lock), [decision-103](decision-103.md) (the bus is the only caller of a
  channel)

## Context

Issue-312 made the Slack thread the work item's — a root that names it, every event a
reply — but left it opened **lazily**, by the first event the channel delivered. A started
work item whose first phase is a human gate can sit for minutes with an announcement on
the ticket and nothing on Slack. The owner asked for the thread (or a channel's
equivalent) to exist as soon as `the-loop start` happens.

Three things had to be chosen: *where* in the-loop "start happens" for every way of
starting, *what* the open is (an event on the bus, or an operation on a channel), and
*what a failure costs*.

## Decision

| # | What was chosen | Why |
|---|-----------------|-----|
| D1 | **The seam is the dispatcher's spawn path — `_spawn_for`, before the workspace checkout.** An injected opener is called with the work item's ref once every refusal has been passed. | Every way of starting a work item — the comment keywords, `the-loop sessions start`, the control plane's route, the MCP tool, and the poller's presence spawn for an authorized author — converges there and nowhere else; the control record does not (the CLI writes it outside the dispatcher, and the poller's presence path never writes one). Before the checkout rather than beside the announcement: the thread is the point, and a clone can take a minute. A spawn that fails afterwards leaves a thread; a thread is attribution, not a standing request, and the retry reuses it. |
| D2 | **The open is a channel operation (`open`), driven by the bus (`open_conversation`), not a bus event.** | A bus event is subscribe-gated — a channel not subscribed to it would get no thread, against "all the channels configured" — and it would land a first reply nobody asked for. A channel that has no conversation to open (the ledger: the issue is the conversation) simply lacks the method and is skipped. The bus stays the only caller of a channel. |
| D3 | **Best-effort, recorded, never a spawn outcome.** A channel that raises or returns no `ts` is `channel.open_failed`; the spawn proceeds; the next event opens the thread lazily as before. | The channel has been best-effort by contract since issue-245; a Slack outage must not stop a work item from starting. Laziness is kept as the fallback, not removed. |
| D4 | **The conversation records origin `start`.** | An operator debugging "where did this message go" can tell a thread the start opened from one an event opened; the record's shape is unchanged and an older reader coerces the value to `event`. |

## Consequences

**Good.** The thread exists the moment a start is accepted, on every channel, from every
entry point; the first event is the first reply; refused starts leave nothing on any
channel; embedders get one injectable seam with the comment publisher's shape.

**Costs, accepted.** One more attribute on the dispatcher and one more builder parameter;
a failed spawn can leave a root with no replies (harmless, reused); a `the-loop start` that
finds a live session opens nothing (no spawn, no open — the next event does).

## Alternatives considered

| Alternative | Why not |
|-------------|---------|
| Open at the control record (`_apply_control` / `_spawn_for_start`) | Two writers of the record outside one seam, and the poller's authorized-author presence spawn never writes one; a refused start would need its own un-open |
| A `work-item.started` event published on the bus | Subscribe-gated, so "all channels" is not guaranteed; leaves an unasked-for first reply; the announcement already reaches a subscribed thread as `comment.agent` |
| Open beside the announcement, after `_spawn_tmux` | The thread would appear after the clone and the harness boot — the delay the ticket is about |
| Open from the graph's first node (a hook) | Runs inside the harness session, after the boot prompt, and only on the graph path; a session that never reaches the graph would open nothing |
