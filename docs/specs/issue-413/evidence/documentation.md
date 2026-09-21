---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#413"
---

# Documentation record (issue-413)

Updated in this PR:

| Page | What changed |
|---|---|
| `docs/capabilities/channels.md` | two capability statements — the listener's own check, and the surfaces that report it — plus the two new event types in the `channel.*` list |
| `docs/config/cli/channels-options.md` | `slack.read.splitCheckBeats`, with the failure it exists to find and why the report reads a window |
| `docs/cli/commands/status.md` | the new report, why it is sticky, and that it does not move the exit code |
| `docs/cli/commands/channels.md` | the `split check:` line |
| `docs/cli/commands/doctor.md` | the rotation remedy, and that the listener now makes this measurement unasked |
| `docs/cli/state.md` | `<root>/local/slack-split.json` in the tree and the classification table |
| `docs/guide/slack.md` | **When nothing arrives at all** — the symptom, the cause, and the fencing procedure including the token rotation (R4.3) |

Not affected: `docs/capabilities/observability.md` (the event catalog it points at is
`the-loop events --types`, which carries both new types without a page edit),
`docs/capabilities/instances.md`, and every capability doc outside the channel.
