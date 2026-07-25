---
type: requirements
phase: requirements-definition
workItem: "issue-90"
status: draft
approvedBy: []
collaborators: [product-manager, engineer, approver]
overrides: {}
---

# Requirements: pre-trust the workspace before spawning a harness session

> Phase 1 of 3 (requirements → design → tasks). Following the Kiro spec approach
> (https://kiro.dev/docs/specs/). Tier 4 (`human-approves-pr` **+ a named human
> security sign-off**, `security.review.humanSignOffMinTier: 4`) — this work item
> writes to the operator's own harness configuration and can pre-accept a safety
> disclaimer on their behalf, so the risk tier is raised a notch above the usual
> CLI change.

## Introduction

the-loop's whole point is that a webhook/poll event turns into an agent session
that just *runs*. [Issue #90](https://github.com/MadaraUchiha-314/the-loop/issues/90)
reports the one thing that reliably stops that from happening: the spawned
Claude Code session opens on an **interactive dialog** instead of on the work.

Two separate dialogs are involved, and neither is a permission *rule* — which is
why `--dangerously-skip-permissions` does not silence them:

1. **The workspace-trust dialog** ("Do you trust the files in this folder?").
   Claude Code shows it for any directory whose canonical path (or an ancestor)
   is not marked trusted in its user-level config file. Every checkout the
   `routing.workspace` machinery creates (issue-76) is a **brand-new directory**
   — `<root>/.worktrees/<host>/<owner>/<repo>/<slug>` or
   `<root>/.work-items/<slug>/…` — so *every single spawn* hits it.
2. **The bypass-permissions disclaimer** — the one-time "you are about to run in
   Bypass Permissions mode" acceptance that gates
   `--dangerously-skip-permissions` itself. Until it is accepted, Claude Code
   either asks for it or silently downgrades the permission mode back to
   `default` ("Permission mode downgraded to default — bypass requires accepting
   the disclaimer interactively first").

The failure is silent-ish and total. With `runner: tmux` the session sits on the
dialog forever: the-loop happily records `session.spawned`, pastes the event
prompt into a TUI that is showing a modal, and the work item never moves. With
`runner: process` the headless run fails or degrades. Either way the operator
has to attach to a terminal and press a key — the exact human-in-the-loop step
the daemon exists to remove.

The fix the issue asks for: **before the-loop spawns a session, it puts the
configuration the harness needs where the harness will read it.**

## Requirements

### Requirement 1 — a spawned session's working directory is already trusted

**User story:** As an operator running the daemon unattended, I want the
directory a session is spawned into to be pre-trusted, so that the agent starts
working instead of waiting on a trust dialog nobody is there to answer.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher is about to spawn a session for a work item THEN the
   system SHALL, before starting the harness process, mark that session's
   working directory as trusted in the harness's own user-level configuration.
2. WHEN the harness is Claude Code THEN "marked as trusted" SHALL mean
   `projects[<path>].hasTrustDialogAccepted: true` in Claude Code's user config
   file, and the same entry SHALL also carry
   `hasCompletedProjectOnboarding: true` so the first-run onboarding screen does
   not replace the dialog it removes.
3. WHEN the working directory's real path differs from its resolved path (a
   symlinked workspace root) THEN the system SHALL record **both** keys, so
   trust holds however the harness canonicalises the path.
4. WHEN a tmux-mode session is **respawned** after being found dead (issue-80)
   THEN the same preparation SHALL run for the respawned session's working
   directory — a respawn must not be the one path that stalls on a dialog.
5. WHEN the working directory is already marked trusted THEN the system SHALL
   make **no write at all**, so the common case cannot race with the harness's
   own writes to the same file.

### Requirement 2 — bypass-permissions mode is usable without an interactive acceptance

**User story:** As an operator who configured
`harnessArgs.claude: [--dangerously-skip-permissions]`, I want that flag to
actually take effect in a spawned session, so that the session does not stop on
per-tool permission prompts or get silently downgraded to `default` mode.

#### Acceptance criteria (EARS)

1. WHEN the configured harness args for the harness being spawned request
   bypass-permissions mode (`--dangerously-skip-permissions`, or
   `--permission-mode bypassPermissions`) THEN the system SHALL record the
   disclaimer acceptance in the harness's user configuration before spawning.
2. WHEN the harness is Claude Code THEN "recorded acceptance" SHALL mean
   `skipDangerousModePermissionPrompt: true` in the user settings file, and — for
   older CLI builds that still read it — `bypassPermissionsModeAccepted: true`
   in the user config file.
3. WHEN the configured harness args do **not** request bypass-permissions mode
   THEN the system SHALL NOT record any such acceptance: the-loop never widens
   permissions the operator did not ask for (the standing `harnessArgs` rule —
   "the dispatcher never widens permissions itself").
4. WHEN `routing.harnessTrust.acceptBypassPermissions` is `never` THEN the
   acceptance SHALL NOT be recorded even if the harness args request bypass
   mode; WHEN it is `always` THEN it SHALL be recorded regardless of the
   harness args; the default `auto` SHALL behave as criteria 1 and 3 describe.

### Requirement 3 — the operator stays in control, and their config survives

**User story:** As an operator, I want the-loop's writes to my harness config to
be predictable, reversible and opt-out-able, so that a daemon convenience never
costs me my own settings.

#### Acceptance criteria (EARS)

1. WHEN `routing.harnessTrust.enabled` is `false` THEN the system SHALL perform
   no preparation at all and spawn exactly as it does today.
2. WHEN the system writes a harness config file THEN it SHALL preserve every
   key it did not set (read → merge → write), write via a temporary file plus an
   atomic replace, and create new files with owner-only (`0600`) permissions.
3. WHEN a config file exists but cannot be read or parsed as JSON THEN the
   system SHALL leave it untouched and report the failure — a corrupt or
   unexpected file is never overwritten.
4. WHEN preparation fails for any reason THEN the spawn SHALL still proceed, and
   the system SHALL log a warning naming the file and the reason — a config-write
   hiccup must not wedge the work item behind a permanently failing dispatch.
5. WHEN preparation is applied or fails THEN the system SHALL emit a
   `workspace.trusted` / `workspace.trust_failed` event-log record, so
   `the-loop events` shows exactly which directories the-loop trusted and when.
6. WHEN the harness has no such configuration concept (cursor-agent today) THEN
   preparation SHALL be a silent no-op, not an error.
7. WHEN the harness's config location is redirected via `CLAUDE_CONFIG_DIR`
   THEN the system SHALL honour it, so the daemon writes where the harness it
   spawns will actually read.

## Security considerations (threat-model-lite)

**Untrusted actors.** Anyone who can open an issue/PR/comment on a watched repo
influences *which repo* is checked out and *what slug* names the checkout.
Nothing about this feature is driven by payload text directly.

**Trust boundaries.**

- *Payload → filesystem path.* The directory this feature trusts is **never**
  taken from a payload. It is the string the dispatcher already resolved
  (`Workspace.prepare()`'s return value, itself built from the existing
  `_safe_component` path-traversal guard, or the static `spawnWorkdir`). This
  work item adds no new payload-derived path.
- *the-loop → the operator's own config.* This is the new boundary and the real
  risk: the daemon writes to `~/.claude.json` and `~/.claude/settings.json`.
  Bounded by (a) writing only the specific keys named in R1/R2, (b) merge-not-
  replace with atomic rename, (c) no write when the value is already correct,
  (d) refusing to touch a file that does not parse.
- *Trust scope.* Marking a directory trusted is what makes Claude Code honour
  `.claude/settings.json`, hooks and skills **from inside that checkout**. Since
  the checkout is a clone of the repo the event came from, trusting it means:
  a contributor who can land a `.claude/` hook in that repo gets it executed by
  the spawned agent. That is *already* the operating assumption of auto-execute
  (the agent runs the repo's code, tests and scripts), and the-loop's actual
  gate against hostile repos is `routing.authorizedUsers` + the repos the
  operator points the daemon at — not the trust dialog, which no unattended
  daemon can answer anyway. Stated here rather than implied, per the loop's
  security rule.

**Abuse cases.**

- *Trust creep.* A bug that wrote an **ancestor** key (e.g. the workspace root,
  or `/`) would trust far more than intended. Mitigated by writing only the
  exact spawn directory (and its realpath), never a parent — and asserted by a
  test.
- *Config clobbering.* A concurrent write from a live Claude Code process could
  be lost by a naive read-modify-write. Mitigated by the no-write-when-unchanged
  rule (R1.5) — the window shrinks to the first spawn into a given directory —
  plus an in-process lock and atomic replace. Residual risk is documented, not
  hidden.
- *Silent permission widening.* Accepting the bypass disclaimer when the
  operator never asked for bypass mode would be the-loop widening permissions on
  its own. Forbidden by R2.3, gated by `acceptBypassPermissions`, and asserted
  by a test.
- *Blast-radius asymmetry between the two writes.* Trust is **per directory**;
  the bypass acceptance is a **user-global** setting (the only form the harness
  offers), so it removes the bypass-mode confirmation from the operator's
  **interactive** sessions too, not only the-loop's spawned ones. Not
  remotely exploitable, but a scope the operator must consciously accept — so
  it is stated outright in the schema, `cli/README.md`, decision-036 and the
  reviewer briefing rather than left to be discovered. `never` plus a narrower
  `--permission-mode acceptEdits` in `harnessArgs` avoids it entirely.
- *Trusting a checkout that contains hostile `.claude/` hooks.* Trust is what
  makes the harness load a repo's own settings/hooks/skills. Reachable only
  from content already on the checked-out tree, which is the **default branch**
  (a fork PR's head ref is not on origin, so `ensure_worktree` falls back to a
  detached default-branch worktree rather than checking it out) — i.e. it takes
  merge rights, on a repo the operator points the daemon at, past
  `routing.authorizedUsers`. Not a new path so much as the same one
  auto-execute already walks by running the repo's code and tests; recorded
  under trust boundaries above rather than treated as newly opened.

**Fail-closed / fail-open.** Deliberately mixed, and each direction is
justified: the *bypass acceptance* fails **closed** (not requested ⇒ not
written). The *preparation step as a whole* fails **open** (a write error still
lets the spawn run) because the alternative — failing the dispatch — retries
forever and buries the work item, while the open failure is loud in both the log
and the event log, and degrades to exactly today's behaviour.

## Out of scope

- Any new payload-derived path or checkout layout (that is issue-76's).
- Teaching cursor-agent an equivalent (it has no such config surface today;
  R3.6 makes it an explicit no-op with a seam to fill in later).
- A general "write arbitrary harness settings" facility. Only the keys named in
  R1/R2 are written (minimalism: YAGNI).
