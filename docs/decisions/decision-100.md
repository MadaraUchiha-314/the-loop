# Decision 100: standing sessions are created and deleted at runtime; the control plane is not a channel

- **Status:** accepted
- **Date:** 2026-08-20
- **Work item:** [issue-277](https://github.com/MadaraUchiha-314/the-loop/issues/277)
- **Deciders:** MadaraUchiha-314 (owner — [ruling on PR #278](https://github.com/MadaraUchiha-314/the-loop/pull/278#issuecomment-5358714877)), the-loop (proposal)
- **Refines:** [decision-099](decision-099.md) (a session that owns no work item lives in its own namespace)

## Context

Reviewing [PR #278](https://github.com/MadaraUchiha-314/the-loop/pull/278), the owner asked
how an operator actually interacts with a standing session, and whether the control plane
ought to be modelled as a `channel` alongside Slack.

Answering it surfaced a defect: a standing session could be *spoken to* three ways
(`standing say`, a Slack thread reply, `tmux attach`) and could speak back **no** way,
because both outbound paths a work-item session has — `ask_session()` and
`GET /api/v1/sessions/transcript` — begin with `WorkItemRef.parse(ref)` and so cannot serve
a session that owns no ticket.

the-loop proposed two options: **A**, give a standing session an outbound verb of its own;
**B**, make the control plane a declared channel by lifting the shared policy
(*authorize → mark → record → deliver*) out of `core.sessions` and `channels.inbound`.

The owner chose neither, and narrowed the scope instead.

## Decision

**The owner's ruling, verbatim in substance:**

1. **"Forget about control plane as a channel."** Option B is withdrawn. The `Channel`
   protocol stays Slack's; no `channels.controlPlane` is introduced.
2. **There are three ways to interact with a standing session, and no others are built
   here:** typing directly into its tmux session, a reply in its Slack thread, and the
   control plane's messaging path.
3. **"We already have a way to interact with a tmux session through control plane, let's
   reuse that."** So option A is withdrawn too: no bespoke `standing ask` verb, no
   name-keyed transcript route. The pane is how a standing session is read, and
   `standing say` — which already reuses `TmuxRunner.deliver_to` — is how it is written to.
4. **"Let's just do the APIs that create the adhoc session and delete that adhoc session."**
   The scope that *is* added: a standing session can be brought into existence and removed
   through the API, rather than only by editing `standingSessions.sessions` and restarting.

## Consequences

**Easier.**

- A standing session stops being a config-file ceremony. `create` gives it a definition in
  the registry and starts it; `delete` stops it and forgets it.
- The `Channel` protocol keeps one implementation and one meaning. The stream keeps the
  no-per-subscriber-filter property issue-239 argued for, and no HTTP route has to
  impersonate a polled message queue.
- The scope of #277 stays the scope of #277.

**Harder.**

- A definition now has two possible sources — the config, or the registry — so every verb
  has to resolve it through one seam (`_entry_for`) or the two lifecycles diverge. That
  seam is the design's answer (design.md §D8) and the reason the record grew to carry the
  whole definition.
- `the-loop start` must restore created sessions that auto-start, because `stop_all`
  already stops every recorded one. Without the symmetry, `restart` would destroy exactly
  what the API created.

**Accepted, with eyes open.** A standing session still cannot *initiate* — it can be read
only by someone looking at its pane (locally, over SSH, or through the ttyd web terminal).
The owner judged that sufficient, and the alternative is recorded here rather than lost, so
a future ticket can reopen it without re-deriving the argument.

## Alternatives considered

- **B — the control plane as a declared channel.** Rejected by the owner. On the merits
  the-loop had also argued against the *mechanism*: `Channel.post()` is an event-typed push
  to a subscribed surface while `GET /api/v1/stream` is a log tail with deliberately no
  per-subscriber filter, and a channel's inbound half is *collected* (cursor, thread
  binding) while the control plane's is a synchronous request that binds nothing. What
  would have paid is unifying the *policy*, not the transport — recorded here in case the
  question returns.
- **A — an outbound verb for standing sessions** (`standing ask`, a name-keyed transcript
  route). Rejected: reuse what already talks to a tmux session.
- **Making `create` adopt an existing session of the same name.** Rejected: a name is one
  session, and adopting silently would let a create take over a running agent.
- **Letting `delete` remove a declared session's record.** Rejected: `the-loop start`
  would recreate it on the next boot, so the verb would be lying. Declared sessions are
  removed by editing the config; `stop` is the runtime verb for them.
