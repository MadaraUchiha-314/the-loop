---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#536"
---

# Security review: the spec chain as one Claude doc (issue-536)

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md`), checked against
  `git diff origin/main...HEAD`.
- **Outcome:** pass.
- **Findings:** none.

| # | Item | Result | Evidence |
|---|------|--------|----------|
| 1 | Design boundaries enforced | pass | Ticket → gate: `claude-doc` is read in `classify_phase_selection` only from the authorized reply or the checklist it signed, matched by exact token through `_CHECK_LINE`. State → prompt: `WorkItemState.load` reads `claudeDoc` with `is True` and drops it beside `claudeArtifact: true`. `CLAUDE_DOC_LINE` is a module constant. Repository → claude.ai and doc → session: skill rules 3, 5, 6 and 7 in `reference/workflow.md` § The spec chain as one Claude doc. |
| 2 | Untrusted input constrained at ingress | pass | The only new input the CLI reads is one checkbox token. No state string, URL or comment text reaches the prompt line; unlike `claudeArtifactUrl`, there is no doc URL in state at all. |
| 3 | Untrusted content cannot steer privileged behaviour | pass | No code reads the doc. The skill frames doc edits and comments as untrusted feedback: they reach the repository only as a session-authored commit reviewed on the PR, and never answer a gate. The prompt line repeats "never a gate answer". |
| 4 | No secrets | pass | No credential is added. The diff's fixtures are rendered checklist text with no tokens. The doc is created through the operator's own connector session. |
| 5 | Fails closed | pass | Absent, unticked, unreadable, non-boolean, both-true on disk, a known non-`claude` harness: each resolves to no doc. Both rows ticked resolves to the default the checklist showed (the owner's decision on PR #537); it widens nothing, since an untouched reply gets the same, and the harness rule still applies after it (`test_both_ticked_on_another_harness_is_not_applied`) (tests in `test_claude_doc.py`). No connector: the skill says ignore and say so. |
| 6 | Least privilege | pass | The CLI gains no capability. The session uses a connector the operator already attached; the-loop never changes the doc's sharing. |
| 7 | Abuse cases have negative tests | pass | Unauthorized tick (`test_an_unauthorized_tick_changes_nothing`), state coercion (`test_anything_but_the_boolean_true_reads_as_false`, `test_both_true_on_disk_keeps_the_artifact`), both ticked (`test_both_ticked_uses_the_default_doc`). The doc-content cases (approval or instructions written in the doc, an editor's change) are skill rules with no code path to test; they are reviewed in `self-review.md`. |
| 8 | New dependencies | pass (n/a) | None. |

**Residual risk, accepted in the requirements.** A doc is editable by whoever the operator
shares it with, which is wider than an artifact's comment-only surface. The mitigation is
procedural (read before rewrite, fold edits in as feedback, review on the PR), not a code
check, because the-loop never reads the doc.

- **Human sign-off:** n/a — tier 3, so no named security sign-off is required; the PR approval is the
  human gate.
