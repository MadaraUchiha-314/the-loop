# Evidence — security review

Reviewed: the full diff of this work item, against `design.md` § Security design and the
abuse cases in `requirements.md` § Security considerations.

## What this change adds to the attack surface

One new **input** and one new **read**:

1. Three checklist tokens parsed out of a comment body at `phase-selection`.
2. One key (`sessionPerPr`) read back out of the work item's portable record on the routing
   path.

Everything else is a move: the mode vocabulary and its resolver were relocated from
`webhook/dispatcher.py` to `the_loop/prsessions.py` unchanged, and the dispatcher imports
them.

## Boundary-by-boundary

| Boundary | Finding | Test |
|---|---|---|
| **Who may answer** | Unchanged. The rows are read from the same body, through the same `_authorized_comments` filter (self-marked comments dropped first, then `routing.authorizedUsers`), signed by the same execute keyword as the phase rows. There is no second channel and no second permission model. | `test_an_unauthorized_ticker_cannot_freeze_a_mode` |
| **What may be said** | A fixed vocabulary of three tokens, matched by dictionary lookup. Anything else is dropped — not obeyed, and not echoed into the refusal list either. No payload-derived string reaches a path, an argv, a prompt, a ref or a log format string. | `test_a_token_outside_the_vocabulary_is_ignored_not_obeyed` |
| **What may be read back** | The portable record is agent-writable, like every state file here. The frozen value is re-checked against `SESSION_PER_PR_MODES` before it is substituted, and `TmuxConfig.__post_init__` re-resolves it a second time, so a hand-edited fourth mode reaches neither the properties nor routing. | `test_a_work_item_with_no_usable_choice_routes_by_the_configured_default` (`"sometimes"`, `""`, `3`, absent) |
| **Blast radius** | The mode is resolved per work item from that work item's own record. A hostile or corrupt value in one record cannot change how another work item routes. | `test_one_work_items_choice_does_not_move_another_ones` |
| **Does it widen anything?** | No. The mode decides *routing*, never *authorization*. `always` still spawns only what `_endpoint_cwd` will give a working tree to (decision-092 D4 unchanged, `require_branch` unchanged), still under `maxConcurrentDispatches`, still only for an armed work item. The spawn-declined path and its `session.pr_session_declined` reasons are untouched. | existing `test_always_still_declines_the_session_when_there_is_no_checkout_for_it` |
| **Failure modes** | Every one lands on the operator's configured value: unreadable store (caught, warned, default), absent key, ambiguous ticks, unreadable checklist. Nothing raises on the routing path — a read failure must never cost a delivery. | `_tmux_for`'s `except`; `test_an_unchosen_or_ambiguous_answer_keeps_the_configured_default` |

## Denial-of-service consideration

A work item that selects `always` multiplies **its own** harness conversations. That is the
requested behaviour, it is bounded by `maxConcurrentDispatches` exactly as before, and it is
reachable only by an authorized human on an armed work item — the same gate that could
already set the operator's default to `always`. Widening *concurrency* under an existing
authorization is not a new privilege.

## Secrets

None read, stored, logged or moved. The one new log line names a work-item ref, an exception
string and a mode name.

## Verdict

No new attack surface beyond the two items above, both of which are validated against fixed
vocabularies on the way in and on the way out. No finding to carry forward.
