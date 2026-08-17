# Evidence — security review (T8, ready-to-ship gate)

- **Mechanism:** `security.review.mechanism: auto` → the built-in security-review skill's
  checklist, applied to the diff of this branch.
- **Risk tier:** **4** (`autonomy.sensitivePaths` matches `**/*schema*`; the diff changes
  `.the-loop/cli-config.schema.json`). `security.review.humanSignOffMinTier` is 4, so this
  work item needs a **named human security sign-off** on the pull request. It is requested
  there, not granted here.
- **Verdict:** no new attack surface. One pre-existing surface is made *narrower*.

## The diff, by security-relevant surface

| Surface | Changed? | Finding |
|---|---|---|
| Authentication / authorization | no | `_endpoint_for` runs **after** `authorizedUsers`, the arming label and the control keywords. Nothing in this diff is reachable by an unauthorized actor that was not already reachable. |
| Untrusted input read | no new fields | The two payload fields this path reads — the pull request's `repository.full_name` and its `head.ref` — were both already read, by `_same_repository` and `_pr_head_ref` respectively. No field is read that was not read before. |
| Command execution | narrowed | `require_branch` changes only whether a `WorkspaceError` propagates. `Workspace._git` still builds an argv **list** and calls `subprocess.run` without `shell=True`; asserted mechanically by `test_git_is_invoked_without_a_shell`, which records every `subprocess.run` call made during a prepare with a metacharacter-bearing ref and checks the argv shape, the absence of `shell`, and that nothing was executed. |
| Filesystem paths | no | Checkout paths still come from `RepoTarget`, whose `full_name` traversal guard (`test_target_rejects_path_traversal_components`) is untouched, and from the work-item slug. |
| Secrets | none | This work item reads, stores, logs and moves no credential. |
| Network | no | No new host, port, protocol or outbound call. |
| Dependencies | none added | Stdlib and the existing `git` binary only. |
| Privilege / concurrency | widened, bounded, opt-in | `always` permits more concurrent harness sessions per work item. Bounded by the existing `maxConcurrentDispatches`, reachable only by an operator editing their own config file, and every spawn still passes the arming rules. Concurrency, not authorization. |

## The abuse cases from `requirements.md`, and what defeats each

| Abuse case | Mechanism | Test |
|---|---|---|
| 1 — a head ref shaped like a git option or carrying shell metacharacters | argv list, no shell; with `require_branch` the failed fetch **declines** the session instead of spawning onto a fallback tree | `test_git_is_invoked_without_a_shell` |
| 2 — a payload naming a repository the work item does not belong to | `record.endpoint_for(pr)` resolves only pull requests already linked to *this* record, and `link_pull_request` is written by the-loop's routing, never by the payload; the event must first clear authorization and the session lookup | `test_the_operator_chooses_which_pull_requests_get_their_own_session`, plus the existing binding tests |
| 3 — many hostile pull requests under `always` | arming rules unchanged (`authorizedUsers`, auto-execute label, control keywords); dispatch bounded by `maxConcurrentDispatches` | existing control/authorization suites, unchanged and green |

## Fail-closed, asserted rather than asserted-about

| Ambiguity | Resolves to | Test |
|---|---|---|
| `sessionPerPr` is a value the system does not recognise | `cross-repository` — the shipped default, the **narrower** of the two splitting choices — with a warning naming the rejected value | `test_an_unrecognised_session_per_pr_fails_closed_to_cross_repository` (5 cases: a wrong name, wrong case, empty string, a number, a list) |
| a checkout cannot be prepared for the endpoint | decline the session, deliver into the work item's, record `session.pr_session_declined` | `test_always_still_declines_the_session_when_there_is_no_checkout_for_it` |
| a same-repository checkout is not on the pull request's branch | decline (never share, never spawn onto the wrong tree) | `test_always_declines_to_one_session_when_the_branch_cannot_be_held_twice` |

Notably, the **wrong-tree** row is a fail-closed path this work item *adds*. Before it, the
only thing standing between an endpoint and a tree on the wrong branch was that
same-repository endpoints could not exist at all — a guard by unreachability. Making them
reachable required making the guard explicit, and it now covers a case
(`ensure_worktree`'s detached fallback landing on a distinct path) that the existing
`_same_path` shared-tree check would have waved through.

## Redaction

Nothing to redact. This work item produced no capture containing a token, cookie, personal
datum or internal hostname — the evidence files are pytest and linter output over
repository-relative paths and pytest `tmp_path` directories. Stated rather than implied, per
`reference/security.md`.
