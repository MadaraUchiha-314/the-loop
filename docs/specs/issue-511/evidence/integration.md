---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Integration and accessibility tests (T2, T9): de-cluttering the control plane UI

> The React suites on the demo transport, asserting every inventory verdict for
> Option C, every preserved action and state, and the roles and names the quieter
> screen keeps. Run at `verification` on 2026-10-20.

## Run

```text
cd ui && bun run test
 Test Files  22 passed (22)
      Tests  366 passed (366)      (372 after the self-review and critic rounds added tests)
   Duration  12.74s
```

On this workstation Node is 26.7, whose experimental global `localStorage` shadows
jsdom's and breaks the suites' `localStorage.clear()`; the run above sets
`NODE_OPTIONS=--no-experimental-webstorage`. CI runs Node 22, where the flag is neither
needed nor accepted — the code and the tests are unchanged either way.

## Scenarios (Gherkin titles from `testing-plan.md`) → suite

| Scenario | Suite | Row |
|---|---|---|
| a sidebar row is one line carrying the number, the title and the urgent flag, and its accessible name carries all three | `Sidebar.test.tsx` | T2, T9 |
| a paused, merged or closed item shows no flag on its row | `Sidebar.test.tsx` | T2 |
| pull request rows nest only under the selected item (and carry no age) | `Sidebar.test.tsx`, `App.test.tsx` | T2 |
| only the Needs you group shows a count | `Sidebar.test.tsx` | T2 |
| the Standing group does not render in the sidebar and the Standing surface still lists every standing session | `Sidebar.test.tsx`, `Standing.test.tsx` (unchanged, 8 passing) | T2 |
| the search box and the instance filter appear behind the search toggle, which carries aria-expanded | `Sidebar.test.tsx`, `App.test.tsx` | T2, T9 |
| an instance filter renders on a fleet and not on a worker | `Sidebar.test.tsx` | T2 |
| the header meta is the ref chip, the phase chip, the note and the age — the repository line and the instance chip are gone | `App.test.tsx` | T2 |
| the current node is written once — the phase chip — and the gate banner says Human gate without the node | `App.test.tsx` | T2 |
| Full graph in the header meta reveals the node row and Collapse graph hides it | `App.test.tsx`, `GraphStrip.test.tsx` | T2, T9 |
| the session tab bar renders only when the item has more than one session | `WorkItemDetail.test.tsx` | T2 |
| the tab bar carries no session tally and the composer carries no delivery hint | `WorkItemDetail.test.tsx`, `Transcript.test.tsx` | T2 |
| pause, resume, stop and start render in the header and call controlSession with the work item's ref — parameterised over an active, a paused and a session-less item, every verb clicked (critic round 1) | `SessionFacts.test.tsx` | T2 |
| with a PR session selected the verbs carry a visible work item label and still target the work item | `SessionFacts.test.tsx` | T2 |
| Session details is a closed details element whose body shows harness, status, started, session id, transcript path, cwd, the attach command and Open on GitHub in full | `SessionFacts.test.tsx` | T2, T9 |
| copy ref and copy attach command write the clipboard | `SessionFacts.test.tsx` | T2 |
| loading, empty board, missing deep link, no-transcript fallback, truncated tail and blocked composer render their sentences in the C layout | `App.test.tsx`, `Sidebar.test.tsx`, `WorkItemDetail.test.tsx` | T2 |
| every hash the 20.5.1 app parses lands on the same surface | `App.test.tsx` (`#/`, `#/item/…`, `#/standing`, `#/settings`, `#/instances`, `#/events`, `#/sessions/…`), `route.test.ts` (unchanged, 21 passing) | T2 |
| below 768 px the sidebar starts closed and reopens from the header; Session details starts closed | `App.test.tsx` | T2, T9 |
| the trace keeps `role="log"`, its name and `tabindex`; the Verbose switch answers Enter and Space | `WorkItemDetail.test.tsx`, `App.test.tsx` (unchanged) | T9 |
| the theme toggle, the gate approval and the question + reply still work in the C layout | `App.test.tsx` (unchanged scenarios) | T2 |
| an empty rail still explains itself — "no work-item state yet" with a checkout, "no checkout recorded" without — in the Full graph slot (critic round 1) | `WorkItemDetail.test.tsx` | T2 |
| the Session details popover is bounded to the space left below it when it opens (critic round 1) | `WorkItemDetail.test.tsx` | T9 |
| a blocked pointer node is still the step (`aria-current`), and only it (critic round 1) | `GraphStrip.test.tsx` | T9 |

New or changed test files: `SessionFacts.test.tsx` (new, 7), `Sidebar.test.tsx` (20, 12 new),
`App.test.tsx` (21, 6 new or re-pointed), `WorkItemDetail.test.tsx` (12, 7 new),
`GraphStrip.test.tsx` (7, 3 rewritten), `Transcript.test.tsx` (19, 1 new),
`grouping.test.ts` (14, 3 new). Every other suite is byte-identical to the branch point.
