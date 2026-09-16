---
type: evidence
phase: security-review
workItem: "github:MadaraUchiha-314/the-loop#371"
---

<!-- Authored per the the-loop:writing skill. -->

# Security review: every comment the-loop finishes with says so on the comment

> The `security-review` gate's proof (`reference/security.md`). Always required; an
> unresolved finding blocks completion regardless of risk tier.

## Scope of the change

Three edits to `cli/the_loop/webhook/dispatcher.py`: a constant table, one call added to
`_settle`, and a pass-through flag on `_reject_control`. No new input is read, no new argv
is constructed, no new file is written and no new network surface is opened.

## Threat-model-lite

| Asset | Threat considered | Finding |
|---|---|---|
| The operator's `gh` credential (the daemon's one write surface to GitHub) | A new path reaches `gh` with attacker-influenced arguments | **None.** The acknowledgement calls the same `GitHubReactor.react` the delivered branch calls. The target is resolved by `target_from_event`, whose payload-derived coordinates are regex-validated (`_NAME_RE` for owner/repo, `_NODE_ID_RE` for node ids, `isdigit()` for numeric ids) before they reach an argv; the content is a palette name the config parser validated against `REACTION_CONTENTS`. Nothing from a comment body reaches the command line. |
| A thread on someone else's repository | the-loop decorates a work item it does not own | **None — actively preserved.** issue-322 R2.6 forbids a non-owner instance from leaving any mark. The scope refusals have no table entry, and the one route that would have reached an entry (`_refuse_scope` → `_reject_control` → `control-rejected`) passes `acknowledge=False`. T7 asserts both routes post nothing. |
| Information disclosure to an unauthorized party | A reaction confirms "a daemon is watching here" to someone who may not act | **None.** Every new acknowledgement is downstream of the ingress authorization gate (`authorizedUsers` ∪ the work item's collaborator roster, plus the self-authored marker), so only a party the-loop already accepts as input can provoke one. The strictest case, `_reject_control`'s `unauthorized-actor`, is reachable only by a **work-item collaborator** who typed a control keyword — a person who was granted input on that item by name — or by an actor-less poll-path event. Telling them "no" discloses nothing that executing their comment would not. The refusals that are genuinely anonymous — self-authored, unauthorized-at-ingress — are refused before `handle` is reached and stay silent. |
| Availability of the receiver | A slow or hostile GitHub response holds the dispatcher | **Accepted, bounded.** `_settle` gains one `gh` round trip on the HTTP request thread, bounded by the reactor's timeout, on a receiver that handles deliveries concurrently. `handle` already makes a call of exactly this shape (`_verify_linkage`). The record is written first, so the worst case loses a delivery receipt whose redelivery is deduped. Analysed in `design.md` § "A known consequence". |
| Integrity of the durable record | A reaction failure corrupts or loses a settled delivery | **None.** The reaction is attempted strictly after `deduper.mark_settled` and after the caller's eventlog entry. `GitHubReactor.react` never raises (its contract, held by issue-84's tests); T12 additionally proves the ordering by exploding a stand-in reactor and asserting the settled outcome survives. |
| Amplification | The change multiplies the-loop's writes to GitHub | **Bounded.** At most one reaction per settled event, on paths that previously posted none, and zero when `routing.reactions.enabled` is false (T11). No path posts two. |

## Findings

None. No finding needed a security-relevant decision, so no escalation applies; at risk
tier 3 the autonomous review suffices (`reference/security.md`).
