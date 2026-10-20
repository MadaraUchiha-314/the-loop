<!-- Written per the `the-loop:writing` skill. -->

# Decision 147: `read.mode` names the Slack transport; interactivity is derived from it, and `gateway` fails closed

- **Status:** proposed (the owner decides at the PR)
- **Date:** 2026-10-20
- **Deciders:** MadaraUchiha-314 (chose option 1, a new read mode, on the ticket, 2026-10-20), the-loop (design)
- **Work item:** [issue-503](https://github.com/MadaraUchiha-314/the-loop/issues/503)
- **Spec:** [`docs/specs/issue-503/design.md`](../specs/issue-503/design.md) §Trade-offs & decisions
- **Refines:** [decision-103](decision-103.md) D5 (a button nobody can receive is worse than none), [decision-116](decision-116.md) D5 (an interactive payload reaches the-loop only over an acknowledging connection)

## Context

`channels.slack.read.mode` did two jobs. It chose the transport, and `== "socket"` was
also the switch for the Approve / Request changes buttons, the Execute / Start buttons
and the kickoff picker. Behind a gateway (issue-496) the only working value was
`socket`, and the `gateway:` block silently stopped the listener that `socket` asks for.
Deleting the block then opened a second Socket Mode consumer on the gateway's app.

## Decision

- **`read.mode` names the transport:** `poll | socket | gateway | off`. Whether
  interactivity is available is derived from it. `push_reachable` is true for `socket`,
  and for `gateway` with a usable `gateway` block. The three gates each combine it with
  their unchanged grant.
- **`gateway` without a block resolves to `off` at parse time,** with an error. This is
  the same move an unknown value already gets, so every reader of the mode fails closed
  with no check of its own. It never falls back to a socket.
- **A Socket Mode connection opens only on an explicit `socket` with no `gateway`
  block.** `the-loop channels listen` refuses beside any block, before it reads a token.
- **The 20.3.0 form (`gateway` + `socket`) is migrated broadly and refused narrowly.**
  It keeps working, is warned about in the log and in `channels status`, and
  `migrate-config` rewrites it. It is detected by its own predicate, and the config
  version is not bumped.

## Consequences

- An operator behind a gateway writes what the instance does, and a deleted block can no
  longer split the app's envelopes.
- Leaving a gateway is now two edits: remove the block, and set `read.mode` back to
  `socket` or `poll`. A block-less `gateway` mode reads nothing, on purpose.
- The rule for a usable block lives in two places: `cli_config.gateway_block` (logging)
  and `migrations._socket_beside_gateway` (quiet). A change to one must be made to both.

## Alternatives considered

- **A separate `read.listener: false` switch (option 2 on the ticket).** This keeps
  `socket` as the mode and adds a second key that must agree with it. The owner chose
  option 1.
- **Keep `gateway` without a block as `gateway`, and let each reader check the block.**
  That is a dozen call sites to keep right. Resolving at parse time is one.
- **Refuse `gateway` + `socket` at load, or bump the config version.** Either would stop
  every 20.3.0 gateway instance on upgrade over a value that still works.
