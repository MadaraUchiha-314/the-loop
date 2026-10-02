# Resume the requested Codex end-to-end verification

Run this only after writable machine/runtime access, network access and existing
GitHub authentication are available. The current session could not complete
those steps; [completion verification](completion-verification.md) records the
actual failures. PR #450 remains unmerged.

## Install and start from devbox

The source tree contains the completion fixes. Replace the installed CLI from
that tree, then start the enabled services from the requested cwd:

```sh
cd /Users/rohithr31/workspace/github.com/MadaraUchiha-314/devbox
uv tool install --force /Users/rohithr31/workspace/github.com/MadaraUchiha-314/the-loop/cli
the-loop --version
the-loop start
the-loop status
the-loop ticket show github:MadaraUchiha-314/the-loop#449
the-loop pr status github:MadaraUchiha-314/the-loop#450
the-loop pr threads github:MadaraUchiha-314/the-loop#450
```

Verify that the installed package contains the completion changes; its version
remains 19.19.0 until release. The devbox config already declares Codex as the
default and enables polling. Its configured token references are `GH_TOKEN` and
`GITHUB_TOKEN`; use existing credentials, never paste their values into evidence.
Review and trust newly installed native hook definitions through Codex `/hooks`.

## Create the smoke issue

After the local fixes and refreshed remote findings are resolved:

```sh
the-loop ticket create --repository MadaraUchiha-314/the-loop-testing \
  --title 'Verify PR #450 source installation with Codex' \
  --body-file /Users/rohithr31/workspace/github.com/MadaraUchiha-314/the-loop/docs/specs/issue-449/evidence/codex-smoke-issue.md \
  --label 'the-loop: auto-execute'
```

Record the returned issue URL. Let the configured poller pick it up. The
authorized user answers any phase-selection or approval gate the chosen graph
requires, selecting Codex if a harness choice is offered. Do not fabricate an
approval or silently skip a gate to make the test unattended.

## Verify before merging PR #450

Capture the new issue and PR URLs, source-install provenance, native Codex
session identity, graph outcomes, readable Harness trace, relevant CI and
review results, and the final smoke file and README link. Record the fresh
run in this evidence directory and publish the reviewer briefing through
`the-loop comment`. An earlier live test does not verify these completion fixes.

Merge PR #450 only after the fresh run and its selected review and approval
gates succeed. Post the issue #449 completion summary immediately after merge,
then claim the graph completion as required by the-loop's workflow.
