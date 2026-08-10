# Decision 072: `poll start --daemon` is opt-in, not the default

- **Status:** proposed — the human gate is the pull request
- **Date:** 2026-08-10
- **Deciders:** MadaraUchiha-314 (approver)
- **Work item:** [issue-191](https://github.com/MadaraUchiha-314/the-loop/issues/191)

## Context

[Issue #191](https://github.com/MadaraUchiha-314/the-loop/issues/191) asks `poll start` to
become a proper daemon — detach, redirect, own the pidfile lifecycle — and leaves one
choice open in its own words: *"Add a `--daemon` flag to `poll start` (or make it the
default, with `--foreground` for systemd/supervisors)."*

The principle behind the ticket argues for the default: *anything the operator has to
remember, the tool should do*. Two facts argue the other way, and they are about who else
runs this command.

- `poll start` is already the **supervised** entry point. A systemd `Type=simple` unit
  tracks the process it launched; if that process forks and exits, systemd reads it as a
  failed start and — depending on `Restart=` — loops. Nothing in the unit file would say
  what changed, and the failure appears on upgrade rather than at install.
- `poll start` is also the **interactive** entry point. An operator running it in a
  terminal to watch a cycle expects output, not an immediate prompt.

So the two spellings do not have symmetric costs: making the flag opt-in costs one
discoverable word on a command line, while making it the default costs a silent behaviour
change in other people's supervisors.

## Decision

**`poll start` keeps running in the foreground by default.** Detaching is `--daemon`, with
`--foreground` as its explicit inverse — one `argparse` `dest`, so the last flag on the
line wins and a wrapper script can force either.

`--daemon --once` is refused rather than ignored: a single cycle has nothing to detach for,
and detaching would hide its exit code from the cron job that asked for it.

**Nothing about this lives in the CLI config.** A `polling.daemon` key would let a host
default to detaching — and would then also apply to `the_loop.daemon_entry`, where the
control plane has *already* detached the process with `start_new_session=True`, so it would
double-fork and orphan the pid the control plane just reported. A flag has no such reach.

## Consequences

**Easier.** Every existing invocation — cron with `--once`, systemd `Type=simple`, a
terminal, a supervisor — behaves exactly as it did. The five-part incantation the ticket
opens with collapses to one flag, and `--daemon` is discoverable in `poll start --help`
rather than being folk knowledge.

**Harder.** An operator who wants a detached poller must still type something. That is the
whole cost, and it buys the guarantee that nobody's supervisor changes shape under them.
Should the balance shift — the flag being forgotten in practice, foreground starts being
rare — flipping the default later is a one-line change plus a release note, whereas
un-flipping it after breaking supervisors is not.

**Unchanged.** Supervision itself. `--daemon` makes a poller outlive its *shell*; surviving
a reboot, a suspend or a `SIGKILL` remains systemd's, cron's or a keepalive's job — which
is why `poll status` exits `0`/`1` on liveness, so a keepalive is one line.

## Alternatives considered

- **Detach by default, `--foreground` to opt out** — the ticket's other option. Rejected on
  the supervisor argument above: the failure mode is silent, appears on upgrade, and lands
  in configuration the-loop does not own.
- **A `polling.daemon` config key** (either default). Rejected: it reaches `daemon_entry`,
  where a second daemonization orphans the pid the control plane reports, and it answers a
  question that belongs to *this invocation* rather than to the host.
- **A separate `poll daemon` verb.** Rejected: it duplicates every flag `start` has, and
  "start it, detached" is a modifier on starting, not a different act.
