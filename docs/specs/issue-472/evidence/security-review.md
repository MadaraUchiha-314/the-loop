---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#472"
---

# Security review: make the phase-selection comment easier to read (issue-472)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *Authorization:* unchanged. No line of `classify_phase_selection`,
    `_parse_selection`, `_authorized_comments` or the freeze changed. The rows a reply
    is matched against are byte-identical in shape and order (`test_selection_layout.py`
    reads them back with the gate's grammar and the Slack mirror's).
  - *Injected markup:* the new `<details>` and `<summary>` text is all module
    constants. The only interpolated values are the ones the comment already printed:
    node ids and descriptions from the shipped graph, the execute keyword, token-checked
    harness, model and effort names, and the declared channel refs. None of them is put
    inside a `<summary>` tag. No reader's text reaches the comment.
  - *The Slack mirror:* `_unfold` only removes `<details>` lines and turns
    `<summary>X</summary>` into `**X**`. It runs after HTML comments are stripped and
    broadcasts are neutralised, and outside code, so it cannot bring back a marker or
    a `<!here>`. Applied to a human's comment, it can only remove the two tags.
  - *Self-authored stamp:* the comment still ends with `SELECTION_MARKER` and is
    stamped by `mark_self_authored`, so the gate still drops its own comment before
    authorization (tested).
  - *Fail closed:* no parse path changed, so every unreadable-input path resolves as
    before.
- **Sign-off:** tier 3, so no named security sign-off is required; the PR approval is
  the human gate.
