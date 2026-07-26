# Decision 040: all daemon runtime state lives under `.the-loop/state/`, with the pre-move paths still honoured

- **Status:** proposed
- **Date:** 2026-07-26
- **Deciders:** @MadaraUchiha-314 (review of PR #100, issue #98)
- **Work item:** issue-98
- **Spec:** `docs/specs/issue-98/`

## Context

Review comment on PR #100: *"We have all these files that we are tracking now
like `poll-state.json`, `poll.pid`, all files in `sessions/` folder. Now we are
introducing another file. Can we consolidate?"*

`.the-loop/` had grown into two different things sharing one directory:

| Kind | Files | Who writes them |
|---|---|---|
| **Config** | `cli-config.yaml`, `harness-config.yaml`, the schemas, `collaborators.yaml`, `manifest.yaml` | a human, often checked in |
| **Runtime state** | `sessions/`, `poll-state.json`, `poll.pid`, `gh-webhook.pid`, `logs/events.jsonl` | the daemon, always git-ignored |

The state half had accumulated one path (and one `.gitignore` line) per feature,
at the same level as the config an operator edits. Nothing marked the boundary
except naming convention and five separate ignore rules — so "is this file mine
or the daemon's?" had no structural answer, and issue-98's pause ledger was
about to add a sixth top-level entry.

## Decision

**One directory for everything the daemon writes: `.the-loop/state/`.**

```text
.the-loop/
  cli-config.yaml              # config — yours
  state/                       # runtime state — the daemon's, one ignore line
    sessions/<slug>.json       # routing.registryDir
    paused.json                # routing.pauseFile
    poll-state.json            # polling.stateFile
    poll.pid  gh-webhook.pid   # polling.pidfile / webhooks.ghWebhook.pidfile
    logs/events.jsonl          # eventLog.path
```

Config vs state becomes a **directory boundary** rather than a naming
convention. `.gitignore` needs one rule. A new piece of state has an obvious
home, so the question this decision answers cannot recur.

**Existing installs are not broken, and are not migrated behind the operator's
back.** `the_loop.state.resolve()` reads the pre-move path whenever *that* is
the one that exists, logging the fact once and pointing at
`the-loop state migrate`. An explicitly configured path always wins and is never
reinterpreted. `the-loop state paths` shows which layout each entry is on.

**Migration is a command, not a startup side effect.** `the-loop state migrate`
moves the pre-move files over; it refuses while a daemon's pidfile looks alive
(`--force` overrides), skips an entry whose target already exists rather than
clobbering it, and supports `--dry-run`.

## Consequences

### Good

- One ignore rule; `rm -rf .the-loop/state` is now a complete, safe reset.
- The daemon's files stop being mixed in with the operator's.
- Where state goes is settled — the same question does not get re-litigated per
  feature (issue-98's pause ledger was the trigger, not the cause).
- `state paths` gives an operator a straight answer to "where is my registry?",
  which previously meant reading three config blocks.

### Costs and risks

- Six config defaults changed at once. Mitigated by the fallback: an operator
  who upgrades and does nothing keeps working exactly as before.
- Two layouts can coexist, which is a real (if inert) state: `state paths`
  labels each entry, and `migrate` refuses to merge a conflicting pair.
- Moving a live registry or pidfile would let two daemons believe they own the
  same work item — hence the running-daemon guard on `migrate`, and hence no
  automatic migration on daemon start.

## Alternatives considered

- **Fold the pause ledger into `sessions/`** — no new top-level file, no
  migration, but a global ledger inside a directory whose contract is "one file
  per session", and the registry's `*.json` glob would need an exclusion. Tidier
  on disk, muddier in the model; it also leaves the four *other* scattered paths
  exactly as they were.
- **Fold it into `poll-state.json`** — rejected outright: pause applies to the
  webhook path too, and the CLI would be writing into a file the poller owns.
- **Migrate automatically on daemon start** — convenient, but it moves files out
  from under whatever else is running, and does it at the worst possible moment
  (start-up, unattended). The fallback gives the same continuity with none of
  the risk.
- **Leave it as it was** — the honest cost is one more top-level file per
  feature, forever, and no boundary between config and state.
