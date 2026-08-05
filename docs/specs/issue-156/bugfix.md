---
type: bugfix
phase: requirements-definition
workItem: issue-156
status: approved
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
---

# Bugfix spec: remove the process runner — a stale session record silently downgrades tmux delivery to a dead process resume

> Phase 1 of 3 for a bug (bugfix → design → tasks). Human approval for this
> tier-3 change happens at the PR (`autonomy.tiers."3": human-approves-pr`).

## Summary

As reported, `routing.runner: tmux` only controls the runner chosen at **first
spawn**. Once a session record exists under the registry, every later dispatch
reads the runner from the record itself ("the session's recorded runner wins",
decision-021). A record that ends up with `runner: "process"` — the dataclass
default when the field is omitted — silently redirects every subsequent event
for that work item to a headless `adapter.resume(...)` subprocess, using
whatever `cwd`/`harnessSessionId` the record happens to carry, instead of the
tmux session the operator is watching. No reconciliation compares the record
against the live config, and nothing logs the disagreement: the poller reports
a *successful* dispatch while the operator's tmux pane stays silent.

The owner's decision on the ticket
([comment](https://github.com/MadaraUchiha-314/the-loop/issues/156#issuecomment-5186334064))
resolves the bug at its root instead of patching the reconciliation gap:
**remove the in-process (headless subprocess) runner entirely. tmux is the only
runner.** With a single runner there is no per-record runner choice left to go
stale, no config/record disagreement to reconcile, and no silent path for a
delivery to take: every dispatch either lands in the work item's `loop-<slug>`
tmux session or respawns one, loudly, through the existing issue-80/89/146
machinery.

## Steps to reproduce

1. Run the daemon with `routing.runner: tmux` in `cli-config.yaml`.
2. Get a work item's registry JSON into a state where `runner` is `"process"`
   (manual edit, a copy/pasted session file, an out-of-band
   `the-loop sessions register` — which never sets `runner`, so the dataclass
   default applies — or a race between two near-simultaneous events).
3. Trigger a new comment/event for that work item.
4. The poller logs "routing X -> session Y" and records a successful dispatch,
   but nothing appears in the tmux session — delivery went to a one-shot
   subprocess resume, with no warning anywhere.

## Expected vs actual

- **Expected:** with the operator running a tmux fleet, every event for a work
  item is delivered into (or respawns) its attachable `loop-<slug>` tmux
  session; any inability to do so is loud.
- **Actual:** events are silently consumed by headless `claude -p --resume …`
  subprocesses driven by a stale record; if the record's `cwd` points at
  another work item's checkout, the resumed process runs against the wrong
  working directory entirely, with no error surfaced.

## Root cause (confirmed by reading the code)

`Dispatcher._dispatch_one` branches on `session.runner == "tmux"`; anything
else falls to `adapter.resume(...)`. `Session.runner` defaults to `"process"`
(`sessions/registry.py`), so any record written without the field — including
every record `the-loop sessions register` creates — takes the headless branch
forever. `RoutingConfig.runner` is consulted only in `_spawn_for`, i.e. at
first spawn. The defect is structural: two runners, a per-record selector with
a quiet default, and no invariant tying the selector to the config. The fix the
owner chose removes the second runner, and with it the selector.

## Requirements

The wording of the owner's decision: "remove the whole in-process based
claude/cursor run. ONLY run using tmux. remove all code and documentation
related to process based runner."

### Requirement 1 — tmux is the only runner

**User story:** As an operator, I want every daemon-driven session hosted in an
attachable tmux session, so that nothing the-loop does is invisible to me.

#### Acceptance criteria (EARS)

- **AC1.1** WHEN the dispatcher spawns a session for a work item THEN the
  system SHALL host it in a named tmux session (`loop-<slug>`), with no
  configuration able to select a headless subprocess instead.
- **AC1.2** WHEN the dispatcher delivers an event to an existing session THEN
  the system SHALL deliver into the recorded tmux session, or take the existing
  respawn path when it is gone — never a headless `adapter.resume` subprocess.
- **AC1.3** WHEN the daemon (`gh-webhook start` / `poll start`) starts THEN the
  system SHALL always require the `tmux` binary in its dependency check.

### Requirement 2 — the process runner's code and vocabulary are removed

**User story:** As a maintainer, I want the process-runner code paths gone, so
that no stale record or config can route a delivery somewhere silent.

#### Acceptance criteria (EARS)

- **AC2.1** WHEN reading the harness adapter contract THEN the system SHALL
  expose no headless per-dispatch `spawn`/`resume` subprocess path; the
  one-shot invocation surface used by critic reviews (`oneshot_argv`) SHALL
  remain.
- **AC2.2** WHEN a session record is written THEN the system SHALL no longer
  write a `runner` field, and WHEN an old record carrying one (any value) is
  read THEN the system SHALL ignore it rather than branch on it.
- **AC2.3** WHEN `routing.runner` appears in an operator's config THEN the
  system SHALL ignore it and log a warning naming the removal (tmux-only), and
  the config schema SHALL no longer declare the key.
- **AC2.4** WHEN a session record has no live tmux session behind it —
  including a legacy record written by the process runner or by
  `sessions register`, which has no `tmuxTarget` — THEN the next dispatched
  event SHALL take the respawn path: resume the recorded conversation in a
  fresh `loop-<slug>` tmux session when possible, else start a fresh one, per
  the existing issue-89/146 rules.

### Requirement 3 — documentation matches the single-runner reality

**User story:** As an operator reading the docs, I want no instruction that
configures or describes the process runner, so that I cannot configure a mode
that no longer exists.

#### Acceptance criteria (EARS)

- **AC3.1** WHEN reading the CLI config reference, the config templates, the
  skill reference docs, or the capability docs THEN the system SHALL describe
  tmux as the only way daemon sessions run; `routing.runner` and
  "process runner" SHALL appear only in historical records (decisions,
  changelog, past specs), which are not rewritten.
- **AC3.2** WHEN the affected capability docs are read THEN their behaviour
  tables SHALL reflect tmux-only dispatch, with a history row tracing to this
  spec.

### Requirement 4 — the removal is proved, and stays proved

**User story:** As a maintainer, I want the test suite to pin the tmux-only
behaviour, so that a future change cannot quietly reintroduce a silent path.

#### Acceptance criteria (EARS)

- **AC4.1** WHEN the test suite runs THEN tests SHALL cover: delivery to an
  existing tmux session, respawn of a legacy record without a `tmuxTarget`,
  the `routing.runner` ignore-with-warning, and the always-on tmux dependency
  check.
- **AC4.2** WHEN the full gate runs (pytest, ruff, pyright, markdownlint,
  config validation) THEN it SHALL pass.

## Security considerations

- **Untrusted actors / trust boundary:** the trust boundary between GitHub
  payloads and harness invocations is unchanged: nothing payload-derived
  reaches an argv, a path, or a tmux target. Removing the headless resume
  *shrinks* attack surface — the path where a corrupted registry file's
  `cwd`/`harnessSessionId` was handed to a subprocess (`adapter.resume`) is
  deleted; the remaining tmux paths keep their existing guards
  (`_SESSION_ID_RE` on resumed ids, `_LOOP_TARGET_RE` on signalled targets).
- **Abuse case:** a hand-edited session record pointing `cwd` at another work
  item's checkout could previously make a *silent* headless resume run there.
  Post-change the same record routes through the tmux respawn path, which
  spawns in that `cwd` but visibly — named `loop-<slug>` session, announce
  comment on first spawn, `session.respawned` events. The registry stays local
  operator-writable state; its validation rules are unchanged.
- **Fail-closed:** when tmux is unavailable the daemon refuses to start
  (dependency check) and a dispatch fails loudly; nothing degrades to a
  headless run.
- No new attack surface: no new inputs, no new privileged operations; this
  change only deletes an execution path.

## Out of scope

- The reconciliation/`sessions doctor` alternatives suggested in the issue
  body — superseded by the owner's decision to remove the process runner.
- Interactive support for the cursor harness in tmux (`cursor-agent` still
  raises `UnsupportedRunnerError` for interactive hosting, unchanged; it
  remains usable as a critic via `oneshot_argv`).
- Rewriting historical records: decisions (e.g. decision-021), CHANGELOG
  entries, and past specs keep their text.
- A registry migration tool: legacy records heal lazily on their next event
  via the respawn path (AC2.4); no eager rewrite of files on disk.

## Open questions

- None. The owner's comment on the ticket is the decision of record.
