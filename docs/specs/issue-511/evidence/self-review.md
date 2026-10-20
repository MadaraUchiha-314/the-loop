---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Self-review: de-cluttering the control plane UI (Option C — Minimal)

> The `self-review` node's proof. One row per round, per `reference/reviewing.md`:
> attribution prefix, own-comment marker, reply-first-then-fix, stop on zero new
> findings, escalate on a repeated finding. Two rounds, the operator's cap
> (`selfReviewCount: 2`); each review was posted on PR #513 before its fixes were made.

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition | Link |
|-------|----------|---------|------------------------|------|
| 1 | self (`claude/claude-fable-5-1`), the implementation at `5f2efdb` against the design's C columns, the inventory and § Security design | new findings (4) | **1** (major) dead code the panel's removal left behind — `SessionAside`, `HeaderBar`'s open-panel path, `Chrome.asideOpen` / `onOpenAside`, `Panels.asideOpen` and the 1280 px initial state, three orphan icons → fixed: removed; the module is `SessionFacts.tsx`. **2** (minor) `ChatBar`'s unread `tmuxTarget` prop → fixed: dropped. **3** (minor) the sidebar re-shaped `{ view, inner }` entries just to sort → fixed: `byActivity` comparator shared with `sortByActivity`. **4** (nit) a title-less row fell back to the short ref beside `#n` → fixed: the repository. Fix commit `ac66b81`; lint, 366 tests and build clean, bundle smaller again. | [round 1](https://github.com/MadaraUchiha-314/the-loop/pull/513#issuecomment-6299606552) |
| 2 | self, the code at `ac66b81` | new findings (1, nit) — cap reached | **1** (nit) the header meta drew the parked/blocked note without the `·` separator the prototype puts before it → fixed. Round 1's four findings verified closed; no repeat. | [round 2](https://github.com/MadaraUchiha-314/the-loop/pull/513#issuecomment-6299655437) |

Accepted as designed, recorded rather than fixed: `compactRail` / `StripEntry` stay
exported with only their test as a reader (the design keeps them); the Session details
popover closes from its summary, like the health popover (a native `<details>`).
