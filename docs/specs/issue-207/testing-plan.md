---
type: testing-plan
phase: test-planning
workItem: issue-207
status: draft
approvedBy: []
overrides: {}
---

# Testing plan: a control-plane dashboard over `/api/v1`

> Derived from [`requirements.md`](requirements.md) and [`design.md`](design.md).
> Authored at `test-planning`, completed at `verification`.

## Test matrix

| # | Type | Applies? | Scope / what it proves | Where it runs |
|---|------|----------|------------------------|---------------|
| T1 | Unit | yes | The join in `model.ts`: ref parsing incl. GHE hosts, spec-id derivation, positional rail reads, the four-record union, `prRepo` qualification, the inbox union, relative times | `cd ui && bun run test src/api/model.test.ts` |
| T2 | Unit | yes | The transport in `client.ts`: refs travel as query parameters, list parameters repeat, `graph/check` posts `prRepo` defaulted, a cross-origin `TypeError` becomes `kind: "network"` with the tunnel advice, FastAPI's `detail` survives a 4xx, a non-JSON error body falls back to the status line | `cd ui && bun run test src/api/client.test.ts` |
| T3 | Contract (OpenAPI) | partial — see note | The client's routes, methods and body keys are written against `docs/api-specs/openapi/the-loop.v1.yaml`, and T2 pins them. A generated-client parity test is **not** added: the contract types most responses as `additionalProperties: true`, so generation would produce `Record<string, unknown>` and prove nothing the hand-written types do not | `cd ui && bun run test src/api/client.test.ts` |
| T4 | End-to-end | yes (component-level) | The whole React layer against the demo transport: the board lists all eight items with positions, the parked item is flagged, a row opens its detail with both PRs on their own inner loops, the attention tab shows the union, a deep link to an unknown ref degrades | `cd ui && bun run test src/App.test.tsx` |
| T5 | UI / visual | manual | The rendered result against the approved design: tokens, blueprint frames, node rails, table rhythm. No screenshot baseline — the design system is vendored verbatim, so a pixel baseline would test the CSS export rather than this app | reviewer, `bun run dev` |
| T6 | Snapshot | n/a — the interesting output is the join, asserted structurally in T1; a DOM snapshot would fail on every copy edit and prove nothing about behaviour | | |
| T7 | Performance / load | yes (by construction, asserted in review) | NFR1: the graph round is a four-worker pool over N jobs, and the flat lists render before it starts. Pinned by reading `GRAPH_CONCURRENCY` and the two `setViews` calls rather than by a timing test, which would be flaky and machine-dependent | code review of `useControlPlane.ts` |
| T8 | Security / abuse case | yes | The five abuse cases of `requirements.md`: the posture note is present and no path proposes `service.exposed: true`; no `dangerouslySetInnerHTML`/`eval`/dynamic import anywhere in `src/`; the base URL is always visible; corrupt `localStorage` degrades field by field; demo mode banners on every screen | `cd ui && bun run test src/state/settings.test.ts` + the grep in T8b |
| T8b | Security / static | yes | `grep -rn "dangerouslySetInnerHTML\|eval(\|new Function\|innerHTML" ui/src` returns nothing | CI (`bun run lint` config forbids none of these directly — run as a review step) |
| T9 | Accessibility | yes (partial) | NFR4: every control is a real `button`/`a`/`input` with an accessible name — T4 selects **only** by role and accessible name, so a control that lost its name fails the suite. The pulse is suppressed under `prefers-reduced-motion` by a media query. A full audit (contrast, focus order under assistive tech) is **not** in this pass | `cd ui && bun run test src/App.test.tsx` |
| T10 | Migration / upgrade | yes (as a **non**-migration) | Nothing existing changes shape: no schema, no record, no route. The settings store is versioned (`…:v1`) from birth, and an absent store is the default path | T1/T8 |
| T11 | Manual exploratory | yes | The one thing no automated test here covers: the app against a **real** service. Start `the-loop service start`, run `bun run dev`, confirm the board, a graph rail, a pause/resume round trip and the event log | operator, before merge |

**On T3.** The strongest available contract check is that the parity test already in the
repo (`cli/tests/test_api_contract_parity.py`) keeps the served schema equal to the
authored one; this client is written against the same file. If a future work item gives
the API real response models, generating types from the contract becomes worthwhile and
should replace `types.ts`.

## Scenarios & requirement trace

| Row | Requirement(s) | Scenario / case |
|-----|----------------|-----------------|
| T1 | R1.1 | a work item with no session, and a session with no portable record, both survive the union |
| T1 | R1.2 | the report's `currentNode` and progress reach the row |
| T1 | R1.3 | with no report, the rail comes from the record's frozen nodes and the row still exists |
| T1 | R1.5 | a parked gate outranks a paused session in the row flag; a healthy item has no flag |
| T1 | R2.1 | passed / current / skipped / blocked are distinguished; a blocked pointer is not drawn as current |
| T1 | R2.3 | `prRepo` is `""` for a same-repo PR and `owner/repo` for one elsewhere |
| T1 | R2.4 | the Claude Code transcript path is derived from `cwd` + session id; cursor yields null |
| T1 | R4.1, R4.2, R4.3 | the inbox is `/attention` ∪ parked gates, urgent first |
| T2 | R3.1, R3.2 | the control and gate calls hit the documented routes with the documented bodies |
| T2 | R3.3 | the service's `detail` is what the operator is shown |
| T2 | R5.4 | a cross-origin `TypeError` produces the tunnel/gateway advice |
| T4 | R1.1, R1.2, R1.5 | eight items listed, positions arrive, the parked one is flagged |
| T4 | R2.1, R2.2 | the detail screen shows the outer loop and one card per PR |
| T4 | R2.5 | the reply box is present, **disabled**, and its title names `POST /api/v1/sessions/reply`; the trace says outright that turns and tool calls are not served |
| T4 | R5.6 | a deep link to a ref this service does not have degrades to a message, not a crash |
| T8 | R5.5 / abuse 5 | demo mode banners; verbs stay in memory |
| T8 | abuse 4 | a store holding `{not json`, a bad `mode`, a string `pollSeconds`, an absurd interval |
| T8 | R5.2, R5.3 | the base URL round-trips through storage and is normalized |
| T11 | R1.2, R3.1, R3.4 | against a real service: positions render, a pause round-trips, the board re-fetches |

## Coverage gaps accepted in this pass

Stated rather than left implicit:

- **No test drives a real service.** T11 is manual. An integration test would need a
  running daemon, a checkout and a tmux session in CI; the seam is instead pinned at the
  HTTP boundary (T2) against the authored contract.
- **No visual baseline** (T5) and **no full accessibility audit** (T9).
- **NFR1 is reviewed, not measured** (T7).
