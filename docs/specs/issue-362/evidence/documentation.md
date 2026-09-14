---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#362"
---

# Documentation: a DM is a channel like any other

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `channels.md` | Three statements of current behaviour: **every kind of conversation is a channel** (the manifest's four scope/event pairs, and the listener's filter staying kind-agnostic); **a channel whose events the app cannot receive is reported** (the prefix-derived line, the `--probe` measurement, the listener's start-up warning, and the fail-quiet rules that keep a finding from misfiring); and the periodic reconcile folded into the existing "downtime is reconciled from the shared cursors" statement | issue-362 |
| `channels.md` (manifest scope list) | The manifest's scope inventory, quoted inline in the slash-command statement, gained `im:history` and `mpim:history` — it had gone stale the moment the manifest changed | issue-362 |

## Documentation

| Document | What changed |
|----------|--------------|
| `docs/guide/slack.md` | The fenced manifest re-synced with the packaged file (a test asserts byte parity); a new **Which events your channel needs** section — the kind → id → scope → event table, what a pre-issue-362 app cannot serve, and the two `channels status` outputs; the **upgrading the app you already have** paragraph and both by-hand rows; the "copy that channel's id" line, which said `C…` as if it were the only shape; and the **Downtime** row and paragraph, now describing the periodic reconcile rather than a connect-only catch-up |
| `docs/config/cli/channels-options.md` | `slack.read.catchUpSeconds` documented with Type and Default (the docs-parity test requires a heading per schema leaf), and the sample YAML at the top of the page |
| `docs/cli/commands/channels.md` | The `status` action's description gained the `read:` cadence, the `channel kind:` line and `--probe`; the Flags table gained the `--probe` row |
| `cli/the_loop/commands/channels_cmd.py` (module docstring) | The five-actions summary said `status` prints presence only; it can now probe, and says so |
| `skills/the-loop/templates/cli-config.yaml` | The commented `read:` block carries the new key, so an operator who starts from the template sees it |
| `cli/the_loop/schemas/cli-config.schema.json`, `.the-loop/cli-config.schema.json` | The schema leaf itself, whose `description` is what `the-loop config` surfaces — byte-identical copies |

## What did not change, and why

- **No README change.** The front page does not name a channel kind or a read cadence;
  the Slack guide it links to is where both live, and that is what moved.
- **No skill or `reference/` change.** `reference/collaboration.md` § Where questions go
  describes how channels compose with the interaction mode, which is unaffected: the
  question still goes to the thread, and the answer still comes back through the same
  pipeline. Nothing in the loop's own rules turned on the conversation's kind.
- **No decision record.** The three layers are the reporter's own proposal, refined
  rather than redirected; `design.md` §Decisions carries the two places it was made
  fail-closed (D2's ambiguity rule, D5's floor). No owner question was opened, so there
  is no human decision to record.
