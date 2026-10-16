# Learning 009: "Nothing to approve" must not be something an agent can arrange

- **Date:** 2026-10-16
- **Source:** system-feedback (self-review and critic review)
- **Work item:** issue-494

## What happened

`brainstorm-approval` follows an optional node, so the gate needed a rule for when
there is no brainstorm. Three review rounds each hit a different edge of "absent":

- **T3 (verification).** `check --recompute` scores every node in declaration order
  instead of walking edges. With no brainstorm, the gate read as an unmet `wait`.
- **S1 → S2 (self-review).** The first fix let a gate with a missing artifact pass on
  `pass`. That turned "delete `brainstorm.md`" into a way past a human: at the gate,
  and back at `brainstorming` after changes-requested.
- **C1 (critic).** A declared-skipped `brainstorming` with a stray file on disk
  reopened the gate under `--recompute`.

## Learning

At a human gate, absence of the subject has two meanings that look identical on disk:
*never written* (nothing to approve) and *removed* (an attempt to skip the human).
Only the work item's history tells them apart. So the "nothing to approve" route must
depend on a fact the agent cannot create by deleting a file: here, whether the gate
was ever entered. And a fix that makes a gate *pass* in some case deserves the
bypass question before it lands: "can the agent bring this case about?"

## Action

- `HookContext.visited` carries the nodes a work item entered. `whenPresent` and
  `absentOutcome` (with `gate:`) block once the gate was entered, and the gate has no
  `pass` edge (`cli/the_loop/graph/hooks/feedback.py`, `artifacts.py`).
- When adding a gate-skipping condition, write the negative test where the agent
  produces that condition itself.
