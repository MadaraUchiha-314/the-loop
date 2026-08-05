# Decision 056: tmux is the only runner — the headless process runner is removed

- **Status:** proposed
- **Date:** 2026-08-05
- **Deciders:** @MadaraUchiha-314 (issue #156 comment)
- **Work item:** issue-156
- **Spec:** `docs/specs/issue-156/`

## Context

Since decision-021, `routing.runner` chose between two ways of hosting a
daemon-driven session: the original headless one-shot subprocess of
decision-016 (`claude -p … --resume`, default) and the attachable tmux-hosted
TUI. The choice was made at first spawn and then **copied into the session
record**, and every later dispatch trusted the copy ("the session's recorded
runner wins", mixed fleets). Issue #156 showed the cost: a record whose
`runner` field says `"process"` — the silent dataclass default, written by
every `sessions register` — reroutes all future events for that work item to
an invisible subprocess while the operator watches an idle tmux pane. No
reconciliation, no warning; the failure mode is silence.

## Decision

Remove the process runner entirely (owner decision on the ticket):

- Every daemon-spawned session is hosted in a named tmux session
  (`loop-<slug>`); `tmux` becomes a required dependency of `gh-webhook start`
  / `poll start`.
- `routing.runner` leaves the config schema; a leftover key is ignored with a
  warning, never an error.
- The session record's `runner` field is removed; a legacy record carrying one
  parses fine and the key is not read. A record with no `tmuxTarget` (legacy
  process records, `sessions register` self-registrations) heals lazily: its
  next dispatched event takes the existing respawn path (issues 80/89/146) and
  resumes the recorded conversation in a fresh tmux session when possible.
- The harness adapter contract loses its headless per-dispatch
  `spawn`/`resume` surface. The **one-shot** invocation used by critic reviews
  (`oneshot_argv`, decision-043) is explicitly retained — it is a review
  mechanism, not a session runner — as are the interactive tmux methods.

## Consequences

- The issue's defect class is structurally gone: with one runner there is no
  per-record selector to go stale and no silent execution path to fall into.
- Supersedes the runner *choice* of decision-021 (whose tmux design otherwise
  stands in full) and the headless per-event dispatch of decision-016 (whose
  CLI-not-MCP and adapter-contract decisions stand; the CLI is now invoked
  interactively under tmux, or one-shot for critics).
- Mixed fleets (per-work-item runner selection, deferred by decision-021) are
  off the table by construction.
- cursor-agent cannot pre-assign an interactive session id, so it cannot host
  daemon sessions; it remains a critic harness. Interactive cursor support is
  a future adapter change, not a config toggle.
