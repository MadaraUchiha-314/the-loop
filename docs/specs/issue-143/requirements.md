---
type: requirements
phase: requirements-definition
workItem: issue-143
status: approved
approvedBy: []
collaborators: [engineer]
overrides: {}
---

# Requirements: the CLI installs the-loop's own plugin before a spawned session starts

> Phase 1 of 3 (requirements → design → tasks). Human approval for this change happens at
> the PR (`autonomy.tiers."4": human-approves-pr` — the change touches
> `.the-loop/cli-config.schema.json`, an `autonomy.sensitivePaths` match).

## Introduction

[Issue #143](https://github.com/MadaraUchiha-314/the-loop/issues/143): *"the-loop's CLI
should add itself as enabled plugins before it starts the work on a repo"*, with the
settings shape spelled out:

```diff
+    "the-loop@the-loop": true
+    "the-loop": {
+      "source": {
+        "source": "github",
+        "repo": "MadaraUchiha-314/the-loop"
+      }
+    }
```

The daemon (`the-loop gh-webhook` / `the-loop poll`) clones a repository per work item and
spawns a harness session in that fresh checkout. Everything the session then knows about
the loop — the `the-loop` skill, the `/the-loop:*` commands, the SessionStart hook that
states the operating rules — arrives through **the plugin**. Nothing in the spawn path
installs it: the-loop pre-seeds workspace trust and the bypass-permissions disclaimer
(issue-90, issue-136) so the session *starts*, then hands it a work-on prompt for a loop
whose machinery is not loaded. On a machine where the operator never ran
`/plugin marketplace add` by hand, the spawned session works the ticket as a plain agent —
no phase labels, no spec chain, no gates. That is the same class of gap `CLAUDE.md`
records for cloud/web sessions in this repository, one layer down.

Claude Code reads two keys from its settings file for this: `extraKnownMarketplaces`
(where a marketplace lives) and `enabledPlugins` (which `<plugin>@<marketplace>` is on).
Writing them is exactly what `/plugin marketplace add` + `/plugin install` do, and the
CLI already owns a narrow, atomic, non-destructive writer for that same file
(`the_loop.trust`, which writes `skipDangerousModePermissionPrompt` there).

## Requirements

### Requirement 1 — a spawned session has the-loop's plugin enabled

**User story:** As an operator running the-loop's daemon, I want every session it spawns to
have the-loop plugin already enabled, so that the session actually runs the loop instead of
working the ticket as a plain agent.

#### Acceptance criteria (EARS)

1. WHEN the dispatcher prepares the environment for a Claude Code spawn or respawn THEN
   the system SHALL ensure the harness's user settings file carries
   `enabledPlugins["the-loop@the-loop"] = true` and an `extraKnownMarketplaces["the-loop"]`
   entry pointing at the configured marketplace repository, before the harness process
   starts.
2. WHEN the settings file already carries both entries THEN the system SHALL write nothing
   at all.
3. WHEN the harness is one with no plugin-configuration surface (`cursor-agent`) THEN the
   system SHALL do nothing and report no error.

### Requirement 2 — the operator's own configuration is never overwritten

**User story:** As an operator who already installed the-loop (from a fork, a local
checkout, or a marketplace of my own), I want the daemon to leave my configuration alone,
so that its convenience write can never silently repoint or re-enable something I chose.

#### Acceptance criteria (EARS)

1. IF `extraKnownMarketplaces["the-loop"]` already exists THEN the system SHALL leave its
   value exactly as-is, whatever it points at.
2. IF `enabledPlugins["the-loop@the-loop"]` already exists — including when it is `false` —
   THEN the system SHALL leave that value as-is.
3. IF either key's container is present but not a JSON object THEN the system SHALL leave
   the file untouched and report the problem, exactly as an unparseable file is handled
   today.
4. WHEN the configured marketplace repository is not of the form `owner/repo` THEN the
   system SHALL write nothing and report the problem.
5. IF the configured marketplace repository is empty THEN the system SHALL enable the
   plugin without adding any marketplace entry, leaving marketplace registration to the
   operator.

### Requirement 3 — it is configurable, auditable and off-switchable

**User story:** As an operator, I want this write to be visible and optional, so that a
machine-global change made on my behalf is one I can inspect, redirect at my fork, or
decline.

#### Acceptance criteria (EARS)

1. WHEN `routing.harnessPlugins.enabled` is `false` THEN the system SHALL make no
   plugin-related write.
2. WHEN `routing.harnessPlugins.marketplaceRepo` names a repository THEN the system SHALL
   register the marketplace from that repository instead of the-loop's own.
3. WHEN a plugin entry is written THEN the system SHALL name the file it wrote in the
   `workspace.trusted` event's `applied` list, so `the-loop events` shows it.
4. IF the write fails THEN the system SHALL log a warning, emit `workspace.trust_failed`,
   and let the spawn proceed — never fail the dispatch.
5. WHEN `routing.harnessTrust.enabled` is `false` THEN the system SHALL still apply the
   plugin write, and vice versa — the two pre-spawn steps are independently switchable.

### Requirement 4 — this repository's own sessions get the same treatment

**User story:** As a contributor working `the-loop` in a Claude Code cloud/web session, I
want the plugin enabled by the repository itself, so that a session that never went
through the daemon still runs the loop.

#### Acceptance criteria (EARS)

1. WHEN a session starts in a trusted checkout of this repository THEN the repository's own
   `.claude/settings.json` SHALL carry the same two entries, matching the diff in the issue.

## Non-functional requirements

- **Idempotent and quiet.** Re-spawning into the same checkout writes nothing (the daemon
  spawns constantly; a file rewritten on every event would race an interactive harness
  process saving the same file).
- **Same write discipline as `trust.py`.** Only the named keys, merged into what exists,
  temp file + atomic replace, `0600` on a file we create, symlinks resolved rather than
  replaced.
- **No new dependency** (`minimalism`): the writer reuses the existing JSON-merge helper.

## Security considerations

- **Actors & trust:** the only actor is the operator running the daemon. Nothing here
  reads the webhook payload, the repository contents, or any other untrusted input — the
  marketplace repository comes from the operator's own config file, and the plugin and
  marketplace *names* are constants in the-loop's source.
- **Trust boundaries & data:** the boundary this crosses is *"what code a spawned harness
  session loads"*. Enabling a plugin makes the harness fetch and run that plugin's skills,
  commands and **hooks** — the SessionStart hook runs on session start. Pointing
  `marketplaceRepo` at a repository is therefore a decision to execute what that repository
  ships, and the config doc must say so. No secrets are read or written; the settings file
  may hold operator state, so a file we create stays `0600`.
- **Scope of the write.** `enabledPlugins` in the *user* settings file is machine-global:
  it enables the-loop in every Claude Code session on that account, not just the ones the
  daemon spawns. This is the same asymmetry `harnessTrust.acceptBypassPermissions` already
  carries, and it is documented in the same conscious-decision terms rather than being
  slipped in.
- **Abuse cases (EARS):**
  1. WHEN a work item's repository ships a `.claude/settings.json` naming some other
     marketplace THEN the system SHALL ignore it — the daemon writes only from its own
     config, never from a cloned repository's files.
  2. WHEN the configured `marketplaceRepo` contains shell metacharacters, a URL, a path
     traversal, or anything else outside `owner/repo` THEN the system SHALL refuse to write
     it (no subprocess is involved anywhere in this path; the guard exists so junk cannot
     be planted in the operator's settings file).
  3. WHEN an operator has deliberately set `enabledPlugins["the-loop@the-loop"] = false`
     THEN the system SHALL respect that and not flip it back on.
- **Fail closed:** an unreadable, unparseable, or unexpectedly-shaped settings file is
  reported and left untouched; a malformed `marketplaceRepo` writes nothing. Every failure
  degrades to today's behaviour (a session without the plugin), never to a wider write.

## Out of scope

- **Installing arbitrary plugins.** The config knob turns the-loop's *own* enablement on or
  off and redirects which repository it comes from; a general "install these plugins in
  every spawned session" list is not requested and would be a different feature
  (`reference/minimalism.md`).
- **Cursor.** `cursor-agent` exposes no equivalent settings surface, so it stays a no-op —
  the same position it holds for workspace trust.
- **Project-scoped enablement for cloned repositories.** Writing into a checkout's
  `.claude/settings.local.json` is considered and rejected in `design.md`.
- **Verifying the plugin actually loaded.** the-loop writes the config the harness reads;
  it does not shell out to `claude plugin` to confirm.

## Open questions

None. The issue states the target shape exactly; the one judgement call (which settings
file) is recorded as a decision record in `design.md`.

## Review comments

*None yet.*
