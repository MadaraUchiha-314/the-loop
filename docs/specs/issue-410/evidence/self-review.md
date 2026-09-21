---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#410"
---

# Self-review: roll running sessions onto a refreshed environment (issue-410)

## Round 1 — self

Read the whole diff against the requirements, the minimalism ladder and
`reference/security.md`.

### What I changed as a result

1. **Dropped a no-op helper.** The first draft of `envstate` carried an `_unused_guard`
   function keeping an import alive. Bloat with a comment attached; both went.
2. **Made `envstate` a module-level import in `core/sessions.py`.** It started as four
   function-local imports, which is how the module ends up with no seam a test can reach.
   One import at the top; the local ones removed.
3. **Two defects found by reading the diff against the requirements, both now
   covered by a test that fails without the fix:**
   - `restart_sessions` built its `TmuxRunner` with **no `env_provider`**, so the
     respawn carried no `-e` at all: every session would have been relaunched
     straight back onto the retired credential and then correctly reported stale.
     The scripted-runner tests could not see it — the double *is* the seam — so the
     double now records what the pane would be handed, and the real-tmux transcript
     in `evidence/verification.md` exercises the wired path.
   - `_env_flags` dropped every pair with an empty value, which is right for
     the-loop's own three variables (an unnamed instance exports nothing) and wrong
     for a declared one: `NAME=` in an env file is an operator **blanking** a
     credential, and skipping it would leave the pane inheriting the very value they
     just retired — reported stale on every later run, forever. The empty-filter now
     applies only to the-loop's own names.
4. **Batched the fleet read.** `status_all` now calls the drift read on every
   invocation, and the first draft used `live_pane_pids` per session — one subprocess
   each. `the-loop status` is documented as the keepalive primitive
   (`the-loop status || …`), so a 20-session deployment would have gone from ~4 tmux
   spawns per health check to ~24. `live_pane_pids_by_session` reads the whole server
   in one `list-panes -a`, with the same dead-pane and positive-pid rules.
5. **Checked a claim I had written as fact, and corrected it.** The design and the
   operator docs said `respawn-pane -k` keeps the pane's scrollback. It does not — tmux
   clears the pane. Verified directly (`evidence/verification.md` § Scrollback) and
   rewritten in all three places: what the verb actually buys is that the session and
   window keep their identity so an attached operator is not dropped. A smaller claim,
   and a true one; the cost is now stated to operators instead of glossed.
6. **Corrected an env-file doc claim rather than leaving it.** `docs/config/cli/index.md`
   said "Read once, at start. A change to the file needs a restart" — no longer true of a
   spawned session, and a half-true statement about credentials is worse than none. It now
   says what is frozen, what is not, and which verb rolls the rest.

### Things I deliberately did not do

- **No HTTP route and no MCP tool.** `restart` follows `reset`: routing recovery through
  the control-plane service would make it depend on the thing an operator runs it to
  repair, and it replaces processes on this host either way. That keeps the OpenAPI
  contract, the SDK and the MCP surface untouched.
- **No new config key, state file or registry field.** The env file and the running
  processes are both already there; the answer is a comparison of the two at the moment it
  is asked. A recorded fingerprint would be one more thing that can go stale.
- **No re-derivation of the harness launch flags.** The reporter filed that separately and
  scoped it out. A relaunched session comes back on the argv the registry recorded, so
  this change refreshes the environment and nothing else — folding the two together would
  have shipped a second behaviour change under one review.
- **No fresh-conversation fallback.** The dispatcher's respawn path falls back to a blank
  conversation when a resume fails, because the alternative there is a session that cannot
  receive its event. Here the alternative is a session that keeps running on a stale token,
  which is strictly better than twenty lost conversations — so a session that cannot resume
  is skipped and left alone (R1.5).

### Judgement calls worth a reviewer's attention

- **`unverified` does not fail the run.** `-e` is a deterministic mechanism; verification
  is the check on it. A macOS or container host that will not report a process's
  environment would otherwise make `restart` permanently exit non-zero. It is reported
  loudly in its own note, and `status` likewise refuses to claim drift it has not observed.
- **A multi-pane session is `stale` when any pane is.** They belong to one work item, and
  one pane on a retired credential is the whole session broken. A pane that merely could
  not be read does not outvote a sibling that answered and matched.
- **the-loop's own three variables are appended last** to the `-e` list, so an env file
  declaring `THE_LOOP_INSTANCE` cannot move the runner's identity. Asserted directly.

### An observation this work surfaced, not caused

`make check` and CI disagree. The Makefile's `test` target runs pytest from the
repository root; the pre-commit hook CI runs does `cd cli && … pytest`. Four
`test_instance.py` argv assertions pass under the second and fail under the first,
because from the root they discover this repository's own `.the-loop/cli-config.yaml`.
Reproduced on `main` with this branch stashed. Recorded in
[`evidence/verification.md`](verification.md) rather than fixed here — the Makefile
comment claims parity it does not have, which is a defect worth its own ticket and not
worth folding into a credential-handling diff.

## Round 2 — critic

Not run: this repository's critic harness is not configured in this environment. The
reviewer briefing on the PR carries the same material a critic round would have produced —
where to focus, the mechanism diagram, and the low-level decisions above.
