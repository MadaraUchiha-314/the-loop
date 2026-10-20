---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#511"
---

# Documentation: de-cluttering the control plane UI (Option C — Minimal)

> The `capability-docs` node's proof, and it gates **both** sections (issue-174). A row
> names a **document**, never a token, a credential or an internal hostname: this tree is
> as public as the repository. Read at `verification` (T14) against the inventory's C
> column on 2026-10-20.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| [`docs/capabilities/control-plane.md`](../../../capabilities/control-plane.md) § Current behaviour | the "one screen of three columns" bullet became the C layout: two columns; the sidebar's two groups, one-line rows and their accessible name, the selected item's PRs, the finder behind a toggle; the main column's meta line (ref chip · phase chip · note · age · Full graph — the phase chip the one statement of the node), the one-session tab rule, the gate banner without the node, the composer's one hint; the session facts behind the Session details disclosure (bounded, closed by default) and the verbs in the header with the `work item` label; each fact drawn once; the standing sessions on the Standing surface alone; the sidebar's `<768 px` rule; the fail-closed sentence. The design-system sentence is unchanged (R4) | yes — an issue-511 row at the top of § History, linking the spec, decision-148 and the issue |

## Documentation

| Document | What changed |
|----------|--------------|
| [`ui/README.md`](../../../../ui/README.md) § Where the screens get their data | the one-screen paragraph describes two columns and the C bands — what each shows by default and what sits behind the Session details disclosure and Full graph; the Standing row of the reads table names `#/standing` rather than "a sidebar section of Work" |
| `ui/README.md` § Layout | `components/` names GraphStrip as the node row behind Full graph and `SessionFacts` as the module of the popover's facts and the header's `SessionControls`; `views/` says "the two columns" |
| `ui/README.md` § Screenshot evidence | notes the states the run now covers (Full graph, Session details, the finder) |
| `docs/specs/issue-511/` (requirements, design, testing plan, tasks, decision-148) | the spec chain itself; `design.md` § UI/UX design marks Option C selected |

Neither document describes the session panel column or the graph strip band as current.
