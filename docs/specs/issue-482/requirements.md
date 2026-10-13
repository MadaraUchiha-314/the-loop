---
type: requirements
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#482"
status: in-review            # draft | in-review | approved — the gate locks it, never the session
approvedBy: []
collaborators: [engineer, security]
overrides: {}
riskTier: 4                  # credential handling: what a spawned session holds, and what `ps` shows
---

<!-- Authored per the the-loop:writing skill. -->

# Requirements: spawned sessions never receive a secret

> Phase 1 of 4 (requirements → design → testing plan → tasks). Tier 4
> (`human-approves-pr`, plus a named human security sign-off): the change decides which
> credentials reach an agent session and what any local process can read from `ps`.
> One work item covers two tickets, at the owner's request: [#482][i482] states the
> principle and [#485][i485] reports the longest-lived symptom.

## Introduction

**What is broken.** Every variable in `env.file` reaches every spawned tmux pane as
`tmux new-session -e NAME=value`. So the GitHub token is in a process's argv, where `ps`
shows it to every local process and, on most hosts, to every other user.

- [#482][i482]: on a daemon-hosted box, `ps aux` showed `-e THE_LOOP_GH_TOKEN=gho_…` in a
  pane's command line, next to every other credential in the file (`JIRA_API_TOKEN`,
  the Jira webhook secret).
- [#485][i485]: when no tmux server is running, that `tmux new-session` call **starts the
  server**, and the server keeps the command line it was started with as its process
  name for its whole life. The reporter's `GH_TOKEN` was readable in `ps` eight days
  after the spawn. The `_env_flags` docstring and the
  [issue-410 security note](../issue-410/requirements.md#security-considerations) both
  assume the exposure ends when the short-lived client returns. It does not.

The root cause is that `env.file` does two jobs: it holds the daemon's credentials, and
it is every session's environment. Nothing separates the two. A second path leaks the
same values with no argv involved: the daemon loads `env.file` into its own environment
at start, and a tmux server the daemon starts inherits that environment, so every pane
inherits the token from the server even when no `-e` names it.

**The principle** ([#482][i482]): the-loop never sends a secret to an agent session. A
session talks to the-loop through the-loop's CLI; the service holds the credentials and
makes the GitHub and Jira calls.

**What this changes.**

- A spawned pane receives the-loop's own three identifiers and nothing from `env.file`,
  unless the operator lists a non-secret name in a new allowlist,
  `env.sessionPassthrough`. A credential name is refused there.
- A spawned pane has every `env.file` name and every configured credential name removed
  from its environment, whatever the tmux server holds.
- The session-side verbs (`ask`, `comment`, `ticket …`, `pr …`) in a daemon-spawned
  session go through the running service. When none answers, they fail with a message
  that says so, instead of running in-process on a token the session no longer has.

**Out of scope.**

- The workspace-trust pre-seed that does not stick ([#482][i482] § Related). The issue
  marks it as unverified and fine to track separately.
- An explicit opt-in for the in-process fallback in a cloud checkout with no daemon.
  [#482][i482] R3 says that is decided separately. A session the daemon did not spawn
  keeps today's behaviour.

## Requirements

### Requirement 1: a pane receives only the-loop's identifiers

**User story:** As an operator, I want a spawned agent session to hold none of my
credentials, so that a compromised or careless agent cannot use or leak them.

#### Acceptance criteria (EARS)

1.1 WHEN the-loop spawns or respawns a session THEN the `-e` flags it passes tmux SHALL
name only `THE_LOOP_INSTANCE`, `THE_LOOP_WORK_ITEM`, `THE_LOOP_CLI_CONFIG` and the names
`env.sessionPassthrough` admits.

1.2 WHEN `env.sessionPassthrough` is unset or empty THEN no name `env.file` declares SHALL
be passed to the pane.

1.3 WHEN the-loop spawns or respawns a session THEN the harness process SHALL start with
every name `env.file` declares and every credential name the config resolves (R4.2)
removed from its environment, except names `env.sessionPassthrough` admits.

1.4 The removal in 1.3 SHALL hold when the tmux server was started by a process that
held those names, including the daemon itself.

### Requirement 2: no credential in any argv

**User story:** As an operator, I want no credential value in any process's command
line, so that `ps` on my host shows none.

#### Acceptance criteria (EARS)

2.1 No argv the-loop builds for tmux SHALL carry the value of a name `env.file` declares
or of a credential name (R4.2), unless that name is admitted by `env.sessionPassthrough`.

2.2 WHEN a spawn's `tmux new-session` starts the tmux server THEN that server's argv SHALL
carry no credential value, so nothing secret stays in `ps` for the server's lifetime
([#485][i485]).

2.3 WHEN a spawn runs tmux THEN the tmux process SHALL be started with the names in 1.3
removed from its own environment, so a server it starts does not inherit them.

### Requirement 3: session-side verbs go through the service

**User story:** As an operator running a daemon, I want an agent's `ask`, `comment`,
`ticket` and `pr` calls to be made by the service, so the session never needs a token.

#### Acceptance criteria (EARS)

3.1 WHEN `the-loop ask` runs AND a service answers `/health` THEN the question SHALL be
posted by the service, with the same marker, wait event and channel fan-out as today.

3.2 WHEN a session-side verb (`ask`, `comment`, `ticket …`, `pr …`)
runs in a session the daemon spawned AND no service answers `/health` THEN it SHALL
exit non-zero with a message that names the missing service and how to start it, and
SHALL NOT run in-process.

3.3 A session SHALL count as daemon-spawned WHEN any of `THE_LOOP_INSTANCE`,
`THE_LOOP_WORK_ITEM` or `THE_LOOP_CLI_CONFIG` is set in its environment.

3.4 WHEN a session-side verb runs outside a daemon-spawned session AND no service answers
THEN it SHALL behave as before this change (the in-process fallback with its stderr
note).

### Requirement 4: an explicit, credential-proof allowlist

**User story:** As an operator who needs a non-secret variable in my agents' panes (a
proxy, a locale), I want to name it explicitly, and I want the-loop to refuse to forward
a credential even if I list one by mistake.

#### Acceptance criteria (EARS)

4.1 The CLI config SHALL accept `env.sessionPassthrough`: a list of environment variable
names, default empty.

4.2 The credential names SHALL be every string under a config key whose name ends in
`TokenEnv`, `tokenEnv`, `SecretEnv` or `secretEnv` (a string or a list of strings), at
any depth, plus the built-in defaults the-loop reads a credential from when the config
names none (`GH_TOKEN`, `GITHUB_TOKEN`, and the schema defaults of the Slack and webhook
keys).

4.3 WHEN `env.sessionPassthrough` lists a credential name THEN the-loop SHALL NOT forward
it, and SHALL log a warning naming the variable (never its value).

4.4 WHEN a passthrough name is declared in `env.file` THEN its value SHALL come from the
file, re-read per spawn (issue-410's rule); otherwise from the spawning process's
environment; a name in neither SHALL be skipped.

### Requirement 5: the drift check and restart follow the new boundary

5.1 `the-loop status`'s session-environment line and `the-loop sessions restart` SHALL
compare a session against what it is supposed to hold: a passthrough name SHALL be
reported when its value differs from the current one, and a removed name (R1.3) SHALL be
reported when the session holds it at all. A session that lacks an `env.file` credential
SHALL NOT be reported stale for lacking it.

5.2 WHEN `sessions restart` runs AND `env.file` is named or `env.sessionPassthrough` is
set THEN it SHALL relaunch the selected sessions on the new boundary, even when nothing is
forwarded: a relaunch that strips a token is the upgrade path of R6. WHEN neither is set
THEN it SHALL refuse, as today.

### Requirement 6: upgrade notes

6.1 The changelog and the operator docs SHALL say that panes spawned by an earlier
version keep the token in their argv, and in the tmux server's when a spawn started it,
until they are restarted; and SHALL say how to clear both (restart the sessions, and
`tmux kill-server` once no session needs keeping).

## Security considerations

**Untrusted actors.** Any local process that can list processes (same user or, on most
hosts, any user); the agent running inside a session, which can be steered by text it
reads from issues, PRs and the web; diagnostic tools and crash reports that capture
process lists.

**Trust boundaries.**

- Daemon/service ↔ session. The service holds credentials; the session holds none and
  reaches GitHub and Jira only through the service's API on the loopback.
- the-loop ↔ tmux. Anything placed in a tmux argv is public to the host; anything in the
  tmux server's environment is inherited by every pane.

**Abuse cases.**

- A1. A local user reads a token from `ps` → R2 (no credential value in any argv).
- A2. A tmux server started by a spawn keeps the token in its name for days → R2.2.
- A3. A pane inherits the token from the tmux server's global environment though no `-e`
  names it → R1.3, R1.4, R2.3.
- A4. An operator lists `GH_TOKEN` in the allowlist by mistake → R4.3.
- A5. A steered agent, finding no service, falls back to a token it should not have →
  R3.2 (a daemon-spawned session never falls back; it also no longer holds the token).

**Fail-closed.** A passthrough name that is a credential is dropped, not forwarded. A
daemon-spawned verb with no service fails rather than running in-process. Reading the
env file failing still yields a pane with the credential names stripped (the configured
credential names do not depend on the file).

**What does not change.** `git` push and clone in a session still use the operator's git
credential (a git helper or SSH key), which is not an API token and is not in `env.file`.
The service's API is unauthenticated on the loopback, as today (decision-059).

[i482]: https://github.com/MadaraUchiha-314/the-loop/issues/482
[i485]: https://github.com/MadaraUchiha-314/the-loop/issues/485
