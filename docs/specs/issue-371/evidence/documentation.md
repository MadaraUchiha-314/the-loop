---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#371"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: every comment the-loop finishes with says so on the comment

> The `capability-docs` node's proof, gating both sections (issue-174).

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `webhook-triggers.md` | A new clause beside issue-84's: an event the dispatcher **consumes** is acknowledged from the same palette — `completed` executed, `error` refused or unreadable, `started` suppressed — after the outcome is recorded and without affecting it; the silent paths (out of scope, duplicate, no work item, policy drop, ingress refusal) named as such | yes (issue-371) |
| `instances.md` | **unaffected** — its rule (§ "no reaction, comment, control record, collaborator grant or session record (D6)") is preserved by construction (the scope refusals have no table entry, and the one route that reaches `_reject_control` passes `acknowledge=False`), so the document remains true as written | n/a |
| `channels.md` | **unaffected** — the Slack pipeline already acknowledges at every accepted path (issue-325) and this work item changes none of it; the audit confirms it rather than altering it | n/a |
| `observability.md` | **unaffected** — it names no reaction event, and the acknowledgement reuses `reaction.added` / `reaction.failed` unchanged, so there is nothing new for it to describe | n/a |
| `control-plane.md` | **unaffected** — it describes the CLI/API control surface, whose comments are self-marked and refused at ingress, so nothing there is acknowledged differently | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/config/cli/routing-options.md` | `reactions.enabled` now states the rule for **both** branches with the full outcome table, and names the two families that stay silent; `reactions.started` / `.completed` / `.error` each say the consumed-branch case they also cover |

## Not documented, deliberately

No decision record. This work item adds no rule the-loop did not already have — issue-84
established "acknowledge on the triggering entity", and this extends it to the branch it
missed. A decision record is for a choice between defensible alternatives that later
readers would otherwise re-litigate; the two choices worth stating (why the suppressed
family is 👀, why there is no fourth state) are in `design.md` § "The table" and
§ "Alternatives considered", where the code's comments point.
