---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#464"
---

# Security review: a Slack app from one click (issue-464)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Input:* the app name is the only operator input. Control characters, an empty
    name, a name over 35 characters and a name with no letter or digit are refused
    before anything is built or written (tested). It reaches the output only through
    `json.dumps`, `yaml.safe_dump` and `quote(safe="")`, and only into the two name
    fields.
  - *Network and credentials:* none. The verb opens no socket and reads no token. The
    link is opened by the operator's browser, and Slack's own dialog confirms the
    workspace and scopes before creating anything.
  - *File writes:* one file, at the path the operator passes or beside the resolved CLI
    config. Written atomically. A file the command cannot read as a manifest is never
    overwritten without `--name`. The file holds no secret.
  - *Scope drift:* regeneration builds every key except the name from the packaged
    manifest, so a tampered kept file cannot carry a scope through an upgrade (tested
    with an added `admin` scope).
  - *Tokens in the conversation:* `/the-loop:init` now says outright never to ask for a
    token in the chat. Tokens go to the environment or `env.file`, and the preflight
    reports presence only.
  - *Permissions:* the shipped scopes and events are unchanged.
- **Risk tier:** 3 (a CLI option that writes one local file, plus walkthrough text; no
  sensitive path touched). That is below the tier-4 threshold for a named human security
  sign-off. The PR approval is the human gate.
