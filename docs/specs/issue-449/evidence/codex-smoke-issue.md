# Verify PR #450 source installation with a fresh Codex work item

This is the pre-merge end-to-end verification for the-loop PR #450. Run this
work item with the **Codex** harness, using the daemon started from the devbox
repository and the corrected source installation.

Add `codex-smoke.md` with the exact line `Codex completed this work item.` and
link it from this repository's README. Open a PR delivering that change.

Acceptance criteria:

- The phase selection records Codex as the chosen harness and honors the
  authorized user's selected phases.
- The spawned session uses the installed PR #450 source and follows the-loop
  instructions and graph verbs.
- The smoke file and README link appear in the delivered PR; any selected
  verification and review steps complete with evidence.
- The session's Harness trace is readable and belongs to its native Codex
  conversation. Unrelated chats do not change its resume target.
- The test work item reaches completion under its selected gates. Record its
  issue, PR, session identity and verification evidence on PR #450 before merge.

Preserve the repository's existing content. This task introduces no dependencies
or credential changes. Native Codex hook trust must be established by the
operator through `/hooks` before relying on Stop continuation.
