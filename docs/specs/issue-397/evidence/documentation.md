---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#397"
---

# Documentation: minor Slack polish (issue-397)

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `docs/capabilities/channels.md` | room-declaration bullet: a new declaration opens the room's conversation at once (O1); grammar bullet: `help public` is the visible form, plain `help` stays ephemeral, the slash command's answer stays ephemeral (O4); the first-line rule and the connector signature recorded (O5) | issue-397 row added |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/reports/followups/README.md`, `docs/reports/followups/minor-observations-o1-o4-o5.md` | link the filed issue and its PR |
| `cli/the_loop/channels/verbs.py` (`help_text`) | the in-Slack `help` answer names `help public` — the user-facing surface of the grammar |
| README / guide | no change: the Slack guide documents the mention grammar by pointing at `help`, which now teaches the new form itself |
