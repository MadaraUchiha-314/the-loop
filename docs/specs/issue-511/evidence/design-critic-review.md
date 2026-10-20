---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Design critic review: de-cluttering the control plane UI

## Design critic review

One round, the operator's cap (`criticReviewCount: 1`). The critic was codex, run with
`the-loop critic run codex --root <worktree> --cwd <worktree>` in 64 s against `5ca236f`,
reading the requirements, the design, the chosen Option C prototype and the components
the design changes. It found six issues. Four were fixed in the design and the prototype,
one was fixed by stating the claim's scope precisely, one was declined with the reason
recorded. The reply was posted before any file changed.

A first invocation without `--cwd` ran in the critic's default directory and reported
that the artifacts were absent; it produced no finding and is not counted as a round.

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | `codex/gpt-6.1-sol` | new findings (6) | **C1** (major) the health word, and the stream's fallen-back state, disappear with a collapsed sidebar, by default below 768 px → declined as a change: the footer is the word's home at 20.5.1 and at every option, the fallen-back state *is* the word (`degraded`), and R5.5 forbids a second home; the claim's scope is now stated in design.md § Error handling and the header signal is a named follow-up. **C2** (major) B and C drew the repository zero times by default, against R2.1 → fixed: the ref chip stays in the header meta at every level (design.md D11; inventory row 23; prototypes). **C3** (major) C's header verbs lost the visible "work item session" targeting on a PR selection → fixed: a `work item` kicker precedes the verbs on a PR selection (D9; row 64; prototype). **C4** (major) the Session details popover had no height bound or inner scroll → fixed: bounded to the viewport and scrolling inside (§ UI/UX accessibility; prototype; new 390 px capture with the popover open). **C5** (major) copy controls for session id, transcript and cwd are new controls under R5.5 → fixed for B and C: the values render in full inside the disclosure with no copy control; only the attach-command copy stays (D6; rows 53, 57, 59; Security design). **C6** (minor) row 61 restored at B what A removed → fixed with C2: `remove` at every level. | [findings and replies](https://github.com/MadaraUchiha-314/the-loop/pull/513#issuecomment-6295579545) |

The cap is one round, so no second critic round ran on the fixes. The design is not
locked by this node; the `design-approval` gate reads it with these findings resolved.
The critic's raw envelope is not committed (it carries the operator's local paths).
