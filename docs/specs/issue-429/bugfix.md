---
type: bugfix
phase: requirements-definition
workItem: "github:MadaraUchiha-314/the-loop#429"
status: in-review            # draft | in-review | approved — tier 3: a human approves the PR
approvedBy: []
severity: high
collaborators: [engineer]
overrides: {}
riskTier: 3                  # changes what the process-enforcement gate blocks on; one additive report field; no grant, schema or state-file change
---

<!-- Authored per the the-loop:writing skill. -->

# Bugfix spec: the stop gate blocks on a node the work item never entered

> Phase 1 of 4 (bugfix → design → testing plan → tasks). Source:
> [issue-429](https://github.com/MadaraUchiha-314/the-loop/issues/429).

## Summary

A daemon-spawned session deadlocks. After every turn the harness stop gate
(`hooks/the-loop-gate.py`) blocks the stop and orders the agent to write an artifact
for a phase the work item has not started. The ticket's case: an item parked at
`phase-selection`, told on every turn to write `design.md`. The agent cannot, the
gate fires again, and the item goes quiet.

The gate asks `the-loop check <item> --format json --recompute` where the item is, and
blocks when the node at `currentNode` is `block`. **Under `--recompute`, `currentNode`
is not where the item is.** It is the first node the *artifacts* leave unmet
(`Runtime._first_unmet`). Whenever every node before some node `N` passes on the
artifacts, but nothing has advanced the item into `N`, the recomputed position is `N`
while the recorded pointer is still behind it. The gate then demands `N`'s artifact.

The ticket attributed this to `current: null`. On `main` (19.13.0) the report never
carries a null `currentNode` for a repository that resolves, and the gate reads
`currentNode`, not `current`. The mechanism is the one above, and it matches the
ticket's observation exactly: `check` (no flag, the pointer) says `phase-selection`;
the gate (`--recompute`, the artifacts) says `design`. Both of the ticket's suggested
fixes still apply in substance, and both are taken (see [Requirements](#requirements) and [`design.md`](design.md)).

## Steps to reproduce

On `main` at `48cb8e6`, in any git checkout:

```console
$ mkdir -p docs/specs/issue-1
$ cat > docs/specs/issue-1/work-item-state.json <<'EOF'
{"workItem": "issue-1", "currentNode": "phase-selection",
 "decisions": {"phase-selection": {"at": "2026-09-25T00:00:00Z"}},
 "parked": {"node": "phase-selection", "reason": "awaiting a human"},
 "skips": {"brainstorming": {"by": "op"}, "requirements-definition": {"by": "op"},
           "requirements-approval": {"by": "op"}}}
EOF
$ the-loop check issue-1
issue-1: ok (at phase-selection)
$ the-loop check issue-1 --recompute
issue-1: UNMET (at design)
  BLOCK  design
         · required artifact is missing (docs/specs/issue-1/design.md)
$ THE_LOOP_WORK_ITEM=issue-1 python3 hooks/the-loop-gate.py claude; echo $?
the-loop: this step is not complete.
  · required artifact is missing (docs/specs/issue-1/design.md)

Fix the above, then finish. (attempt 1/3)
2
```

The state is the one a selection leaves when it has been recorded but the item not yet
walked on. It does not need to be exactly this one. Any recorded pointer behind the
first node the artifacts leave unmet reproduces it.

## Expected vs actual

| | Expected | Actual |
|---|---|---|
| the gate, item parked at `phase-selection` | lets the turn end (nothing the agent can do) | exit 2, demands `design.md` |
| the gate, item at `design`, `design.md` missing | exit 2, demands `design.md` | same (correct today) |
| the gate, no position it can resolve | lets the turn end | lets the turn end, but only by accident: no explicit rule |
| `check --recompute`, the two positions differ | says both | prints only the derived one; `check` and the gate read as contradicting each other |

## Root cause

`hooks/the-loop-gate.py` `blocking_node` bounds the gate by `currentNode`, and the gate
always runs `check --recompute` (`run_check`). `Runtime.status(recompute=True)` sets
`current = self._first_unmet(reports) or current`. So the gate asks about the first
unmet node **anywhere in the graph**, not the first unmet node the item has reached.

Its docstring argued this on purpose, for two reasons (issue-109):

1. **Trust.** Work-item state is agent-writable, so a gate must not take a *verdict*
   from it. That still holds. Verdicts are the recomputed ones.
2. **The inert case.** A work item whose pointer was never advanced sits at the start
   node, so a pointer-bounded gate would never fire. This no longer holds.
   - Since issue-177 the start node is `phase-selection`, a human gate that `wait`s
     until a selection is recorded.
   - Since issue-370 `THE_LOOP_WORK_ITEM` is set only in sessions the daemon spawns,
     and the daemon is what advances the pointer.
   - So the case the derived position was meant to cover is exactly the case this
     ticket reports as a bug: an item the daemon has not advanced.

The ticket's other failure, a report that cannot say where the item is, has no explicit
rule. `blocking_node` returns `None` for a null `currentNode` only because nothing in
`nodes` matches `None`. The ticket's fix 2 asks for that to be deliberate.

## Requirements

### Requirement 1: the gate asks only about nodes the item has reached

1. WHEN the harness stop gate evaluates a work item THEN it SHALL block only on the
   first node that is not satisfied **at or before the recorded pointer**, and only when
   that node's status is `block`.
2. The gate SHALL take every node's verdict from the recomputed report. The pointer
   bounds *which* nodes are asked about and never decides whether one passed.
3. WHEN the pointer is ahead of an unmet node THEN the gate SHALL still block on that
   node. A pointer moved forward hides nothing behind it.

### Requirement 2: a gate that cannot tell where the item is lets the turn end

1. IF the report has no `currentNode`, or a `currentNode` that names no node in it,
   THEN the gate SHALL let the turn end.
2. IF the report's `pointer` is empty (no state file found, or the item never entered
   the graph) or names no node in the report THEN the gate SHALL let the turn end.
3. WHEN the report carries no `pointer` key (a CLI older than this change) THEN the gate
   SHALL fall back to `currentNode` as the bound, its behaviour before this change.

### Requirement 3: `check` reports both positions

1. Every resolving `check` report (CLI JSON, `POST /graph/check`, the
   `check_work_item` MCP tool) SHALL carry `pointer`: the node work-item state records,
   `""` when none was found. This holds in both modes.
2. `currentNode` SHALL keep its meaning in both modes. CI's
   `check --recompute --fail-on …` reads no pointer and is unchanged.
3. WHEN `check --recompute` prints a table and a state file was found whose pointer
   differs from the derived position THEN the `state:` line SHALL name the pointer.
4. issue-238's position-unknown answer SHALL keep its six keys.

## Security considerations

- **The gate now reads one fact from agent-writable state: the position.**
  - Moving the pointer *forward* gains nothing (R1.3).
  - Moving it *backward* lets an agent end turns while later nodes are unmet. But those
    are nodes the item has not officially entered, and entering them takes an `advance`
    that evaluates their gates, or a recorded `force`.
  - The stop gate is a nudge, not the merge boundary. CI's `check --recompute` reads no
    pointer and still gates the merge. That residual is accepted here, and the
    attempt cap already bounds the gate to three nudges per node.
- No new input, route, credential, subprocess or file write. `pointer` is an extra key
  on an existing read-only response, holding a value the same response already exposed
  through `currentNode` in non-recompute mode.

## Out of scope

- A pointer the operator `force`d past an unmet node still gets that node demanded, as
  today. That is a finding, not an invention: the item did walk past it.
- The ticket's "fall back to the graph state the service maintains under the state
  root". The pointer lives only in the repository's `work-item-state.json` (the state
  layout's `pointer` attribute, `cli/the_loop/state.py`). There is no second copy
  to fall back to. Issue-396 already resolves the checkout through the session
  registry when the gate's working directory does not hold the item.
