---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#482"
---

# Self-review: spawned sessions never receive a secret (issue-482, issue-485)

## Round 1 — findings, all fixed before the PR

1. **A broken provider stripped nothing.** `TmuxRunner.spawn_environment` returned an
   empty boundary when the provider raised, so the pane inherited the server's token.
   Now it falls back to the default credential names (fail closed); tested.
2. **The no-service message misdescribed a person.** It said "this session was started by
   the daemon" even when a person had exported `THE_LOOP_CLI_CONFIG` at a terminal. It now
   names the variable that triggered it and says what a daemon session holds.
3. **A malformed credential value could break the spawn.** Any string under a `*tokenEnv`
   key reached `env -u`; a value such as `A=B` makes `env` exit. Only valid names are
   collected now; tested.

## Round 2 — no new findings

Re-read the diff for: `env -u` with no names (no prefix is added); the pre-3.2 tmux path
(no `-e`, still stripped; tested); `respawn-pane` (same boundary; tested); the restart
verb with an empty env file (relaunches, by R5.2; tested); the contract parity test (passes
with `askSession`); a pane's pid after `env` execs (the harness's, so the issue-410 probe
reads the right process; the real-tmux test waits for it).

## Notes for the reviewer

- **Breaking.** Operators who relied on `env.file` reaching sessions (for example `gh` in a
  pane using `GH_TOKEN`) lose that; the commit is marked breaking so the release says so.
- **Kept for later, per #482 R3.** The in-process fallback outside a daemon session is
  unchanged; its explicit opt-in is a separate decision.
- **Not in scope.** The workspace-trust pre-seed in #482 § Related.

## Critic review

No critic harness is installed in this cloud session (`the-loop critic list` has nothing
to run), so the critic rounds did not run. The PR review is the next reader.
