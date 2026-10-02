# Codex documentation verification

## Capability docs

`docs/capabilities/interactive-sessions.md` now requires explicit absolute
rollout directory metadata. `docs/capabilities/distribution.md` now states
that the installed instructions include the required sibling writing skill.
Both updates ship with their corresponding fixes.

## Documentation

Updated the CLI installation page, install and upgrade command pages, plugin
installation guide and CLI README. They now describe the Codex component,
instruction and hook locations, required `/hooks` trust and runtime binary.
The install page documents preservation of existing instructions and approval
policy. Existing Codex instructions in the top-level README remain consistent.

The repository-wide Markdownlint CLI2 0.18.1 check and relevant installation
and documentation parity tests validate these changes. See
[completion verification](completion-verification.md).
