# Evidence — security review (gate)

**Mechanism:** the harness's built-in `security-review` skill, run on
`claude/github-issue-360-uav3nz`. **Outcome: pass — no findings.**

One note on scope, because it matters for reading this record. The skill diffs the branch
against `origin/HEAD`, which on a fresh clone here resolved to the whole of the previous
release (issue-358's merge plus the version bump) rather than to this work item. The
review below is deliberately scoped to **this branch's own changes** — reviewing already
merged and already reviewed work would produce findings that belong to another work item's
paper trail, and issue-358 has its own
[`security-review.md`](../issue-358/evidence/security-review.md).

## What was reviewed

```console
$ git diff --stat main..HEAD    # source and test files only; the spec chain is untracked prose
 cli/tests/test_critics.py            | 21 +++++++++++++++++++-
 cli/tests/test_modelchoice.py        |  5 ++++-
 cli/tests/test_modelprobe.py         | 26 ++++++++++++++++++++++++-
 cli/the_loop/harness/cursor_agent.py |  6 +++++-
 docs/capabilities/review-loop.md     |  6 ++++++
```

The whole of the non-test change is one class attribute:

```python
-    model_flag = "-m"
+    model_flag = "--model"
```

## The abuse cases of `bugfix.md`

| Case | Verdict | Why |
|---|---|---|
| AC1 — a model name smuggles a second option into the cursor argv | **not exploitable, unchanged** | `critics.run_critic` spawns a **list** argv with `shell=False` (`critics.py:446`) and the name is one element; a long flag consumes one following argument exactly as the short one was meant to. Covered by `test_placeholder_value_with_metacharacters_stays_one_argument` and `test_the_prompt_reaches_the_critic_as_one_argument`, both unchanged and passing. |
| AC2 — the change makes a model offerable that the harness refuses | **no** | `offerable` still withholds only on a standing `refused` verdict, and a verdict is still produced only by running the harness. The change alters which flag the probe *sends*, never how a verdict is read. `test_abuse_a_forged_verdict_cannot_introduce_a_choice` is unchanged and passing. |
| AC3 — the claude adapter's argv changes | **no** | `ClaudeCodeAdapter.model_flag` was already `--model` and is untouched; `test_oneshot_argv_appends_the_model_flag` is unchanged and passing. |

## Categories examined, and why each is empty

- **Command injection.** The only new value is a constant the-loop itself authors. No
  untrusted input reaches it, and the spawn is `shell=False` list-argv, unchanged.
- **Path traversal / file operations.** None added. The verdict cache's path, reads and
  writes are untouched; the new test writes only under pytest's `tmp_path`.
- **Authn / authz.** No gate, no permission check, no authorization path is touched. The
  phase-selection gate's authorization (`the-loop execute` by an authorized human) is
  unchanged; what changes is only which spelling the resolved choice becomes.
- **Secrets / data exposure.** Nothing new is logged. `modelprobe` already logs a refused
  name and a truncated harness output; that code is unchanged, and this fix *reduces* what
  reaches it, since a rejected-flag error message no longer arrives there as a refusal.
- **Deserialization.** None added — no new parsing, no new file format, no new field.

## Direction of the change

The defect was a control that silently did not run: an `unavailable` critic round does not
count toward `reviews.criticReviewCount`, so a cursor critic with a model removed itself
from the review bar while the roster still looked healthy. Fixing it **restores** a review
control rather than relaxing one.

**Human sign-off:** n/a — risk tier 2, below the tier-4 threshold that requires a named
human security sign-off (`reference/security.md`).
