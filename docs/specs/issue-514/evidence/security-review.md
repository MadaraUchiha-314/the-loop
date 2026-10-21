---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#514"
---

# Security review: split `/the-loop:init` into `/init`, `/init-cli` and `/init-gateway`

> The `security-review` node's proof. Required before ready-to-ship unless an authorized
> human declared the phase away at `phase-selection`. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** security-review skill (Claude Code built-in). One sub-agent compared the
  non-documentation diff against `origin/main:commands/init.md`, checking injection,
  authorization, secrets exposure and schema validation.
- **Outcome:** pass. What it checked:
  - The credential rules carry over unchanged into `/init-cli`: presence only, never the
    value, prefix, length or hash, never written to a file, never pasted into the
    conversation. `/init-gateway` now applies the same rules to every `*Env` it
    declares. `/init` touches no credential.
  - Validation still reads the plugin's schema from disk, never the network, and a schema
    that cannot be read stops the command before it writes anything.
  - `/init-gateway` states the `listen.exposed` rule for a non-loopback host, which the
    old command left to the schema.
  - The Python and schema edits are strings and comments only.
- **Findings:** none. One non-security wording issue: the validate step came after the
  write step yet said to stop before writing. Fixed in `5b327dbc`.
- **Human sign-off:** n/a (risk tier 3).
- **Link:** https://github.com/MadaraUchiha-314/the-loop/pull/515#issuecomment-6309570044
