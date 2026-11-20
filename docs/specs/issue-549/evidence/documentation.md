---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#549"
---

# Documentation: the Slack collaboration experience

## Capability docs

- `docs/capabilities/channels.md`: the new posting pipeline:
  - room policy, placement, short form, long form, message plan and delivery;
  - defusing, the status reaction, mentions and the recap line;
  - gate buttons on every human gate, and gate messages edited to their outcome;
  - edit retries and the residual re-post window.
- `docs/capabilities/gateway.md`: `reactions.remove` on the method allow-list.

## Documentation

- `docs/config/cli/channels-options.md`: `maxChars` and `longMessages` removed, with a
  migration note (they still validate and warn once).
- `docs/guide/slack.md`: what a room and the central channel show; approving from Slack.
- `docs/cli/commands/comment.md`, `docs/cli/commands/channels.md`: `--summary`; the
  deprecated keys dropped from `channels status`.
- `docs/architecture/architecture.md`: the pipeline line.
- `docs/decisions/decision-154.md` (accepted) supersedes `decision-118.md` (the digest).
- `skills/the-loop/reference/collaboration.md` and
  `skills/the-loop/templates/cli-config.yaml`: the summary rule and the removed keys.
