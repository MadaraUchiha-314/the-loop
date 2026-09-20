# bug: RoomPolicy's gate-collapse and operator-docs rules do not suppress live

From [`docs/reports/e2e-slack-test-2026-09-20.md`](../e2e-slack-test-2026-09-20.md) (N2),
the live validation run of the issue-393 room rework on the-loop 19.7.0.

## Seen

The rules exist and are unit-tested, but in the live room:

- **Each human gate was still announced three times** within seconds: the 📋
  `phase-approval-pending` digest with the Approve / Request changes buttons, a 🔨
  "*X* reached *gate*" line (`phase.progress`/`phase.started`), then a 💬
  "*gate* is ready for review" mirror (`comment.agent`). Only the first is
  actionable. 9 of the run's 31 bot messages were these duplicates.
- **The tmux cheat-sheet still posted to the room** (the session-started mirror
  with the attach table and shell block) — the operator-docs suppression did not
  fire.
- The endgame piled five messages into two minutes (🎉 at-complete, 🔨
  started-complete, ✅ completed-complete, the agent's ✅ summary, 🎉 closed); the
  `complete` node's own started/completed pair says nothing.

The transition-collapse and progress-edit rules DO work live (no mid-run
`phase.completed` lines; the six-node review chain rendered as one message edited
in place), so the wiring is sound — the failing rules are the ones keyed on
recognizing a gate's satellites and an operator-doc mirror.

## Root cause (found on the 2026-09-20 follow-up)

Three independent reasons the rules could not fire, all confirmed against the
runtime and the mirror path:

1. **The gate node emits `phase.progress`, not `phase.started`.** An approval node
   declares no `phase:` of its own and inherits its predecessor's, so entering it
   does not change the phase label and the runtime emits `phase.progress`.
   Gate-collapse only dropped `phase.started`, so the gate's lifecycle line was
   never a candidate to drop.
2. **The "ready for review" mirror carries no node.** `publish_comment` derives no
   `detail["node"]` from a mirrored `comment.agent`, so gate-collapse's node guard
   (`if node and gate_ts.get(node)`) was always false for it.
3. **`operatorDoc` was never set.** The rule read `event.detail["operatorDoc"]`,
   but nothing ever stamped it — the session-started cheat-sheet posts straight to
   GitHub and comes back as a plain mirror.

## Fix (branch `fix/n1-selection-grammar-refusal-reason`)

`RoomPolicy.decide` now: (1) collapses a `phase.progress` **and** `phase.started`
at a node with a live `gateTs`; (2) reads the gate node from the "ready for
review" mirror's own text ("**\<node\>** is ready for review") and matches it to a
pending gate, so the nodeless mirror is dropped for exactly the gate that is open;
(3) recognises the tmux cheat-sheet by its own lead ("started an interactive
session for" + "tmux attach -t") as operator docs. Plus an **endgame-collapse**
rule drops the terminal `complete`/`done` node's own phase pair (the empty
"started/completed phase *complete*" lines) — the dedicated `work-item-complete` /
`work-item.closed` events and the session's summary carry the end. Unit tests per
rule in `test_room_policy.py`.
