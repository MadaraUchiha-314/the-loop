---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#410"
---

# Security review: roll running sessions onto a refreshed environment (issue-410)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), against the diff.
- **Outcome:** pass, with two accepted, documented trade-offs (below) and one
  **escalation**: tier 4 requires a named human security sign-off.
- **Findings:** none unresolved.

### Accepted trade-off 1 — the values reach tmux through an argv

`new-session -e NAME=VALUE` and `respawn-pane -e NAME=VALUE` put the value in the argv of
a short-lived `tmux` client, where another user on the same host can read it from `ps` for
as long as that call runs.

Accepted, narrowly, and stated in both the requirements and the operator documentation:

- the status quo is **worse, not better**: the same values already sit permanently in the
  tmux server's environment, readable by anyone who can reach its socket
  (`tmux show-environment -g`), and in a file on the same disk. The marginal exposure is a
  fraction of a second against an indefinite one;
- nothing is ever written to the tmux **global** environment, so the-loop never widens the
  set of sessions carrying its secrets — only its own `loop-*` panes receive them;
- the one exposure-free alternative (having the pane source the env file itself) would
  mean **executing** operator content through a shell. `envfile`'s grammar is deliberately
  not shell — no interpolation, no multi-line — and its module contract is that nothing
  evaluates, expands or executes any part of the file. Refused;
- the exposure is to a local user on the host that already runs the sessions, and the
  operator invoking `sessions restart` is that user.

### Accepted trade-off 2 — the file wins for the names it declares

At process start `envfile.load` leaves alone any name the environment already carries. The
spawn and restart paths cannot honour that rule: the value this process carries may be
exactly the retired one, and an operator's deliberate export is indistinguishable from a
stale load. For the names an env file declares, the file is therefore the source of truth
on those two paths.

This is the only rule under which a rotation can take effect at all, and it is stated as a
rule in `requirements.md` § Security and in `docs/config/cli/index.md` rather than left
implicit. It can only ever *narrow* drift: a name the file does not declare is untouched.

### Checklist

- *Secrets in output:* **no value reaches any sink.** A variable is identified by name and
  by a truncated SHA-256 fingerprint (`envstate.fingerprint`). Asserted mechanically over
  the messages, the structured rows, the fingerprint map, the rendered `status` line and
  the JSONL event log, on all four outcome paths (`fresh`/`stale`/`unverified`/`failed`) —
  `TestSecretsAreNeverPrinted`. `envstate` is the only module that handles a value and was
  read in full at review; it has no `logger` call carrying one, and a malformed env-file
  line is reported by **number**, never by text (a malformed line may itself be a secret).
- *Reading another process's environment:* only pids **tmux reports for the-loop's own
  `loop-*` panes** are ever read — the same provenance rule that governs which pids
  the-loop will signal. `process_environ` never raises: an exited pid, `EACCES`, or a
  platform with neither `/proc` nor a usable `ps` is `None`, reported as *unverified*
  rather than guessed at.
- *Command injection:* the only caller data interpolated into a tmux argv is the recorded
  harness conversation id, validated against `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$` before
  use (the dispatcher's existing rule), and the tmux target, validated against
  `_LOOP_TARGET_RE` — a respawn kills a running process, so a hand-edited `tmuxTarget`
  must not be able to aim it at another session. Both are covered by tests. Every argv is
  a list passed to `subprocess.run` without a shell.
- *Privilege:* none added. The command relaunches processes this machine already runs, as
  the user who already runs them, from a file that user already reads.
- *Trust boundary:* unchanged. Nothing here reads event text, channel input or any other
  untrusted source; the inputs are the operator's own config, their own env file and
  tmux's report of their own panes.
- *Denial of service / blast radius:* `--all` is explicit and never inferred (a bare
  `restart` is a usage error). A relaunch is scoped to sessions in this machine's registry
  and never starts a stopped one. `restart` is not reachable over HTTP or MCP — it runs
  in-process, the `reset` precedent.
- *Fail-closed:* every new failure mode reports rather than assumes. A session that cannot
  be verified is `unverified`, not "fine"; a session still on a retired value exits
  non-zero; `status` claims no drift it has not observed.
- *New dependencies:* none. `hashlib` and `subprocess` are stdlib.

- **Risk tier:** **4** — raised by the sensitive-path rule: the change reads the
  credential file and hands its values to spawned processes
  (`**/*secret*` / `**/*credential*` in substance). Tier 4 requires a **named human
  security sign-off**, distinct from the PR approval — see below.

## Human security sign-off (tier 4)

**Required, not yet obtained.** Requested on the pull request. The two accepted trade-offs
above are the substance of what is being signed off:

1. handing credential values to tmux through an argv, and
2. the env file winning over an already-set environment variable, for the names it
   declares, on the spawn and restart paths.

Until a named human signs off, this work item does not complete.
