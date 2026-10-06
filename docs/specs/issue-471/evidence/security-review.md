---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#471"
---

# Security review: the spec chain as one Claude artifact (issue-471)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Authorization:* unchanged. The `claude-artifact` row is read only from the reply
    an authorized user signed with `the-loop execute`, or from the checklist that reply
    signed (`_authorized_comments`, the same path every row uses). It is matched by exact
    token against `_CHECK_LINE`, and is never a phase, a skip, an opt-in or a refusal
    (tested ticked and unticked).
  - *Agent-writable state:* `work-item-state.json` is agent-writable. `claudeArtifact`
    is read with `is True` in `WorkItemState.load`, in the runtime freeze, in
    `GraphLink` and in the archive. A string, number, list or object reads as `false`
    (tested with each).
  - *Prompt injection:* the prompt line is a module constant (`CLAUDE_ARTIFACT_LINE`),
    selected by one boolean. No payload, state string or comment text enters it.
  - *Gate integrity:* the CLI adds no ingress for artifact comments, and no gate reads
    them. The skill states that an artifact comment is untrusted feedback, that its
    author is not checked against `routing.authorizedUsers`, and that it never answers
    a gate.
  - *Disclosure:* the CLI publishes nothing and holds no new credential. The session
    publishes to the operator's own Claude account, private by default, and the skill
    forbids changing the sharing. The spec chain already reaches the same provider as
    model input. The evidence redaction rule still governs what a spec may contain.
  - *Fail closed:* unreadable checklist, absent row, non-boolean value, a harness known
    not to be `claude`, and a session without the artifact tool all resolve to no
    artifact (tested except the last, which is the skill's rule).
- **Sign-off:** tier 3, so no named security sign-off is required; the PR approval is
  the human gate.
