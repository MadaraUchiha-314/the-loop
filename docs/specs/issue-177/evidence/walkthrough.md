# Evidence: the motivating scenario, end-to-end

> A doc-fix work item walked through the rebuilt channel (owner review, PR #178): the
> `phase-selection` gate, an authorized reply, and the resulting skips. Run against the
> **shipped** `pdlc-work-item-loop` in a temp repository with a fake GitHub integration
> serving the ticket's comments — nothing here touched the network. (The one warning line
> the run emits is the best-effort `set-phase-label` hook failing against a fictitious
> repo and being ignored, exactly as designed.)

## 1. Entry posts the checklist, and the loop stops

```text
🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. Copy the list below
into a reply, **untick anything this work item does not need**, and add
`the-loop execute` to start.

```markdown
- [x] brainstorming
- [x] requirements-definition
- [x] requirements-approval
- [x] design
- [x] design-approval
- [x] tasks-breakdown
```

These phases always run and are not selectable — they are what keeps a lighter work
item honest:

- test-planning
- implementation
- verification
- self-review
- critic-review
- security-review
- evidence
- capability-docs
- reviewer-briefing
- human-approval

A doc fix usually needs none of the selectable phases; a feature usually needs all of
them. Reply with `the-loop execute` and no list to run the full process.

Only an authorized user's **reply** is read — ticking boxes on this comment does
nothing, because GitHub does not report who edited a comment.

<!-- the-loop:phase-selection -->

🤖 _the-loop, autonomous comment_
<!-- the-loop:agent-comment -->
```

The floor is named in full — every non-skippable node the item will walk, including the
review-chain nodes that carry no phase label.

## 2. An unauthorized reply changes nothing

A `@random` commenter unticking `design` and `test-planning` with `the-loop execute`:

```text
gate: wait; node: phase-selection; skips: {}
```

## 3. The authorized reply

```text
Doc fix — no spec chain needed.

- [ ] brainstorming
- [ ] requirements-definition
- [ ] requirements-approval
- [ ] design
- [ ] design-approval
- [ ] tasks-breakdown
- [ ] verification        ← deliberately unticked: a protected phase

the-loop execute
```

the-loop's confirmation:

```text
🤖 _the-loop_ — **phase selection recorded**

Skipping, as declared by @owner: `brainstorming`, `requirements-definition`,
`requirements-approval`, `design`, `design-approval`, `tasks-breakdown`

These are declarations, not verdicts: `the-loop check` reports each as *skipped by
declaration*, and every other phase still gates this work item.

**Refused** (these phases are not selectable and will run): `verification`

Starting the loop.

🤖 _the-loop, autonomous comment_
<!-- the-loop:agent-comment -->
```

The attempt on `verification` is refused and named — not silently honoured, and not
silently dropped either.

## 4. What was recorded

```json
"currentNode": "test-planning",
"skips": {
  "brainstorming":            {"via": "selection", "token": "brainstorming",            "by": "@owner", "reason": "", "at": "…"},
  "requirements-definition":  {"via": "selection", "token": "requirements-definition",  "by": "@owner", "reason": "", "at": "…"},
  "requirements-approval":    {"via": "selection", "token": "requirements-approval",    "by": "@owner", "reason": "", "at": "…"},
  "design":                   {"via": "selection", "token": "design",                   "by": "@owner", "reason": "", "at": "…"},
  "design-approval":          {"via": "selection", "token": "design-approval",          "by": "@owner", "reason": "", "at": "…"},
  "tasks-breakdown":          {"via": "selection", "token": "tasks-breakdown",          "by": "@owner", "reason": "", "at": "…"}
}
```

The pointer landed on **`test-planning`** — the first node of the never-skippable floor.
The spec-chain nodes were routed around without running a single hook (no
`loop:requirements-definition` label was ever applied; the only label sync attempted is
for the node actually entered).

## 5. `the-loop check --recompute`

```text
  ok     phase-selection
  --     brainstorming
         · skipped by declaration — via selection, token 'brainstorming', by @owner
  --     requirements-definition
         · skipped by declaration — via selection, token 'requirements-definition', by @owner
  --     requirements-approval
         · skipped by declaration — via selection, token 'requirements-approval', by @owner
  --     design
         · skipped by declaration — via selection, token 'design', by @owner
  BLOCK  test-planning
         · required artifact is missing (docs/specs/issue-999/testing-plan.md)
  --     design-approval
         · skipped by declaration — via selection, token 'design-approval', by @owner
  --     tasks-breakdown
         · skipped by declaration — via selection, token 'tasks-breakdown', by @owner
  ok     implementation
  BLOCK  verification
         · required artifact is missing (docs/specs/issue-999/testing-plan.md)
  BLOCK  self-review        · required section is missing: Review cycles …
  BLOCK  critic-review      · required section is missing: Review cycles …
  BLOCK  security-review    · required section is missing: Security review (gate) …
  BLOCK  evidence           · required section is missing: Final validation evidence …
  BLOCK  capability-docs    · required section is missing: Capability docs …
  BLOCK  reviewer-briefing  · required section is missing: Pull requests …
  wait   human-approval
```

Four things worth the reviewer's eye:

- Every skipped node reports **who and how**, never `pass` (R3.2).
- `phase-selection` reads **`ok`**, not `wait` — `check` passes no event by design, so
  the answered-ness is a durable decision in graph state. Self-review round 4 caught this:
  without it every work item would have reported as stuck at its first node forever.
- `test-planning` still **blocks** for its missing plan: even the lean lane keeps its
  proof (R1.6), and the phase the reply tried to untick is among the gates still red.
- `implementation` reads `ok` because its `tasks.md` re-gate treats the declared absence
  as planned (R3.4) and its other gates pass vacuously here; its proof burden sits with
  `verification` and the review chain, which are all still red until earned.

## 6. The tamper case: a forged skip on `security-review`

```text
  security-review status: block (not 'skip')
         · required section is missing: Security review (gate) (…/execution-log.md)
         · graph state declares a skip on this node, which is not skippable —
           the declaration is refused and has no effect
```

The hand-written declaration is inert — the node is evaluated on its artifacts alone —
and the report says so on the node it tried to touch (R3.3).
