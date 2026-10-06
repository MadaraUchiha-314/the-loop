---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#466"
---

# Security review: arming a linked pull request (issue-466)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against the diff.
- **Outcome:** pass.
- **Findings:** none.
  - *New write:* one `POST /repos/{o}/{r}/issues/{n}/labels` per newly recorded PR,
    through the existing `GitHubClient.add_labels`, which adds and never replaces.
  - *Trust boundary:* the labels come from the executing process's own
    `routing.autoExecuteLabels`. No request field names a label. The PR's host passes
    `_trusted`, the same allow-list every issue-447 verb uses. An untrusted host is
    refused before a client is built, and a test asserts that no call is made.
  - *Arming an untracked PR:* labels follow a recorded link only. A failed link, or a
    work item with no session, applies nothing, so the change cannot make a stranger's PR
    spawn a session under `spawnOnUnmatched: labeled`.
  - *Who can call it:* unchanged. `pr create` still needs a registered work item, and
    `link-pr` still writes nothing without a session record.
  - *Fail-closed:* a refusal applies nothing, keeps the link, and exits 0 with a note.
    The note names the labels and GitHub's message, never the token.
- **Risk tier:** 3 (CLI behaviour that writes to GitHub; no sensitive path touched). That
  is below the tier-4 threshold for a named human security sign-off. The PR approval is
  the human gate.
