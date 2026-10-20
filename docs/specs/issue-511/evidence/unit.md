---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Unit tests (T1): de-cluttering the control plane UI

> The pure helpers the C layout rests on, asserted without a DOM. Run at
> `verification` on 2026-10-20 as part of `cd ui && bun run test`
> (22 files, 366 tests, all passing — the full summary is in
> [`integration.md`](integration.md)).

| Suite | Tests | What it proves |
|---|---|---|
| `ui/src/views/grouping.test.ts` | 14 (3 new) | `SIDEBAR_GROUPS_MINIMAL` is Needs you · Everything else, in that order; `minimalGroup` folds In flight, Shipped and Idle into Everything else while `sidebarGroup` still answers four ways (#205 and #178 needs-you; #209 in-flight, #181 shipped, #198 idle); `sortByActivity` orders by `lastActivity` descending and leaves its input alone; `filterViews`, `itemStatus` and the ended-item rules unchanged |
| `ui/src/views/WorkItemDetail.test.tsx` § railNote | 2 (new) | a parked item reads `parked — awaiting a human` and never contains the node id; an item that needs nothing reads `""` |
| `ui/src/components/GraphStrip.test.tsx` § compactRail / railLabel | 4 (unchanged) | `compactRail` and `railLabel` keep their shape — `railLabel` still feeds the PR tab's `inner loop` fact |
| `ui/src/components/Transcript.test.tsx` § chatBlocked (via ChatBar) | 3 (unchanged) | the blocked reason per session state |
| `ui/src/api/model.test.ts` § rowFlag | unchanged | the flag and its urgency per view |

Red → green: each new test was committed failing against the 20.5.1 helper and passing
after the change (commits `ef160f9`, `43533bc`).
