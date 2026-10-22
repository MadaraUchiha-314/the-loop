---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#517"
---

# Security review: hand a conversation to the-loop from any surface, at any stage

> The `security-review` node's proof. See `reference/security.md`.

## Security review (gate)

- **Mechanism:** the built-in `security-review` skill, run over `git diff 985bfd84..HEAD`
  against the threat model in `requirements.md` §Security considerations and
  `design.md` §Security design.
- **Outcome:** pass. No high-confidence vulnerabilities were found. Every trust-boundary
  defect found earlier, in self-review rounds 1–2 and the critic round, was fixed
  before this gate: empty-author admission, trust in a pasted self-marker, symlink
  escapes, forged lock lines, and the unadopted artifact URL. See
  [self-review.md](self-review.md) and [critic-review.md](critic-review.md).
- **Checked:**
  - **Record admission:** API-metadata author only, empty author refused, the
    self-marker grants nothing, and parts must come from the same author.
  - **Branch names reaching git:** the `the-loop/` prefix, `check-ref-format` rules,
    and argument-list git calls.
  - **Paths:** the closed artifact-name set, `contained()` against the repository root,
    and symlinked targets refused.
  - **Approvals:** the furthest artifact is never locked, a lock is recognised by its
    recorded hash, and the phase-selection reply and approval gates still need an
    authorized human.
  - **Deserialization:** a strict key–value parser, with no YAML, pickle or eval on
    comment content.
  - **Prompt and comment rendering:** only closed-set values and validated URLs are
    shown.
  - **Jira:** the mirror refusal, and `parent` validated as an issue key.
- **Findings:** none at high or medium confidence. One observation, accepted by design:
  a session holding the operator's credentials can post an operator-authored record.
  It changes only the phase-selection proposal, which an authorized reply must still
  sign.
- **Human sign-off:** n/a (risk tier 3, below 4).
