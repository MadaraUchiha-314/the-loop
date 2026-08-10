# Evidence — the ticket's two symptoms, before and after

Work item: issue-199 · captured 2026-08-10 · no network, no credentials.

## What was run

The ticket's scenario, made offline and deterministic: a work item armed by **one**
comment carrying both the `the-loop contribute` keyword and the goal block, driven through
the same `GraphLink.on_spawn` the dispatcher calls after a successful spawn, against a
fake GitHub integration that serves the thread and records what the-loop posts.

```python
ARMING = (
    "the-loop contribute\n"
    "Goal: make the retry loop honour the configured backoff\n"
    "Success criteria:\n"
    "- [ ] the flaky-timeout test passes 50 consecutive runs\n"
)
...
link.on_spawn(WorkItemRef.parse("github:o/r#9"), str(root),
              session_id="s-1", runner="tmux", routed=Routed())
```

The "before" columns were produced by the same script against the pre-change
`cli/the_loop` (`git stash push -- cli/the_loop`), with the `routed=` argument dropped —
the parameter did not exist, which is itself the first half of the defect.

## Before — symptom 2: the arming comment reaches no gate

```text
pointer after the ONE arming comment: goal-definition
goal frozen: False

--- the phase-selection checklist it posted ---
(nothing posted)
```

The goal is stated, authorized, and sitting in the thread; the gate that would freeze it
is never evaluated. Nothing is posted, because `post-goal-request` correctly declines to
ask a question that is already answered — so the ticket goes quiet and the work item waits
for an unrelated event.

## Before — symptom 1: the surface row, once a later event moves it

Same run with one extra `rt.advance(...)` standing in for that unrelated later event:

```text
**Where should the outer loop happen?** This is not a phase — it is where the
requirements, design, testing plan and task list are iterated with you:

- [ ] `outer-loop-on-pull-request` — on a pull request in this repository.

Leave it unticked (the default) and they happen **on this work item**, here. Tick it
and they happen on a pull request instead. Either way the artifacts are committed files
linked from here, and each repository this work item contributes code to gets its own
pull request for the inner loop.

surface row present: True
```

…and the session's prompt block:

```text
  iterate the outer loop's artifacts on: this work item (the default) — comment on the
  ticket, and do not open a pull request just to carry the spec chain
```

Both describe an outer loop this work item does not have.

## After — one comment, and only answerable questions

```text
pointer after the ONE arming comment: phase-selection
goal frozen by: @owner

--- the phase-selection checklist it posted ---
🤖 _the-loop_ — **which phases does this work item need?**

Before the loop starts, tell it what this item actually needs. **Untick anything this
work item does not need — right here on this comment — then reply `the-loop execute`.**
The tick state at that moment is frozen and becomes the graph this item walks.

- [x] context-intake
- [x] scoped-plan
- [x] plan-approval
- [x] implementation
- [x] verification
- [x] self-review
- [x] critic-review
- [x] security-review
- [x] reviewer-briefing
- [x] human-approval

These phases always run and are not selectable — they are what keeps a lighter work item
honest:

- goal-definition

There is no outer loop to place on this one: the-loop is **contributing** to a work item
somebody else is already running, so its plan and its results are posted on this thread,
and the code it writes arrives as an ordinary pull request on the repository it targets.

A doc fix usually needs little more than implementation and verification; a feature
usually needs every phase. Reply `the-loop execute` with the boxes untouched to run the
full process.

You can also put the list in the reply itself — a checklist in the `the-loop execute`
comment wins over the boxes above. Either way the **authorization is your reply**: the
tick state is a proposal, and saying the keyword is what makes it yours.

surface row present: False
```

And the prompt the session is given:

```text
the-loop process state for issue-9:
  node: phase-selection (phase: phase-selection) — status: in-progress
  resume with: `/the-loop:contribute-to issue-9`
  iterate on: this work item (a contribution has no outer loop — post the plan and its
  results here, and open no pull request but the one carrying the code)
  when this node's work is done, run: `the-loop graph complete issue-9`
  (this block is the-loop's own state, not part of the event payload)
```

One comment; the goal frozen with its author's name on it; the pointer at
`phase-selection`; a checklist that asks only what this loop can answer.
