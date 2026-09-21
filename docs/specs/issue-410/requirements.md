---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#410"
status: in-review            # draft | in-review | approved — tier 4: the PR approval plus a named security sign-off
approvedBy: []
collaborators: [engineer]
overrides: {}
riskTier: 4                  # credential-bearing: reads the env file and hands its values to spawned processes
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: roll running sessions onto a refreshed environment

> Phase 1 of 4 (requirements → design → testing plan → tasks). Source:
> [issue-410](https://github.com/MadaraUchiha-314/the-loop/issues/410).

## Introduction

A harness session's environment is whatever tmux handed its pane when the pane was
forked. Nothing re-reads it afterwards, and nothing notices when it has gone stale — so
a credential rotation splits the deployment in two: the service, restarted, holds the
new token; every session already running holds the old one, and keeps holding it for as
long as it runs.

The reporter lived the full failure. They rotated the Slack bot token, pointed the
channel at a different conversation and restarted the service. The service picked both
up. The ~20 sessions did not, so every post those sessions attempted reached a
conversation their old identity was not a member of:

```text
slack: post failed: ... {'ok': False, 'error': 'channel_not_found'}
```

**144 consecutive agent questions failed over three days.** Fingerprinting the token
each process actually held is what finally named the cause:

| what | fingerprint | which bot |
|---|---|---|
| the env file | `c5c1dead` | A — the new one |
| the service process | `c5c1dead` | A — restarted after the rotation |
| the tmux server's global environment | `89100053` | B — the old one |
| all 20 sessions | `89100053` | B — the old one |

Two facts make this the-loop's problem rather than the operator's.

The first is that **config files do not behave this way**. `cli-config.yaml` is re-read
per call; issue comments are re-read per poll. Only the environment is frozen, so the
operator's reasonable model — "restart the service and it picks up the new config" —
holds everywhere except the one place that carries the secrets.

The second is that **the tmux server is the freeze point, not the session**. The table
above shows the *server's* global environment still on bot B. A tmux pane's environment
is built from that global environment layered with the session's own, and the-loop's
spawn passes only `THE_LOOP_INSTANCE`, `THE_LOOP_WORK_ITEM` and `THE_LOOP_CLI_CONFIG`
through `-e`. Every credential therefore arrives by inheritance from a server process
that outlives every restart the operator knows to perform. A session spawned *an hour
after* the rotation would have been born on bot B too.

The reporter implemented the recovery as an external script and it works — 21 sessions
restarted in place, all verified, conversations intact — but it reaches into `/proc` and
the runner's pane naming to do it. That is the-loop's own furniture, and the recovery
belongs beside it.

### Scope

In scope: refreshing the environment of sessions the-loop runs, detecting when it has
gone stale, and not spawning fresh sessions into the same staleness.

Out of scope, and filed separately by the reporter: the harness **launch flags** are
frozen by the same mechanism (a session released from the human-start gate was spawned
without a configured flag). This work item restores the *environment*; it does not
re-derive the argv from current config.

## Requirements

### Requirement 1 — an operator can roll running sessions onto the current environment

**User story:** As an operator who has just rotated a credential, I want one command
that relaunches the running sessions on the new value, so that recovery is a step I take
deliberately rather than a breakage I discover three days later.

#### Acceptance criteria

1. WHEN the operator runs `the-loop sessions restart --all` THEN the system SHALL
   re-read the configured `env.file` **at that moment** and relaunch every live session
   it manages with the values that file now declares.
2. WHEN the operator runs `the-loop sessions restart <work-item>` THEN the system SHALL
   do the same for that work item's session alone.
3. WHEN neither `--all` nor a work item is given THEN the system SHALL refuse and say
   which of the two it needs, rather than guessing at a fleet-wide relaunch.
4. WHEN a session is relaunched THEN the system SHALL resume the **same harness
   conversation** in the **same working directory**, so that nothing the agent knew
   about the work item is lost.
5. WHEN a session's recorded harness conversation cannot be resumed THEN the system
   SHALL leave that session alone, report it, and SHALL NOT replace it with a fresh
   conversation — losing 20 conversations is a worse outcome than a stale token.
6. WHEN a registered session is not running THEN the system SHALL report it as skipped
   and SHALL NOT start it: `restart` refreshes what is running, and `start` is the verb
   that brings a session up.
7. WHEN no `env.file` is configured THEN the system SHALL refuse with that reason,
   because there is no declared environment to refresh and a respawn for nothing still
   costs the operator every pane.

### Requirement 2 — the relaunch is verified, and says so

**User story:** As an operator, I want the command to prove the sessions are actually on
the new value, so that I never again mistake a healthy-looking service for a healthy
fleet.

#### Acceptance criteria

1. WHEN a session has been relaunched THEN the system SHALL read the new process's own
   environment and compare it, name by name, with what the env file declares.
2. WHEN a relaunched session's environment does not match THEN the system SHALL report
   that session by ref, name the variables that differ, and exit non-zero.
3. WHEN a relaunched session's environment cannot be read on this platform THEN the
   system SHALL report it as unverified — distinctly from both a match and a mismatch —
   and SHALL NOT exit non-zero on that ground alone.
4. WHEN the operator passes `--dry-run` THEN the system SHALL report what it would
   relaunch, and why, without touching a single pane.

### Requirement 3 — a stale environment is visible before it bites

**User story:** As an operator, I want `the-loop status` to tell me the fleet has
drifted, so that the answer arrives in the minute after the rotation rather than on the
third day of silence.

#### Acceptance criteria

1. WHEN `the-loop status` runs and one or more running sessions hold values that differ
   from the current `env.file` THEN the report SHALL carry a line naming how many
   sessions are running with a stale environment and the command that fixes it.
2. WHEN every running session matches THEN `status` SHALL say nothing about the
   environment — a clean deployment gains no line.
3. WHEN `status` is asked for JSON THEN the same facts SHALL be present as structured
   data, per session.
4. WHEN the sessions' environments cannot be read THEN `status` SHALL NOT report drift
   it has not observed, and SHALL NOT fail.
5. A stale environment SHALL NOT change `status`'s exit code: it is an observation about
   sessions, and `status`'s contract is "every **enabled service** is running".

### Requirement 4 — a session spawned after a rotation is not born stale

**User story:** As an operator, I want the rotation to be finished when I have rolled the
fleet, so that the next session the daemon spawns does not quietly reintroduce the value
I just retired.

#### Acceptance criteria

1. WHEN the daemon spawns a session and an `env.file` is configured THEN the harness
   SHALL receive the values that file declares **as read at spawn time**, rather than
   inheriting the tmux server's environment for those names.
2. WHEN no `env.file` is configured THEN the spawn SHALL be exactly what it is today —
   no new behaviour reaches a deployment that declares no env file.
3. WHEN the tmux in use is too old to accept per-session environment
   (`new-session -e`, tmux 3.2) THEN the spawn SHALL proceed as it does today, with the
   existing single warning and no failure.

### Requirement 5 — secrets stay unprinted

**User story:** As the operator whose credentials these are, I want the recovery path to
be as quiet about values as the rest of the-loop is, so that fixing a leak does not
publish one.

#### Acceptance criteria

1. The system SHALL NOT write an environment **value** to any output stream, log record
   or event — not at any level, not on any failure path.
2. WHEN a value must be identified in output THEN the system SHALL identify it by a
   **fingerprint** (a truncated SHA-256 of the value), which is what makes "these two
   processes hold different tokens" sayable without saying either.
3. The system SHALL name a differing variable by **name** and fingerprint only.

## Security considerations

**The values reach a child process through an argv.** Handing tmux `-e NAME=VALUE` puts
the value in the argv of a short-lived `tmux` client, where another user on the same host
can read it from `ps` for as long as that call runs. This is accepted, narrowly:

- the alternative is the status quo, in which the same values sit *permanently* in the
  tmux server's environment (readable via `tmux show-environment -g` by anyone who can
  reach the socket) and in a file on the same disk, so the marginal exposure is a
  fraction of a second against an indefinite one;
- nothing is written to the tmux **global** environment, so the-loop never widens the set
  of sessions that carry its secrets — only its own panes receive them;
- the-loop's dotenv parser is deliberately not a shell, so the one exposure-free
  alternative (having the pane source the file itself) would mean executing operator
  content and is refused.

This is stated in the operator documentation rather than left to be discovered.

**Reading another process's environment.** Verification reads `/proc/<pid>/environ` (and
on platforms without it, `ps eww`). Only pids tmux reports for the-loop's own
`loop-*` panes are ever read — the same provenance rule that governs which pids the-loop
will signal — and the read is failure-tolerant: a pid that has exited, a permission
denial or a platform without either mechanism yields "unverified", never an exception and
never a guess.

**The file wins for the names it declares.** At process start `envfile.load` leaves alone
any name the environment already carries. A relaunch cannot honour that rule: the value
this process carries may be exactly the retired one, and there is no way to tell an
operator's deliberate export from a stale load. For the names an env file declares, the
**file** is therefore the source of truth on the spawn and restart paths. This is the
only rule under which a rotation can take effect, and it is documented as a rule rather
than left implicit.

**No new privilege.** The command relaunches processes this machine already runs, as the
user who already runs them, from a file that user already reads. It grants nothing and
reaches nothing it did not already own.
