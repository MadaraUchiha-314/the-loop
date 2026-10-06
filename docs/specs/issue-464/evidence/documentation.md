---
type: evidence
phase: needs-review
workItem: "github:MadaraUchiha-314/the-loop#464"
---

# Documentation: a Slack app from one click (issue-464)

## Capability docs

- **[`docs/capabilities/channels.md`](../../../capabilities/channels.md)** gains the
  EARS criteria for `--name`, `--link` and `--write` (renaming, the link, the kept file,
  the delta, the fail-closed read) and a history row.

## Documentation

- **Slack guide** (`docs/guide/slack.md`): step 1 leads with the one-click path and
  explains the name, the handle, the shared `/the-loop` command and re-running after an
  upgrade. Section 1b regenerates and pastes the kept file instead of hand-editing the
  name. The reproduced manifest carries the packaged file's new header lines (a test pins
  the two as identical).
- **Onboarding guide** (`docs/guide/onboarding.md`): init asks the name and hands over
  the link, and tokens never go into the chat.
- **CLI reference** (`docs/cli/commands/channels.md`): the usage line, the `manifest`
  bullet, and four flag rows.
- **Slash commands:** `/the-loop:init` step 5 (ask the name, `--write`, the link, where
  tokens go) and `/the-loop:upgrade-the-loop`'s new step 5 (regenerate, report the delta,
  ask for a name when nothing is kept). Later steps renumbered.
- **Managed files:** `.the-loop/manifest.yaml` lists `.the-loop/slack-app-manifest.json`.
- **Packaged manifest header** (`cli/the_loop/channels/slack-app-manifest.yaml`) names
  the one-click command.
- **`README.md` and the skill** do not describe the Slack setup steps, so they are
  unchanged.
