---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#440"
---

<!-- Authored per the the-loop:writing skill. -->

# Self-review: the harness is a per-work-item choice at `phase-selection`

> The self review before human review
> ([`reference/reviewing.md`](../../../../skills/the-loop/reference/reviewing.md)). I read
> the branch diff adversarially, asking which launch could still reach a harness nobody
> chose, and what a reviewer would reject.

## Review cycles

### Cycle 1: the premise

1. **Found: only `claude` can host a session.** `cursor-agent` has no pre-assignable
   interactive session id, and there is no `codex` or `pi` adapter. Offering either would
   park a work item on a spawn that fails. So the offered set is declared ∩ hosting,
   derived from whether the adapter overrides `interactive_argv`, and the section needs
   two of them. On today's adapters it is dormant; the requirements say so up front and
   list the adapters as follow-ups.
2. **Found: the gate and the daemon disagreed on the default.** The gate honoured
   `harnesses[].default`, the daemon only `routing.defaultHarness`. With a harness
   choice, "the default" is named in the confirmation, so it has to be true.
   `modelchoice.default_harness` is now the one rule (R4).

### Cycle 2: the diff

1. **Every spawn seam.** `_spawn_for` resolves the harness after `on_arm` and hands it to
   `_spawn_tmux`, which now records, logs, announces and passes it to the `session_spawn`
   hook. Respawns (`_respawn_tmux`), PR endpoints (`_spawn_endpoint`) and `sessions
   restart` keep the recorded `session.harness`, which is correct: a conversation cannot
   be resumed in another harness (R3.4).
2. **Drift.** `_choice_drifted` resolves against the endpoint's own harness, so a frozen
   codex does not make a live claude session look drifted and respawn it on a
   conversation codex cannot resume (pinned by `test_a_live_session_keeps_its_harness`).
3. **Found and fixed: the union broke row order.** The first cut unioned model and effort
   rows in first-seen order across harnesses, so a probe refusal on one harness could
   reorder the checklist and put effort levels out of the loop's enum order. The union now
   follows the declared order (`test_the_union_keeps_the_declared_order`).
4. **One changed test.** `test_two_default_harnesses_is_an_error` now also draws the new
   non-hosting-default warning for `cursor`; the assertion filters to errors, which is
   what that test is about.
5. **Byte-identical checklist.** With fewer than two offered harnesses no row, heading or
   text changes (`test_one_harness_is_not_a_choice_and_changes_nothing`).

## Outcome

No open findings.
