---
type: evidence
workItem: "github:MadaraUchiha-314/the-loop#389"
---

<!-- Authored per the the-loop:writing skill. -->

# Documentation: the mention is the address, and three acts each end in the session

> The `capability-docs` node's proof, gating both sections (issue-174). Task 12 of
> [`tasks.md`](../tasks.md): the operating model and the documentation of design §7 and
> §9, satisfying R4.7, R5.6 and R8.2–R8.4. The code, the catalog, the schema text, the
> channels options page and the packaged manifest are other tasks' and are recorded
> there.

## Capability docs

| Capability doc | What changed | History row |
|----------------|--------------|-------------|
| `channels.md` | Nine new Current-behaviour clauses: the mention rule with §1's input table and the poll skip; the room's listen mode; the grammar and `help`; `record-context` (the snapshot, the cap, the scrub order, the marked record, the `snapshots` idempotency, delivery with the `context` frame, `context.md`); `record-decision` (marked, attributed by the envelope, never a gate answer, `decision-<nnn>.md`); the shortcuts and the modal; the two speaker tiers and a collaborator by Slack id; delivery and `the-loop channels records`; the manifest scope, event and shortcuts with the `status` lines. The catalog bullet names the two grants and why they are not subscriptions; the grants bullet gains the verb step; the issue-375 room bullet says a room hears only mentions unless `--listen all`; the reads bullet names the three new payload kinds and the `snapshots` map; the observability bullet lists the six new drop reasons and six new `channel.*` events. Two Design links (the issue-389 design, decision-133) | yes (issue-389, 2026-09-19) |
| `webhook-triggers.md` | Under *Work-item collaborators*: a roster entry may carry a Slack member id (`add-collaborator slack:U…`, the mention form, `--slack`), at least one id required, fail closed; a Slack-id-only collaborator is input on Slack only and binds nothing | yes (issue-389, 2026-09-19) |
| `observability.md`, `process-graph.md`, `cli.md`, `interactive-sessions.md` | **unaffected** — the new event names live in `channels.md`'s observability bullet as every channel event does; no graph node, no session shape and no verb family changed (`channels records` is a sub-verb of the channels command, documented with its capability) | n/a |

## Documentation

| Document | What changed |
|----------|--------------|
| `skills/the-loop/templates/context.md` | **New** bundled template: `type: context`, no phase, `status: living`; the fixed entry shape (heading with date, person and channel; provenance line; the snapshot as a fenced quote) and one placeholder entry |
| `.the-loop/manifest.yaml` | A `workItemArtifacts` row for `docs/specs/<id>/context.md` (`role: context`, `optional: true`, no phase), so the graph-parity suite knows it as an artifact no node produces |
| `cli/the_loop/interaction.py` | `_ARTIFACT_RULE` names `testing-plan.md` and `context.md` beside the other artifacts and says `context.md` is appended, one entry per record; `cli/tests/test_interaction.py` and `test_interaction_integration.py` pin the new names |
| `skills/the-loop/SKILL.md` | § The artifact chain: `context.md` as the optional fifth artifact (living, no gate, session-kept, one entry per `context.added` record with provenance) and the rule that a `decision.recorded` record becomes `docs/decisions/decision-<nnn>.md` plus its index row; the durable-surface rule and § Knowledge the loop maintains name it |
| `skills/the-loop/reference/workflow.md` | The artifact chain block draws `context.md` beside the chain; a paragraph on the fold-in (the entry shape, the decision record, `the-loop channels records <ref>` at the start of every phase); item 5 in the spec artifacts list |
| `skills/the-loop/reference/collaboration.md` | § Where questions go: the mention rule and its two exceptions, the grammar, the fold-in rule, the two speaker tiers, decision-133; the durable-surface rule names `context.md` |
| `docs/guide/slack.md` | The modes table gains the mention rule and the three acts, and its typed rows now carry the mention; a new *Addressing the-loop* section with the gesture table, the tiers table and what a snapshot copies; *A room for one work item* gains `--listen all` and says a room hears only mentions by default; the upgrade prose and table gain `app_mentions:read`, `app_mention` and the two shortcuts with their callback ids (the fenced manifest block untouched — it is byte-pinned to the packaged manifest, task 2's); *Which events your channel needs* gains the mention row; *Limits* gains the socket requirement and the poll-mode consequence; *Downtime* gains the lost-mention row and scopes the catch-up rows to a DM and an `all` room |
| `docs/config/cli/routing-options.md` | Under `control.keywords.add-channel`: the `--listen` option (`mentions`, the default, or `all`), authorized users only, and that a room's input is what addresses the-loop |
| `docs/cli/commands/add-channel.md`, `docs/cli/commands/add-collaborator.md` | A `--listen` row and a `--slack` row in the Flags tables (the CLI forms of design §2 and §5) |
| `docs/config/cli/channels-options.md`, both `cli-config.schema.json` copies, `skills/the-loop/templates/cli-config.yaml`, `.the-loop/cli-config.yaml`, `cli/the_loop/channels/slack-app-manifest.yaml` | **not in this task** — task 1 (the grant rows and the `publish` description) and task 2 (the manifest) carry them |
| `README.md`, `docs/guide/*` (other pages) | **unchanged, deliberately** — the Slack guide is the one page a Slack operator meets first, and the front page describes the loop, not a channel's grammar |
