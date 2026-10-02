# Codex completion security review

## Security review

Mechanism: the-loop security checklist, applied to the Codex remediation and
the local completion fixes. The local code review found no remaining actionable
security finding after S1 was fixed. This does not satisfy a remote approval gate.

| Boundary | Evidence and result |
| --- | --- |
| Conversation identity | UUID validation, exact absolute directory metadata, unique launch-marker matching and session-store containment. Negative tests cover unsafe IDs, wrong directories, ambiguity, symlink escape and malformed directory metadata. Passing. |
| Instruction files | Managed blocks preserve existing content; malformed managed blocks are rejected. Files escaping the checkout are refused. Writes retain modes and check for concurrent changes. Existing preservation and escape tests pass. |
| Hook and workspace trust | Hook installation reports the native trust requirement and does not bypass it. Sandbox and approval choices remain operator-owned. Trust preparation preserves existing TOML entries and uses atomic locked writes. Existing tests pass. |
| Harness delegation | Unknown harnesses block. Arguments use subprocess argv lists; Codex JSONL extraction feeds local JSON validation. Existing MCP and critic-output tests pass. |
| GitHub retries | Only a disconnected GraphQL read is retried; mutation and semantic failures are not replayed. Covered in the earlier Codex regression record. |
| Secrets and dependencies | Authentication remains in the normal Codex home. The completion fixes introduce no dependency or credential handling. No credential values appear in their code, fixtures or evidence. |

S1: malformed directory metadata could match the daemon's process directory.
The six negative regressions reproduced this before explicit absolute metadata
validation was added. See [self-review](self-review.md) and
[completion verification](completion-verification.md).

Human sign-off: **not verified**. The PR touches schema and trust surfaces;
the live selected gates and any required named sign-off must be checked before
completion. No approval is inferred from the request to drive the PR.
