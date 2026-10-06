---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#465"
---

# Self-review: `the-loop pr ready` (issue-465)

> `the-loop critic list` reports no critics configured in this cloud checkout, so the
> critic rounds are unavailable. Round 3 found nothing new, which meets the stop rule
> (`the-loop critic policy`: 3 self, 3 critic, stop on no new findings).

## Review cycles

| Round | Reviewer | Outcome | Findings → disposition |
|-------|----------|---------|------------------------|
| 1 | self (scope read) | new findings | (a) GitHub's REST API ignores `draft` on `PATCH …/pulls/{n}`, so a REST-only design would report success and change nothing. The verb uses the GraphQL mutation. (b) Letting the caller pass a node id would let it ready any PR the token can write. The id is now read from the resolved PR's own document. |
| 2 | self (diff read) | new findings | (c) `pr.md` said the CLI prints JSON fields; it prints one line, and the route and MCP tool carry the fields. Reworded. (d) Two reflowed paragraphs in `SKILL.md` and `automation.md` ran past the ~90-column prose width. Reflowed. |
| 3 | self (adversarial read) | zero (converged) | — |
| — | critic | unavailable | — |

## Questions asked of the diff, and their answers

- **What if the PR document carries no `node_id`?** `mark_pull_ready` refuses the empty
  id before any request (`GitHubApiError`), and core turns that into exit 1.
- **Does an already-ready PR cost a write?** No. One read, exit 0, `changed: false`. A
  test asserts the only call is `get_pull`.
- **Can a manager run it on the wrong member?** It uses `_acting_member`, the same path
  `pr merge` and `pr resolve-thread` use, so the lifecycle guard runs on the instance
  that registered the work item.
- **Does the human-approval gate notice a PR left as a draft?** Not in this change. The
  skill now tells the agent to ready it first; a gate-side check would be a separate
  work item.
