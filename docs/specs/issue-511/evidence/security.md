---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Security tests (T8): de-cluttering the control plane UI

> The two abuse cases of `design.md` § Security design and the fail-closed list of the
> requirements, as tests; plus the grep for HTML-injecting calls. Run at `verification`
> on 2026-10-20, inside `cd ui && bun run test` (all passing).

## Abuse case 1 — markup in untrusted text stays text in every relocated position

| Position | Test | Asserts |
|---|---|---|
| the one-line row and its `aria-label` | `Sidebar.test.tsx` "abuse case 1: a title with markup renders as text…" | title `<b>x</b><img src=x onerror="alert(1)">` is the row's text and name; `row.querySelector("b, img")` is null |
| the header title, the phase chip, the note, the gate banner's reason | `WorkItemDetail.test.tsx` "keeps markup in the title, the node name and the note as text" | heading `textContent` equals the input; `**n**<i>x</i>` is text; no `b`, `i`, `img` or `strong` element in the header or the banner |
| the Session details popover | `SessionFacts.test.tsx` "abuse case 2 …" (same fixture covers both cases) | cwd, session id, harness and the attach command render their markup as text; no element created |
| the trace | `Transcript.test.tsx` "renders attacker-shaped tool text as text, not markup" (unchanged) | `renderInline` still emits text nodes inside `strong` / `code` |

## Abuse case 2 — content behind a disclosure renders from the typed record

`SessionFacts.test.tsx` passes a `WorkItemView` whose `session.cwd`, `session.harnessSessionId`
and `session.harness` carry markup, and asserts each `KV` row's `textContent` equals the
field byte for byte — the popover renders `SessionEndpoint` / `PullRequestView` fields
through the same `KV` rows as 20.5.1's panel, never a string assembled in the DOM.

## Fail-closed — the warnings survive the de-cluttering

| Signal | Test |
|---|---|
| the demo banner | `App.test.tsx` "says outright that the data is not real" |
| the connection banner (`role="alert"`) | `App.test.tsx` "keeps the connection banner above the columns when the service cannot be reached" (a transport whose every call rejects) |
| the `degraded` health word | `Sidebar.test.tsx` "reads degraded in the footer when a daemon is stopped"; the fleet case in "lists each instance … reads degraded for a down member" |
| the blocked composer's reason | `Transcript.test.tsx` (paused / closed / none, the reason as the one hint); `App.test.tsx` (#187: "No session is registered…") |

## Grep

```text
grep -rn "dangerouslySetInnerHTML\|innerHTML\|eval(" ui/src ui/index.html
(no matches)
```

No copy control was added (the two clipboard writes are 20.5.1's), no route, request,
setting or dependency — the diff of `ui/src/api`, `ui/src/state` and `ui/src/demo`
against `origin/main` is empty ([`build.md`](build.md)).
