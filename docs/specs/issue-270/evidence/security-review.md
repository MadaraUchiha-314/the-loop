# Security review (issue-270)

- **Mechanism:** the checklist in `skills/the-loop/reference/security.md`
  (`security.review.mechanism: auto` → no built-in security-review skill was available in
  this session, so the checklist is the recorded fallback).
- **Effective risk tier:** 3 (`autonomy.defaultTier`; no `sensitivePaths` touched — no
  schema, no workflow, no `harness-config.yaml`). Below
  `security.review.humanSignOffMinTier: 4`, so no named human security sign-off is required;
  human approval of the pull request still applies (tier 3 = `human-approves-pr`).
- **Reviewed against the diff:** `cli/the_loop/webhook/router.py`,
  `cli/the_loop/webhook/dispatcher.py`, `cli/the_loop/poller/poller.py`,
  `cli/the_loop/eventlog.py`, the two prompt-template copies and the docs.
- **Outcome:** pass, no findings.

## Checklist

| # | Item | Verdict | Evidence in the diff |
|---|---|---|---|
| 1 | every trust boundary in `design.md` §Security design is enforced where the design says it is | **pass** | the four boundaries are one mechanism each: the outcome is a fixed literal (`SETTLED_*` constants in `dispatcher.py`), the record is subtractive (`Deduper.mark_settled` only writes a value beside a key), the bound is the existing LRU (`Deduper.__init__`/`add`), and `done` outranks `settled` in `delivery_status` |
| 2 | untrusted inputs validated/constrained at their ingress; injection surfaces covered | **pass** | nothing untrusted enters the new code path. `_settle` takes `routed.delivery_id` (GitHub's own id, or the poller's synthesised `poll-comment-<id>`) and a literal the dispatcher owns. No comment body, title, label, branch, ref or author is read; nothing new reaches an argv, a path, a prompt or a filesystem write |
| 3 | untrusted content cannot steer privileged behaviour | **pass** | the settled record can only stop the poller re-forwarding. It cannot deliver an event, spawn/resume a session, arm a work item, or widen `authorizedUsers`. Every authorization guard (router self-marker → `authorizedUsers` → the control path's named-actor re-check) runs upstream and is untouched. The one *prompt* change is a constant sentence with no interpolation, on the trusted side of the `$payload_excerpt` boundary — asserted by `test_the_spawn_prompt_tells_the_session_to_read_the_whole_thread` |
| 4 | no secrets in code, config, logs or fixtures | **pass** | the new event (`poll.comment_settled`) carries a work-item ref, a comment id, the comment's author login and one outcome literal — the same fields `poll.comment_forwarded` already logs. No tokens, no bodies, no hostnames |
| 5 | AuthZ checks fail closed | **pass** | unchanged, and the new code sits *after* them. `control-rejected` is settled **because** the authorization check failed closed — the rejection is the outcome being recorded, not a bypass of it |
| 6 | least privilege | **pass** | no new file, network or process access. The change removes work: a settled comment stops being re-evaluated each cycle, and a settled presence stops re-forwarding |
| 7 | every abuse case from the requirements has a passing negative test | **pass** | the muting direction (could a *deliverable* comment be baselined?) → `test_a_delivery_a_session_received_outranks_a_settlement`; the retry direction (does a refusal that wants a retry still get one?) → `test_a_spawn_policy_drop_still_releases_its_id_and_settles_nothing`; the ledger-growth abuse case (a commenter accumulating permanent per-cycle work) → `test_a_pre_start_comment_is_refused_once_and_never_counted_again` |
| 8 | new dependencies justified and from trusted sources | **n/a** | none added |

## Residual risk, accepted and recorded

The settled mark is **process-local** (decision-097 D11), so a daemon restart between a
refusal and the first poll cycle reverts to the pre-change accounting for that one comment.
Bounded by one cycle where it used to be unbounded; the durable half of the fix — the
baselined comment id — is written by that cycle. The same limit bounds the narrowing of the
"a `cleanup` keyword re-forwarded after a restart executes twice" window: it is narrowed, not
closed, and the spec says so rather than claiming otherwise.
