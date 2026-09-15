---
type: evidence
record: final-validation
workItem: "github:MadaraUchiha-314/the-loop#368"
---

# Final validation: one rule for where a work item's attributes live

## Final validation evidence

Every requirement, and what proves it. The commands are in `testing-plan.md`'s results
table; the whole suite is **3711 passed, 1 skipped**, with ruff, ruff format, pyright,
the config validator and markdownlint over every `**/*.md` all clean.

| Requirement | Met by | Proof |
|---|---|---|
| R1 — one rule, written down and enforced | `state.ATTRIBUTES` + `ATTRIBUTE_KINDS`, the rule's four assertions | T1: a file cannot grow an unclassified key, a kind cannot sit in a file its rule forbids, a machine handle can never be in a tracked file, and the page must name every key |
| R2.1 — a work item's pull requests travel with it | `WorkItemState.pullRequests[]`, written by `GraphLink.on_pr_linked` from both writers | T2, T5, T13 |
| R2.2 — a pull request's upstream state is recorded | `set_pr_state` via `GraphLink.on_pr_state` on the close path | T2, T6 |
| R2.3 — the channel thread travels | the binding in the portable record's `channels` | T7 — a second machine continues the conversation |
| R2.4 — each entity recorded once | the local record keeps only the ref; the repository's file keeps the pull request | T24's leak assertion |
| R3 — no machine handle in a tracked file | the `session` block deleted; `resolve_session` asks the registry | T3, T4, and T1's S9 as the standing rule |
| R4 — the frozen selection is recorded once | `sessionPerPr`/`model`/`effort` on the state; the portable `graph` retired and read-only | T9, T10 |
| R5 — one local file per work item holds every handle | the registry's map plus `channels.slack.cursors` | T12, T24, T25 |
| R6 — machine-wide files named and left alone | `GENERATED_PATHS` unchanged; no pidfile or heartbeat touched | T1's S1–S5, unchanged |
| R7 — the security boundaries of each file are kept | `control`, `collaborators`, `ended` stay with the operator; no workspace id in a repository | `evidence/security-review.md`; T13 |
| R8 — no migration step | every old shape read, new shape written on the next save | T3, T8, T10, T24 |
| R9 — the change is legible | the page, seven capability docs, decision-128, a breaking commit | T15, `evidence/documentation.md` |
| R10 — one portable record per work item | the poller resolves the owner before any write; no `ended` on an owned pull request | T23, T11 |

## Acceptance criteria

- **The ticket's first report — the audit** — is `requirements.md` § Audit: every
  attribute of the four files, classified, with findings F1–F8.
- **The ticket's second report — the viewpoint and the from → to with an example** — is
  `design.md`: the rule, the attribute-by-attribute mapping, and the worked example with
  three pull requests spawning three sessions plus the work item's own, before and after.
- **The owner's two review points** are both in: one portable record per work item
  (R10, design D9), and nothing about a pull request replicated in the local file
  (R5.1, design D10).

## Deviations from the approved design

Three, each found in implementation, each recorded in the design with its reason:

1. **D6** — the thread index is derived on each load, not cached at listener start: the
   daemon and the listener are separate processes, and a cached index would drop a reply
   in a thread the other bound. T19 became `n/a` with it.
2. **D9** — the control plane's issue-302 join **stays**: a pull request given its own
   portable record before this change still has one, and this change deletes no record.
3. **D11, D12** — a read cursor with no session record to live in, and a standing
   session's binding, stay in the channel file: both are machine-local either way, and
   dropping the first would break at-most-once delivery.
