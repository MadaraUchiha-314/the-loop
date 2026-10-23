---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#498"
---

# Security review: a control keyword must open the comment; an ambiguous body is conversation

> The `security-review` node's proof (`reference/security.md`). Risk tier **4**: the
> change narrows the control trust boundary and touches `**/*schema*` and
> `.the-loop/**` (the `routing.control.keywords` description only). A named human
> security sign-off is required before the work item completes, distinct from the PR
> approval.

## Security review (gate)

- **Mechanism:** Claude Code's built-in `security-review`, as a sub-agent briefed with
  the control trust boundary. It traced the parser, the dispatcher's ambiguous path, the
  Slack relay's origin and speaker rules, and envelope and marker forgery.
- **Outcome:** no findings at confidence ≥ 8 ([PR comment](https://github.com/MadaraUchiha-314/the-loop/pull/523#issuecomment-6370129714)).
- **Checked and clean:**
  - The anchored pattern matches a subset of the old one.
  - An ambiguous body takes the command-free path: scope, the pause and awaiting-start
    suppressions, and `_on_unmatched`.
  - Only authorized speakers' words are relayed unmarked. Collaborators get
    `work-item.reply`, and `Speaker.may` blocks the binding acts.
  - The relay's attribution line cannot open with a keyword.
  - HTML-comment and envelope forgery is unchanged from the quoted form.
  - Origin judgment and `_pending_control_ids` are untouched.
- **After the review:** the critic's P1 fix (14b92cb6) narrows the phase-selection
  gate's reading from a substring test to the same grammar. It removes a path and adds
  none.

## Checklist (`reference/security.md`)

| # | Item | Result |
|---|------|--------|
| 1 | Every trust boundary in design §Security design enforced | pass — parser anchor, ambiguous → command-free path, gate grammar |
| 2 | Untrusted inputs constrained at ingress | pass — parser returns declared constants and validated arguments only |
| 3 | Untrusted content cannot steer privileged behaviour | pass — fewer bodies reach a command; authorized-actor guards unchanged |
| 4 | No secrets in code/config/logs/fixtures | pass — none added |
| 5 | AuthZ fails closed | pass — a body the grammar cannot read executes nothing |
| 6 | Least privilege | n/a — no new component |
| 7 | Every abuse case has a passing negative test | pass — two commands execute neither (`test_control.py`, `test_routing.py`); forwarding bypasses no pause (`test_an_ambiguous_comment_on_a_paused_session_is_still_suppressed`); gate not released (`test_selection_choices.py`) |
| 8 | New dependencies justified | n/a — none |

## Human security sign-off (tier 4)

Pending: requested on PR #523 with the review request.
