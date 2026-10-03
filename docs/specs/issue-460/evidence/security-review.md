---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#460"
---

# Security review: an orphan tag blocks every release (issue-460)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Permissions and credentials:* unchanged. `contents: write` stays on the release
    job and `id-token: write` on the publish job. No secret, token or environment is
    added.
  - *`ref: main`:* the job now always builds and publishes from `main`'s tip. Before,
    a `workflow_dispatch` from another branch would build that branch and push it as
    `main`. That path is now closed, which narrows what can be published.
  - *`--atomic`:* a failed push now writes nothing. It used to write a tag. This is
    fail-closed.
  - *Recovery:* the only content change is version strings and one changelog entry,
    taken from the orphan bump commit `95bfe36`. No remote tag or release is deleted or
    rewritten.
  - *Trust boundary:* unchanged. No untrusted input is read.
- **Risk tier:** 3, raised by the sensitive path `.github/workflows/**`. Tier 3 is
  below the tier-4 threshold for a named human security sign-off. The PR approval is the
  human gate.
