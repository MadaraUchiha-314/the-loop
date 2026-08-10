# Evidence: the opt-in phase, walked both ways (issue-188)

Manual exploratory verification (T11) against the **shipped** outer loop — not a fixture of
it. A scratch work item (`issue-999`) with an empty spec folder is evaluated twice: once
with nothing selected, once with `design-critic-review` selected the way the gate records
it.

## 1. The shipped graph shows the node, and how it is marked

```text
$ uv run the-loop graph show
graph v1, start: phase-selection
  phase-selection  [required, human]
      --selected--> brainstorming
  …
  design  [skippable]
      --skipped--> design-critic-review
      --pass--> design-critic-review
  design-critic-review  [opt-in]
      --skipped--> test-planning
      --pass--> test-planning
  test-planning  [skippable]
      --skipped--> design-approval
      --pass--> design-approval
  …
```

`[opt-in]` rather than `[skippable]`: the two share a mechanism, but only one of them runs
by default, and printing the weaker word would read as on-by-default.

## 2. The checklist the gate posts

Rendered from the shipped graph through `post-phase-selection`'s own body builder
(abridged — the default-on rows and the surface row are unchanged):

```text
🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. **Untick anything this
work item does not need, tick anything optional it does want — right here on this
comment — then reply `the-loop execute`.** …

- [x] brainstorming
- [x] requirements-definition
…
- [x] human-approval

**Optional phases — these do NOT run unless you tick them.** They are offered, not planned:

- [ ] design-critic-review — a different model/harness reviews the LOCKED design.md
      against the requirements, before the testing plan and the task DAG are derived from it

**Every phase of this loop is selectable — including the reviews, the security review and
the approval gate.** …

A doc fix usually needs little more than implementation and verification; a feature usually
needs every phase. Reply `the-loop execute` with the boxes untouched to run the full
process — every phase above that is already ticked, and none of the optional ones.
```

## 3. Nobody selected it — routed around, and reported as *not selected*

```text
$ the-loop check issue-999 --recompute
  BLOCK  design
         · required artifact is missing (docs/specs/issue-999/design.md)
  SKIP   design-critic-review
         · not selected — an opt-in phase, off unless it is ticked at `phase-selection`
  BLOCK  test-planning
         · required artifact is missing (docs/specs/issue-999/testing-plan.md)
```

No declaration exists in `graph-state.json` — `"skips": {}` — and the node is still not
walked. This is also the pre-issue-188 work item's path: a state file that never heard of
the node skips it rather than blocking on it.

## 4. An authorized user ticked it — walked, and gating like any other node

After the gate records `optIns["design-critic-review"] = {via: selection, by:
@MadaraUchiha-314, …}`:

```text
$ the-loop check issue-999 --recompute
  BLOCK  design
         · required artifact is missing (docs/specs/issue-999/design.md)
  BLOCK  design-critic-review
         · required artifact is missing (docs/specs/issue-999/execution-log.md)
  BLOCK  test-planning
         · required artifact is missing (docs/specs/issue-999/testing-plan.md)
```

The node now has a real gate over the execution log, and it blocks — a selected phase is an
ordinary phase.

## 5. What the state file records

```json
{
  "workItem": "issue-999",
  "skips": {},
  "optIns": {
    "design-critic-review": {
      "via": "selection",
      "token": "design-critic-review",
      "by": "@MadaraUchiha-314",
      "at": "2026-08-10T12:00:00+00:00"
    }
  },
  "surface": ""
}
```

A selection carries the same provenance shape a declared skip does — who, through which
channel, when — because it is the same kind of fact.

## 6. This work item's own report

```text
$ uv run the-loop check issue-188
issue-188: UNMET (at phase-selection)
  WAIT   phase-selection
         · waiting for an authorized user to choose the phases and reply `the-loop execute`
  ····   11 node(s) not reached yet
```

Its own selection was never posted on the ticket (this work item was driven directly from a
cloud session on the owner's assignment, recorded in `execution-log.md`), so its pointer is
honestly still at the gate.
