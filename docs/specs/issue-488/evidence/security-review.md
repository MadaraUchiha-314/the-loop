---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#488"
---

# Security review: the explainer, the spec quiz and the code quiz

> The `security-review` node's proof. See `reference/security.md`. Reviewed against
> `origin/main...HEAD` (merge base `60a5dd9`), after the self-review and critic fixes
> (head `61e4999` and the records after it).

## Security review (gate)

- **Mechanism:** the-loop checklist (`reference/security.md` § The checklist). This
  harness exposed no built-in security-review skill to the session. Each item below was
  verified against the diff.
- **Outcome:** **escalated.** Three security findings from the review rounds are fixed.
  One finding, SR1, needs a human decision. The risk tier requires a named sign-off.
- **Effective risk tier: 4.** `requirements.md` states tier 3, "rises to 4 if the design
  touches a schema". The diff touches `.the-loop/manifest.yaml` (two evidence rows),
  and `.the-loop/**` is one of the fixed sensitive paths. No `*schema*`, workflow, auth,
  secret or credential path is touched. (A diff against the stale local `main` lists
  upstream schema files. Against `origin/main` it lists only the manifest.)

### Checklist

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | Every trust boundary in design §Security design is enforced | **pass, stronger than designed** | "Who ticked": `quiz-attested` reads the editors from GraphQL. It requires a non-empty, authorized editor for **every** edit in the history (C1), and a comment authored by an authorized login, or `isSelf` on Jira (S1, S8). "Untrusted text → page": the engine is unchanged and renders with `textContent` only (T5 and abuse case 3). "Self-attested": the comment and the record say "attested by", never "passed" |
| 2 | Untrusted inputs are constrained at ingress | pass | Marker and box are parsed with anchored regexes (`quizmarks.py`). Every part of the view command must match `^[A-Za-z0-9._/-]+$`, else no command is built (`test_a_hostile_location_gets_no_shell_command`). The edit list is read as data. Quiz JSON escapes `<` as `<` (C3 fixed the reference) |
| 3 | Untrusted content cannot steer privileged behaviour | pass | The `quiz_attestation` doorbell carries a comment id and the marker's node name, never a body or an actor. It cannot spawn, arm, or deliver a prompt (`test_a_quiz_tick_on_a_work_item_with_no_waiting_gate_spawns_nothing`). It only makes a waiting gate look again. A human comment carrying copied markers can ring it, but the gate then refuses that comment (S1). Rings are deduplicated per comment, body and version (S9) |
| 4 | No secrets in code, config, logs or fixtures | pass | A credential-pattern grep over the diff's added lines finds nothing. `live-attribution.md` holds a public node id, logins and timestamps only. The T11 query used `THE_LOOP_GH_TOKEN` once, by the owner's explicit reply, and printed nothing of it |
| 5 | AuthZ fails closed | pass | An empty or unknown editor is refused before `is_authorized` (which is True for `None`) can wave it through. A failed query, a marker mismatch or Jira's unsupported history all mean `wait`. An unauthorized editor anywhere in the history means `wait` (C1). `explainer-postdates-spec` stands aside outside a git checkout. That is a quality check (R5.6), not an authorization one, and the gate's digest check still applies |
| 6 | Least privilege | pass | One read-only GraphQL query (`comment_edits`) and read-only `git status`, `log` and `merge-base`. No new token, scope or write path |
| 7 | Every abuse case has a passing negative test | pass | 1: `test_quiz_attested_refuses_unauthorized_editor` (it also asserts `graph.quiz_refused`). 2: `test_quiz_attested_fails_closed_without_editor`. 3: `test_explainer_template_renders_text_not_markup`. 4: `test_quiz_attested_ignores_unmarked_and_artifact_text`. 5: the T11 redaction grep (`live-attribution.md`). 6: `test_quiz_attested_ignores_forged_comment`, `test_a_look_alike_with_a_wrong_digest_cannot_send_the_quiz_back`, `test_an_unticked_look_alike_cannot_hide_the_real_tick`, `test_an_authorized_edit_after_an_unauthorized_tick_does_not_pass`. All pass in the 6137-test run |
| 8 | New dependencies are justified and trusted | pass | No runtime dependency is added. The UI check (`evidence/ui/check.mjs`) uses Playwright and axe-core, installed locally as verification tooling only. Its `node_modules` is gitignored, and no package manifest is committed |

### Findings

| # | Sev | Finding | Disposition |
|---|---|---|---|
| S1 | high | A look-alike quiz comment from any commenter could force `stale` or hide the real tick | fixed `e9138f7` (self-review) |
| S8 | high (Jira) | The quiz marker was lost on Jira, so the gate re-posted on every event | fixed `3e247f5` (self-review) |
| C1 | high | An authorized edit after an unauthorized tick adopted that tick | fixed `61e4999` (critic) |
| SR1 | high | **The session's environment holds the operator's GitHub token (`THE_LOOP_GH_TOKEN`).** Design §Security design says the session cannot tick for the author because spawned sessions never receive a secret (issue-482). In this deployment that is false. A compromised or prompt-injected session could tick as the operator, and GraphQL would name an authorized user. The same token could also post an unmarked "approved" to any human gate, so this is not specific to the quiz | **escalated.** Not fixable in this change: the leak is in the spawn environment, not in the quiz. Asked on the PR ([comment](https://github.com/MadaraUchiha-314/the-loop/pull/489#issuecomment-6199110164)): open a separate issue for the regression, and is shipping with it documented acceptable? **Unanswered**, so not treated as accepted. The token was never used except for T11's one approved query |

**Deviation from the locked design.** design.md is approved, so it is not edited.

- **The comment's author is now part of the boundary.** Abuse case 6 was designed as
  "requires the self-authored marker and the node + digest marker". It now also needs
  the comment's author to be an authorized login (S1), or Jira's `isSelf` (S8).
- **The whole edit history counts.** The design read the latest editor. Every editor in
  the history must now be authorized (C1).
- **The marker's shape changed** to the colon form (S8).

Each change only narrows what passes.

- **Human sign-off:** **required, since the risk tier is 4. Pending.** It must come from
  @MadaraUchiha-314 on PR #489, together with a decision on SR1. Until both arrive, this
  record does not count as a sign-off and the work item cannot complete.
