---
type: execution-log
workItem: "issue-136"
phase: needs-review
status: in-progress
---

# Execution Log: a spawned session still opens on the workspace-trust dialog

> Append-only log of progress for the user's visibility. Checked in alongside
> the spec at `docs/specs/issue-136/`.

## Phase transitions

| Phase | Entered | Reviewed/approved by | Notes |
|-------|---------|----------------------|-------|
| requirements-definition | 2026-08-04 |  | Issue #136: the issue-90 pre-spawn trust write does not silence the dialog at the default scope. Root cause confirmed against the shipped `claude` binary before drafting. |
| design | 2026-08-04 |  | One seam: `ClaudeTrustStore.trust()` writes the trust key on the cwd **and** (when supplied) the root, instead of one or the other. `scope` is redefined as "does trust additionally widen", not "where trust goes". |
| tasks-breakdown | 2026-08-04 |  | 9-task DAG |
| implementation | 2026-08-04 |  | Implemented on `claude/github-issue-136-r0wa2t` |
| needs-review | 2026-08-04 |  | PR opened; awaiting human review + named security sign-off (risk tier 4, `human-approves-pr`, `security.review.humanSignOffMinTier: 4`) |
| complete |  |  |  |

## Progress entries

### 2026-08-04 — root cause confirmed against the shipped harness

- **Phase:** requirements-definition
- **Did:** The report names a race; it is not one. Read the trust logic out of the
  shipped `claude` binary rather than guessing, and found `hasTrustDialogAccepted`
  has **two** readers with different scoping rules:
  - the base "is this workspace trusted" check walks **up** from the cwd — this is
    the one issue-90 satisfied with a root entry;
  - a second gate reads the **exact** project key with **no** walk. It decides
    whether the dialog is shown *anyway*, and whether the repository's own
    `.claude/settings.json` `permissions.allow` / `additionalDirectories` load. It
    short-circuits only on sandbox mode, an in-session acceptance, a background
    session kind, `cwd == $HOME`, or that exact-key trust — **never** on the
    permission mode, so `--dangerously-skip-permissions` cannot help.

  So at the default `scope: workspace-root`, every fresh checkout of a repo that
  ships project-scoped grants gets the dialog. the-loop's own repository ships
  exactly such a `.claude/settings.json`, which is why the reporter sees it every
  time.

  Reproduced headlessly, because `claude -p` prints the same gate's diagnostic
  instead of rendering the modal. Config written **by `ClaudeTrustStore` itself** at
  the default scope, in a fake HOME, with a repo carrying allow-rules:

  ```console
  $ cd <root>/.worktrees/repo && claude -p "reply with OK"
  Ignoring 1 permissions.allow entry from .claude/settings.json: this workspace has
  not been trusted. Run Claude Code interactively here once and accept the trust
  dialog, or set projects["<root>/.worktrees/repo"].hasTrustDialogAccepted: true in
  <home>/.claude.json.
  Ignoring 1 permissions.additionalDirectories entry from .claude/settings.json: …
  ```

  The harness names the missing key itself: the **checkout's** project key, not the
  root's.
- **Next:** design + tasks, then the one-line-shaped fix.
- **Blockers:** none.

### 2026-08-04 — implemented (T1–T9)

- **Phase:** design → tasks-breakdown → implementation → needs-review
- **Did:**
  - **T1–T2 (red).** Inverted the two unit assertions that *encoded* the bug
    (`"hasTrustDialogAccepted" not in projects[str(workdir)]`) and extended the
    `workspace-root` integration scenario to require the checkout's own trust key at
    the moment the harness starts. Added cases for `root == cwd` (no duplicate in the
    audit note), the applied-note contents, and the repeat-spawn no-write. 5 failures,
    each for the right reason.
  - **T3–T4 (green).** `cli/the_loop/trust.py` — `trust()` now starts `trust_keys`
    from the cwd keys and *appends* the root's keys (deduplicated) when a usable root
    is supplied, instead of choosing one or the other. The applied note renders every
    top-level directory written, replacing the `is not` identity check that stopped
    being meaningful. Module and method docstrings rewritten around the two-readers
    finding.
  - **T5.** Confirmed the unchanged paths: `scope: directory`, an ignored root, a
    too-broad root, and idempotence on a repeat spawn all behave exactly as before.
  - **T6–T8.** `.the-loop/cli-config.schema.json`, `docs/config/cli/routing-options.md`,
    both `cli-config.yaml` comment blocks, `skills/the-loop/reference/automation.md`,
    `docs/capabilities/interactive-sessions.md` and `docs/capabilities/webhook-triggers.md`
    now describe `scope` as *"does trust additionally widen"*. Also removed a claim
    that was already stale before this work: `automation.md` still said trust was
    "scoped to the spawn directory and never a parent", which PR #92 had made untrue
    when it defaulted to `workspace-root`. Recorded as
    [decision-052](../../decisions/decision-052.md), revising decision-037's scoping
    half.
  - **T9.** `make check` green.

  **Evidence — end to end against the real binary.** Same fake HOME and repo as the
  reproduction above, config regenerated by `ClaudeTrustStore.trust()` at the default
  scope after the fix:

  ```console
  $ uv run --project cli python -c "…ClaudeTrustStore(...).trust('<root>/.worktrees/repo', '<root>')"
  ['trusted <root>/.worktrees/repo and <root> (and everything under it) in <home>/.claude.json']
  $ python3 -m json.tool <<< "$(jq .projects <home>/.claude.json)"
  {
    "<root>/.worktrees/repo": {"hasTrustDialogAccepted": true,
                               "hasCompletedProjectOnboarding": true},
    "<root>":                 {"hasTrustDialogAccepted": true}
  }
  $ cd <root>/.worktrees/repo && claude -p "reply with OK"
  OK
  ```

  No diagnostic, grants load, session runs.

  **Test evidence (red→green).**

  | | before | after |
  |---|---|---|
  | `cli/tests/test_trust.py` | 4 failed | pass |
  | `cli/tests/test_trust_integration.py` | 1 failed | pass |
  | `make check` (lint · format · pyright · config-validate · 974 tests) | — | green |

- **Next:** post the reviewer briefing on the PR; human approval + named security
  sign-off.
- **Blockers:** none.

## Review rounds

### Self-review (3 of 3, `reviews.selfReviewCount`)

1. **Correctness of the seam.** Walked each `scope` × root combination against the
   new `trust_keys` construction: `directory` (no root reaches the store) → cwd only,
   unchanged; root not containing the cwd → `is_within` false → cwd only, unchanged;
   too-broad root → filtered out a level up in `Dispatcher._trust_root()` → cwd only,
   unchanged; `root == cwd` → deduplicated to one key so the audit note does not list
   the same directory twice. Idempotence is unchanged because it lives in `_set_flag`
   / `_update_json`, not in key selection. **No findings.**
2. **Audit-trail honesty.** The old note used `trust_keys is not onboarding_keys` to
   decide its wording — an identity check that silently becomes always-false once
   `trust_keys` is derived from `onboarding_keys`. Caught and replaced with an
   explicit render naming every top-level directory written, and pinned by
   `test_the_applied_note_names_every_trusted_directory`. Realpath aliases stay out of
   the note deliberately: the same directory under a second name is noise, not scope.
   **1 finding, fixed.**
3. **Documentation parity.** Swept every place outside `docs/specs/` that describes
   trust scoping. Found `skills/the-loop/reference/automation.md` still claiming trust
   is "scoped to the spawn directory and never a parent" — stale since PR #92, not
   this change — plus five other places phrasing `scope` as *where* trust goes.
   All corrected; `test_docs_parity.py` and markdownlint green. **1 finding, fixed.**

### Critic review

`reviews.critics` is empty in `.the-loop/harness-config.yaml`, so the configured
critic rounds have no harness to run
(`the-loop critic run` needs at least one registered entry). Recorded here rather
than silently skipped — the human review at the PR is the compensating gate, and the
change is small, fully covered by tests, and verified end to end against the real
harness binary.

### Security review (`security.review`, gate)

Mechanism `auto`. The change is in scope for a security review because it widens what
the daemon marks trusted on the operator's machine.

- **Boundary moved:** under `scope: workspace-root`, one additional project key —
  the spawn directory the daemon just created and is about to run in — is marked
  trusted. That directory is already inside the operator's declared trusted root and
  already passed the harness's base trust check through the ancestor walk. Under
  `scope: directory` the behaviour is byte-for-byte unchanged.
- **Effective new capability:** a cloned repository's own `.claude/settings.json`
  `permissions.allow` / `additionalDirectories` now load, where before they were
  dropped. This is what answering the dialog by hand does, and what `scope: directory`
  already did. It means pre-trusting a clone honours grants authored by anyone who can
  push to that repository — now stated explicitly in the schema, the config reference
  and the capability doc rather than implied. `harnessTrust.enabled: false` is the
  opt-out.
- **Guards intact:** `is_within` still refuses a root that does not contain the cwd;
  `is_too_broad` still degrades `/` and `$HOME`; an unparseable config is reported and
  never overwritten; writes stay narrow (two booleans), merged, atomic, `0600` on
  create, and skipped when already correct; a failed write warns, emits
  `workspace.trust_failed`, and lets the spawn proceed — degrading to the dialog
  (narrower), never to a wider grant.
- **No new inputs or execution:** the spawn directory comes from the-loop's own
  workspace machinery, never from payload text; nothing is parsed, interpolated into a
  shell command, or executed. No credential is read or written.
- **Human sign-off:** risk tier 4 (`.the-loop/cli-config.schema.json` matches
  `autonomy.sensitivePaths`), so `security.review.humanSignOffMinTier: 4` requires a
  **named human security sign-off** on the PR before this can be marked complete.
  Pending.
