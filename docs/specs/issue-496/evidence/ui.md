---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#496"
---

# T5 / T9 — the Gateway card: vitest, screenshots beside the prototype, accessibility

> Testing plan rows T5 (UI / visual) and T9 (accessibility). Captured 2026-10-19 on the
> implementation at `feat/issue-496-gateway`.

## Command and outcome

```text
cd ui && NODE_OPTIONS=--no-experimental-webstorage ./node_modules/.bin/vitest run
Test Files 21 passed (21);Tests 330 passed (330);
```

(`bun run test` is the same command. Node 26 exposes an experimental `localStorage`
global that shadows jsdom's and is `undefined` without `--localstorage-file`; the
flag restores the environment every view test assumes. The one existing assertion
touched — the not-live pane counts three "has not answered" paragraphs now, the Gateway
card being the third.)

`src/views/InstanceDetail.test.tsx` carries six new cases: the five states from the
fixture (`DEMO_GATEWAY`) rendered through the manager transport, and the one vocabulary
(`gatewayWords`). `tsc --noEmit` and `oxlint --type-aware` are clean.

## The five states, implementation beside the locked prototype

Each implementation screenshot is the instance pane's Daemons and Gateway cards rendered
by the app (jsdom render → the built stylesheet → headless Chromium, 1000×900, light).
Each prototype screenshot is `design/gateway-card.html` driven to the same state.

| State | Implementation | Prototype | Words carried |
|-------|----------------|-----------|---------------|
| connected | [gateway-card-connected.png](ui/gateway-card-connected.png) | [prototype-connected.png](ui/prototype-connected.png) | `connected · long-poll`; url, polling as, since · committed seq, gateway health; the queue table by subject and role; Daemons rows `off · gateway configured` |
| connecting | [gateway-card-connecting.png](ui/gateway-card-connecting.png) | [prototype-connecting.png](ui/prototype-connecting.png) | `connecting · attempt 3`; no queue |
| refused | [gateway-card-refused.png](ui/gateway-card-refused.png) | [prototype-refused.png](ui/prototype-refused.png) | `refused · duplicate instance (409)`; the notice names the peer holding the name and the remedy |
| unreachable | [gateway-card-unreachable.png](ui/gateway-card-unreachable.png) | [prototype-unreachable.png](ui/prototype-unreachable.png) | `unreachable · retrying`; the notice says it does not fall back |
| not configured | [gateway-card-none.png](ui/gateway-card-none.png) | [prototype-none.png](ui/prototype-none.png) | `not configured`; the Daemons rows keep their verbs |

Differences from the prototype, on purpose: the implementation shows the backlog and
oldest-uncommitted age against the first subject row only (the queue is one per
instance, so per-subject depth is not a fact the API has), and the gateway-health line
counts running ingresses rather than "2 pollers".

## T9 — accessibility

- The state is carried by words next to a decorative dot: `StatusDot` renders with
  `aria-hidden`, and the connected test asserts the words are found by text.
- The queue table has an accessible name — `getByRole("table", { name: "This instance's
  queue, by subject" })` — and column headers.
- The refused and unreachable notices are plain text in `role="alert"` regions, asserted
  by role in the tests.
- Keyboard pass (manual, 2026-10-19): with the card rendered in the built app, Tab reaches
  the Daemons verbs and the instance's Restart control in order; the card itself holds no
  interactive element, so nothing is skipped or trapped; the table reads row by row.
