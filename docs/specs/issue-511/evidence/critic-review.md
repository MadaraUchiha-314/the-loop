---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Critic review: de-cluttering the control plane UI (Option C — Minimal)

> The `critic-review` node's proof — a different model/harness reading the diff. Same
> procedure as the self-review round (`reference/reviewing.md`); a round that could not
> run is recorded as **`unavailable`** with the cause and does NOT count toward the
> operator's `reviews.criticReviewCount`. One round, the operator's cap
> (`criticReviewCount: 1`). The reply was posted on PR #513 before any file changed; the
> critic's raw envelope is not committed (it carries the operator's local paths).

## Review cycles

| Round | Critic (`<harness>/<model>`) | Outcome | Findings → disposition | Link |
|-------|-----------------------------|---------|------------------------|------|
| 1 | `codex/gpt-6.1-sol`, run with `the-loop critic run codex --root <worktree> --cwd <worktree>` against `ec72366` in 70 s, reading the requirements, the design's C columns, the prototype, the diff, the tests and the evidence | new findings (4) | **1** (major) the empty-rail explanation ("no work-item state yet" / "no checkout recorded") became unreachable — *Full graph* rendered only for a non-empty rail and the strip nothing until expanded (R5.3) → fixed: for an empty rail the header meta draws the sentence in the control's slot, visible by default; `GraphStrip` drops its unreachable empty branch; two tests through `WorkItemDetail`. **2** (major) the Session details popover's `max-height: calc(100vh - 9rem)` assumed a desktop header; at 390 px the wrapped header can push a long body past the viewport, where the shell's `overflow-hidden` hides it → fixed: on toggle the popover measures its top and sets `max-height` to the space left below it (the class value is the fallback before the first measure); tested; the 390 px still recaptured. **3** (major) a blocked pointer node lost `aria-current` — the model marks the pointer `blocked` when its report blocks and the node marked only `current` (R6.2; older than this change) → fixed: `GraphStrip` takes the pointer's id and marks it the step whatever its state; tested with a blocked pointer beside another blocked node. **4** (minor) the verbs scenario claimed "pause, resume, stop and start" and exercised `pause` → fixed: parameterised over the three session states, every verb clicked and `controlSession` asserted with the work item's ref and instance; `evidence/integration.md` corrected. Security and docs: no finding. Fix commit follows the reply; lint, 372 tests and the build clean; JS 336 965 B, CSS 24 350 B. | [findings and replies](https://github.com/MadaraUchiha-314/the-loop/pull/513#issuecomment-6299742156) |

The cap is one round, so no second critic round ran on the fixes; the security review
reads them next.
